"""
Pipeline complet : Connecteur -> Fenetre temporelle -> Matching Engine ->
Filtrage faux positifs -> Criticite (et categories des selecteurs trouves)
-> Deduplication -> Persistance -> Alertes.

Chaque connecteur retourne un dict {"entries": [...], "texte_global": ...,
"nb_entries": int}. Le pipeline traite CHAQUE entree individuellement
(une entree = une victime potentielle = une Exposition potentielle),
plutot que la page entiere d'un coup, pour rester precis sur FR-16.

Les entrees ont des schemas heterogenes selon les sources (cles de date
"date_publication", "discovery_date" ou "date" ; nom porte par
"nom_entite_detecte" ou "titre") : _normaliser_entry() les ramene a un
schema unique avant traitement.

ROBUSTESSE - une exception sur UNE entree ne doit jamais interrompre les
entrees suivantes, ni les sources suivantes : le crawl profond multiplie
le nombre d'entrees traitees, donc la surface d'exception. Chaque entree
et chaque connecteur sont isoles, avec rollback de la session (la
deduplication commite en interne : sans rollback, une session en erreur
ferait echouer toutes les entrees suivantes).

COLLECTE PARALLELE - plusieurs sources sont collectees en meme temps
(reglage sources_en_parallele, cf. executer_tous_les_connecteurs). Une
source passe l'essentiel de son temps a attendre : le delai FR-06 entre
deux requetes, plus la latence Tor. Seule cette collecte reseau est
parallele. Tout ce qui lit puis ecrit la base (preparation, analyse,
enregistrement) se fait sous app.db.verrou_base, une source apres
l'autre : deux sources publiant la meme victime n'en font ainsi qu'une
exposition. Le delai FR-06 reste compte PAR SOURCE (BaseConnector), et
une source n'est jamais traitee par deux fils a la fois.
"""

import argparse
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy.orm import joinedload

from app.config_system import get_config_int
from app.connectors import connecteurs_actifs, connecteur_par_nom
from app.conservation import (
    identifiants_des_references, preparer_texte_conserve, signalements_a_completer,
    texte_complet,
)
from app.connectors.dates import CLES_DATE, parser_date
from app.crawl.registre import (
    enregistrer_entrees_vues,
    identifiants_a_relire,
    identifiants_traites,
    marquer_echec_detail,
    marquer_traitee,
    purger_registre,
    signatures_connues,
)
from app.db import get_session, init_db, verrou_base
from app.models import (
    Selecteur, Source, StatutDetailEntree, TypeEvenementCollecte, TypeSource, utc_now,
)
from app import supervision
from app.matching.engine import match_text_against_catalogue
from app.matching.exclusion import filtrer_faux_positifs
from app.matching.criticite import calculer_criticite
from app.matching.deduplication import completer_signalements, enregistrer_exposition
from app.alerting.dispatcher import declencher_alertes

logger = logging.getLogger(__name__)


# Budget global de pages de detail par cycle de collecte.
#
# Chaque requete sur une source attend 30 a 45 s apres la FIN de la
# precedente (FR-06, cf. BaseConnector), plus la latence Tor (5 a 25 s) :
# compter environ 50 s par page de detail. 250 pages representent donc
# environ 3 h 30 de collecte, dans un cycle desormais QUOTIDIEN - la marge
# est large, et les pages non servies sont reprises au cycle suivant.
BUDGET_DETAILS_GLOBAL_PAR_RUN = 250

# Cles possibles pour un meme concept, par ordre de preference.
CLES_NOM = ("nom_entite_detecte", "titre", "nom_entite")
CLES_REFERENCE = ("reference_source", "lien_detail")

# SourceReference.reference_source est une String(500).
LONGUEUR_MAX_REFERENCE = 500


def _get_or_create_source(session, connector) -> Source:
    """
    Retrouve ou cree l'enregistrement Source correspondant au connecteur,
    necessaire pour FR-04 (suivi par source) et FR-17 (audit lie a la source).
    """
    source = session.query(Source).filter_by(
        nom=connector.SOURCE_NAME
    ).first()

    if source is None:
        type_source_enum = TypeSource(connector.SOURCE_TYPE) if connector.SOURCE_TYPE in TypeSource._value2member_map_ else TypeSource.TEST_CLAIRNET
        source = Source(
            nom=connector.SOURCE_NAME,
            type_source=type_source_enum,
            url_ou_identifiant=getattr(connector, "TARGET_URL", None) or "unknown",
        )
        session.add(source)
        session.commit()
        logger.info(f"[pipeline] Nouvelle Source creee en base : {connector.SOURCE_NAME}")

    return source


def _premier_non_vide(entry, cles):
    for cle in cles:
        valeur = entry.get(cle)
        if valeur:
            return valeur
    return None


def _normaliser_entry(entry, connector) -> dict:
    """
    Ramene les schemas heterogenes des connecteurs a un schema unique.
    Remplace le rattrapage par "or" en cascade qui etait dissemine dans la
    boucle de traitement.
    """
    reference = (
        _premier_non_vide(entry, CLES_REFERENCE)
        or getattr(connector, "TARGET_URL", None)
        or "unknown"
    )

    date_publication = parser_date(
        _premier_non_vide(entry, CLES_DATE),
        getattr(connector, "DATE_FORMATS", ()),
        source=connector.SOURCE_NAME,
    )

    return {
        "identifiant_entree": (
            entry.get("identifiant_entree") or connector.identifiant_entree(entry)
        ),
        "nom_entite": _premier_non_vide(entry, CLES_NOM),
        "texte_brut": entry.get("texte_brut") or "",
        "reference_source": str(reference)[:LONGUEUR_MAX_REFERENCE],
        "date_publication": date_publication,
        # Borne posee par un connecteur a listing chronologique sur une
        # annonce non datee ; sert a la fenetre d'analyse, jamais enregistree.
        "date_plafond": entry.get("date_plafond"),
        "niveau_detail": entry.get("niveau_detail", "listing"),
        "a_page_detail": (
            bool(connector.url_detail(entry)) if connector.SUPPORTE_DETAIL else False
        ),
        "echec_detail": entry.get("echec_detail"),
        # Calculee ici parce que le dict normalise perd les cles propres au
        # connecteur (nb_posts, date...) dont elle est tiree.
        "signature_listing": connector.signature_listing(entry),
        # Pose par _analyser_collecte, qui seul a acces au registre : la page
        # de detail de cette annonce ne sera jamais lue (cf.
        # _detail_definitivement_perdu). Sans cette cle, _traiter_une_entree
        # devrait interroger la base par entree.
        "detail_abandonne": False,
    }


def _traiter_une_entree(session, source, entry, selecteurs, seuils, stats) -> bool:
    """
    Applique la chaine d'analyse a UNE entree normalisee.
    Retourne True si l'entree a produit (ou mis a jour) une Exposition.

    seuils : dict issu de _seuils_du_run() (criticite minimale + date limite),
    complete par traiter_connecteur() des signalements a completer.
    """
    texte = entry["texte_brut"]

    # Completion d'une exposition DEJA enregistree, a qui il manque le texte
    # de l'annonce ou ses selecteurs (cf. app.conservation) : des que
    # l'annonce est lue en entier, elle complete son propre signalement.
    signalements = seuils.get("a_completer", {}).get(entry["reference_source"])
    if signalements and texte_complet(entry):
        if not texte:
            # Garde-fou : une annonce vide ne serait jamais completee, et
            # serait relue a chaque cycle. Comptee comme un echec de detail,
            # elle est abandonnee au bout de MAX_ECHECS_DETAIL (registre).
            entry["echec_detail"] = "annonce sans texte"
            return False
        _completer_exposition(session, entry, signalements, selecteurs, stats)
        return True

    if not texte:
        return False

    # FR-03 - une annonce qui POSSEDE une page de detail n'est JAMAIS
    # enregistree sur le seul texte de la page d'accueil (le listing).
    #
    # Sans cette garde, le titre d'une categorie suffisait a creer une
    # Exposition et son alerte ; la page de detail, lue ensuite, relevait la
    # criticite et declenchait une SECONDE alerte pour le meme incident. Et
    # tant que le budget ne servait pas cette page, l'exposition restait
    # partielle (criticite du seul titre, aucun texte conserve).
    #
    # L'entree n'est pas perdue : elle reste A_TRAITER dans le registre (cf.
    # _marquer_dans_le_registre) et _priorite_detail la sert AVANT les autres,
    # puisque son texte de listing cite deja un selecteur.
    #
    # Seule exception, sinon une annonce camerounaise sur une page cassee ne
    # serait jamais signalee : une page de detail definitivement inaccessible
    # (cf. _detail_definitivement_perdu). L'analyse se replie alors sur le
    # titre, avec la criticite partielle que cela implique.
    if not texte_complet(entry) and not entry["detail_abandonne"]:
        stats["nb_details_en_attente"] += 1
        return False

    # FR-03 : fenetre temporelle reglee par l'administrateur.
    #
    # Une entree SANS date exploitable est analysee quand meme : trois de
    # nos sources (payload, safepay, cmd_organization) ne datent pas leurs
    # annonces, les ecarter reviendrait a cesser de les surveiller.
    #
    # Sur un listing chronologique, une annonce sans date n'est pas plus
    # recente que l'annonce datee qui la precede (date_plafond) : si cette
    # borne est deja hors periode, l'annonce l'est aussi.
    date_publication = entry.get("date_publication")
    date_reference = date_publication or entry.get("date_plafond")
    if date_reference is not None and date_reference < seuils["date_limite"]:
        stats["nb_hors_periode"] += 1
        return False

    # FR-09 : matching
    matches_bruts = match_text_against_catalogue(texte, selecteurs)
    if not matches_bruts:
        return False  # aucune correspondance camerounaise, on ignore silencieusement

    # FR-11 : filtrage des faux positifs
    matches_filtres = filtrer_faux_positifs(texte, matches_bruts, session=session)
    if not matches_filtres:
        stats["nb_rejetees_faux_positif"] += 1
        return False

    # FR-10 : criticite (selecteurs distincts, ponderes par leur poids)
    detail = calculer_criticite(matches_filtres)

    if detail.score < seuils["criticite_minimum"]:
        stats["nb_rejetees_criticite_faible"] += 1
        return False

    nom_entite = entry["nom_entite"] or matches_filtres[0].selecteur_valeur or "Entite inconnue"

    # FR-12 : deduplication + persistance
    exposition, est_nouvelle, ancienne_criticite = enregistrer_exposition(
        session=session,
        nom_entite=nom_entite,
        # FR-13 : les categories de l'exposition sont celles des selecteurs
        # qui l'ont declenchee.
        categorie_ids=detail.categories,
        type_source=source.type_source,
        reference_source=entry["reference_source"],
        criticite=detail.score,
        niveau_criticite=detail.niveau,
        source_id=source.id,
        date_publication=date_publication,
        # Derogation CN-04/CN-05 (cf. app.conservation) : le texte COMPLET de
        # l'annonce, masque, est conserve sur le signalement. Pas un titre
        # de listing re-analyse seul.
        texte_brut=preparer_texte_conserve(texte) if texte_complet(entry) else None,
        # Selecteurs trouves, affiches dans le detail de l'exposition.
        selecteurs=detail.details,
    )

    # FR-25/FR-26 : declenchement des alertes (nouvelle detection ou
    # confirmation par hausse significative de la criticite)
    declencher_alertes(
        session, exposition,
        est_nouvelle=est_nouvelle,
        ancienne_criticite=ancienne_criticite,
    )

    stats["nb_expositions_creees_ou_maj"] += 1
    categories = ", ".join(c.nom for c in exposition.categories) or "sans categorie"

    # Seules les NOUVELLES expositions remontent dans la console : une
    # redetection sans gain de criticite n'apprend rien a l'operateur qui
    # regarde le cycle avancer.
    if est_nouvelle:
        supervision.emettre(
            TypeEvenementCollecte.NOUVELLE_EXPOSITION,
            f"{nom_entite} - criticite {detail.resume()} - {categories}",
            source=source.nom,
            exposition_id=exposition.id,
            session=session,
        )

    logger.info(
        f"[pipeline] Exposition traitee : '{nom_entite}' "
        f"(criticite={detail.resume()}, categories={categories}, "
        f"selecteurs={detail.selecteurs})"
    )
    return True


def _completer_exposition(session, entry, signalements, selecteurs, stats):
    """
    Relecture complete d'une annonce deja signalee : texte, selecteurs,
    criticite et categories de son exposition (jamais a la baisse).

    La fenetre d'analyse ne s'applique pas ici : elle sert a ne pas
    DETECTER d'incidents anciens, pas a laisser incomplete une exposition
    deja enregistree. Le seuil minimum d'enregistrement non plus :
    l'exposition existe deja.
    """
    texte = entry["texte_brut"]
    detail = calculer_criticite(filtrer_faux_positifs(
        texte, match_text_against_catalogue(texte, selecteurs), session=session,
    ))

    completees = completer_signalements(
        session, signalements,
        categorie_ids=detail.categories,
        criticite=detail.score,
        niveau_criticite=detail.niveau,
        date_publication=entry.get("date_publication"),
        texte_brut=preparer_texte_conserve(texte),
        selecteurs=detail.details,
    )

    for exposition, ancienne_criticite in completees:
        # Meme regle qu'a toute redetection : une hausse significative de
        # criticite declenche l'alerte de confirmation (FR-25/FR-26).
        declencher_alertes(
            session, exposition, est_nouvelle=False, ancienne_criticite=ancienne_criticite,
        )
        logger.info(
            f"[pipeline] Exposition completee : '{exposition.nom_entite}' "
            f"(criticite {ancienne_criticite} -> {exposition.criticite}, "
            f"selecteurs={detail.selecteurs})"
        )
    stats["nb_expositions_completees"] += len(completees)


def _seuils_du_run() -> dict:
    """
    Lit en UNE fois les reglages administrateur qui bornent le run.

    Les lire ici plutot qu'a chaque entree evite une requete par entree
    (get_config ouvre et ferme une session a chaque appel), tout en
    garantissant qu'un meme cycle applique des reglages coherents meme si
    l'administrateur les modifie pendant la collecte.
    """
    periode_jours = get_config_int("periode_collecte_jours")
    return {
        "criticite_minimum": get_config_int("criticite_minimum_enregistrement"),
        "date_limite": utc_now() - timedelta(days=periode_jours),
        "periode_jours": periode_jours,
    }


# Sources en cours de traitement, affichees par la console de supervision :
# plusieurs a la fois quand la collecte est parallele.
_sources_en_cours = set()
_verrou_sources_en_cours = threading.Lock()


def _publier_source_en_cours(nom, en_cours: bool):
    """Ajoute ou retire une source de la liste publiee pour la console."""
    # La publication reste sous le verrou : deux fils ne peuvent pas
    # publier deux listes dans le desordre.
    with _verrou_sources_en_cours:
        if en_cours:
            _sources_en_cours.add(nom)
        else:
            _sources_en_cours.discard(nom)
        supervision.battre_coeur(
            source_en_cours=", ".join(sorted(_sources_en_cours)) or None
        )


def _catalogue_fige(session) -> list:
    """
    Selecteurs actifs sous forme de tuples (valeur, categorie_id,
    lieu_generique, poids), forme que match_text_against_catalogue accepte.

    Pourquoi pas les objets Selecteur : chaque commit de la session les
    EXPIRE, et le pipeline commite apres chaque entree - chaque analyse
    relisait alors tout le catalogue en base, selecteur par selecteur. Et le
    calcul de priorite des pages de detail tourne pendant la collecte
    reseau, hors verrou : il ne doit pas toucher la base.
    """
    return [
        (
            s.valeur,
            s.categorie_id,
            bool(s.categorie and s.categorie.lieu_generique),
            s.poids or 1,
        )
        for s in (
            session.query(Selecteur)
            .options(joinedload(Selecteur.categorie))
            .filter_by(actif=True)
            .all()
        )
    ]


def _priorite_detail(entree, identifiants_a_completer, catalogue,
                     connector=None, signatures=None) -> int:
    """
    Ordre de service des pages de detail dans le budget du cycle :
      2 - annonce d'une exposition a completer (texte ou selecteurs manquants) ;
      1 - annonce dont le texte de listing cite deja un selecteur du
          catalogue (correspondance exacte : un titre est court, le test est
          immediat) - une annonce probablement camerounaise - OU annonce
          deja traitee dont le listing annonce un volume different, donc du
          contenu qui n'a jamais ete analyse ;
      0 - toutes les autres, dans l'ordre du listing.
    Sans cela, une annonce camerounaise placee bas dans un listing charge
    n'etait lue que sur son titre (criticite partielle, texte non conserve)
    tant que le budget ne l'atteignait pas.

    Tourne pendant la collecte reseau, HORS verrou : ne touche pas la base
    (cf. _catalogue_fige, et 'signatures' lu en amont).
    """
    if entree.get("identifiant_entree") in identifiants_a_completer:
        return 2
    texte = entree.get("texte_brut")
    if texte and match_text_against_catalogue(texte, catalogue, enable_fuzzy=False):
        return 1
    if connector is not None and connector.signature_a_change(entree, signatures):
        return 1
    return 0


def traiter_connecteur(connector_class, db_session=None, budget_details=None,
                       profondeur_max=None) -> dict:
    """
    Execute le pipeline complet pour UN connecteur donne.

    connector_class : classe (pas instance) heritant de BaseConnector.
    budget_details  : nombre maximum de pages de detail pour ce run.
    profondeur_max  : nombre maximum de pages de listing pour ce run.

    Trois temps : preparation et analyse sous app.db.verrou_base, collecte
    reseau hors verrou - c'est elle qui dure, et que la collecte parallele
    fait se chevaucher entre sources.

    Retourne un resume statistique de l'execution.
    """
    session = db_session or get_session()

    with verrou_base:
        source = _get_or_create_source(session, connector_class)
        connector = connector_class(db_session=session, source_id=source.id)

    logger.info(f"[pipeline] === Debut traitement : {connector.SOURCE_NAME} ===")

    # Publie la source en cours d'analyse pour la console de supervision ;
    # le finally la retire quoi qu'il arrive, sans quoi elle resterait
    # affichee au cycle suivant (la liste vit en memoire du processus).
    _publier_source_en_cours(connector.SOURCE_NAME, True)
    try:
        with verrou_base:
            supervision.emettre(
                TypeEvenementCollecte.DEBUT_SOURCE,
                f"Analyse de la source {connector.SOURCE_NAME}...",
                source=connector.SOURCE_NAME,
                session=session,
            )

            # Le connecteur ne lit pas la base : on lui passe ce qu'il doit
            # ignorer, et jusqu'ou remonter (periode et plafond de pages
            # reglables).
            #
            # Une annonce deja analysee dont l'exposition n'a pas encore son
            # texte ou ses selecteurs (analysee avant ces fonctions, ou sur son
            # seul titre) n'est PAS consideree comme connue : sa page de detail
            # est relue, dans le budget du cycle, pour completer l'exposition.
            a_completer, _ = signalements_a_completer(session, source, connector)
            identifiants_a_completer = identifiants_des_references(connector, a_completer)
            connues = identifiants_traites(session, source.id) - identifiants_a_relire(
                session, source.id, identifiants_a_completer,
            )
            # Une entree connue dont le listing annonce un volume different
            # (un post ajoute a une categorie deja traitee) redevient
            # candidate au budget, cf. BaseConnector.signature_a_change.
            signatures = signatures_connues(session, source.id)
            seuils = _seuils_du_run()
            seuils["a_completer"] = a_completer
            if profondeur_max is None:
                profondeur_max = get_config_int("pages_listing_max")
            catalogue = _catalogue_fige(session)

        # Collecte reseau, HORS verrou : les autres sources avancent pendant
        # que celle-ci attend ses reponses. Seul son journal d'audit, en fin
        # de collecte, reprend le verrou (BaseConnector._journaliser_synthese).
        result = connector.collect(
            entrees_connues=connues,
            budget_details=budget_details,
            profondeur_max=profondeur_max,
            date_limite=seuils["date_limite"],
            priorite=lambda entree: _priorite_detail(
                entree, identifiants_a_completer, catalogue, connector, signatures
            ),
            signatures_connues=signatures,
        )

        with verrou_base:
            return _analyser_collecte(session, source, connector, result, seuils, catalogue)
    finally:
        _publier_source_en_cours(connector.SOURCE_NAME, False)


def _analyser_collecte(session, source, connector, result, seuils, catalogue) -> dict:
    """
    Analyse et enregistre ce qu'une collecte a rapporte. Appelee sous
    app.db.verrou_base : une seule source a la fois ecrit en base.
    """
    stats = {
        "source": connector.SOURCE_NAME,
        "collecte_reussie": result["success"],
        "nb_entries_brutes": 0,
        "nb_expositions_creees_ou_maj": 0,
        "nb_expositions_completees": 0,
        "nb_rejetees_faux_positif": 0,
        "nb_rejetees_criticite_faible": 0,
        "nb_hors_periode": 0,
        "nb_sans_date": 0,
        "nb_entrees_en_erreur": 0,
        # Annonces laissees de cote parce que leur page de detail n'a pas
        # encore ete lue (cf. _traiter_une_entree) : elles seront servies en
        # priorite au prochain passage du budget.
        "nb_details_en_attente": 0,
    }
    stats.update(result.get("statistiques_crawl", {}))

    if not result["success"]:
        # Le DETAIL de l'erreur ne remonte PAS dans la console : il est deja
        # journalise dans JournalAudit par BaseConnector et consultable dans
        # la page Audit. On emet neanmoins une ligne de cloture, sans quoi la
        # console resterait bloquee sur "Analyse de la source X..." sans
        # jamais indiquer que le pipeline est passe a la suivante.
        supervision.emettre(
            TypeEvenementCollecte.FIN_SOURCE,
            f"{connector.SOURCE_NAME} : source non joignable ce cycle (detail dans Audit)",
            source=connector.SOURCE_NAME,
            session=session,
        )
        logger.error(f"[pipeline] Collecte echouee pour {connector.SOURCE_NAME} : {result['error']}")
        # Mise a jour du compteur d'erreurs de la source (FR-04)
        source.nombre_erreurs += 1
        session.commit()
        return stats

    # Mise a jour de la derniere collecte reussie (FR-04). Le compteur
    # d'erreurs est remis a zero : sans cela il croit indefiniment et ne
    # represente plus l'etat courant de la source, seulement son passe.
    source.derniere_collecte_reussie = utc_now()
    source.nombre_erreurs = 0
    session.commit()

    # collect() renvoie toujours ses entrees sous "entries" (BaseConnector).
    entries_brutes = result["extracted_text"]["entries"]

    stats["nb_entries_brutes"] = len(entries_brutes)

    entrees = []
    for brute in entries_brutes:
        try:
            entrees.append(_normaliser_entry(brute, connector))
        except Exception as e:
            logger.warning(f"[pipeline] Entree illisible ({connector.SOURCE_NAME}) : {e}")
            stats["nb_entrees_en_erreur"] += 1

    # Le registre voit TOUTES les entrees du listing, y compris celles que
    # le budget ne servira pas ce cycle-ci : un seul commit pour l'ensemble.
    # Compte des entrees sans date exploitable : soit la source n'en publie
    # pas, soit son format n'est pas reconnu (cf. reconnaissance --phase
    # dates). Visible dans la page Collecte, sans avoir a lire les logs.
    stats["nb_sans_date"] = sum(1 for e in entrees if e["date_publication"] is None)

    lignes_registre = enregistrer_entrees_vues(session, source.id, entrees)

    # Une annonce dont la page de detail est definitivement perdue est la
    # seule a pouvoir etre analysee sur son titre (cf. _traiter_une_entree).
    for entree in entrees:
        entree["detail_abandonne"] = _detail_definitivement_perdu(
            lignes_registre.get(entree["identifiant_entree"]), entree, connector
        )

    # Catalogue charge une seule fois, a la preparation de la source
    # (cf. _catalogue_fige) : les commits de la boucle ne l'expirent pas.
    selecteurs = catalogue
    logger.info(
        f"[pipeline] Fenetre d'analyse : {seuils['periode_jours']} jours "
        f"(entrees publiees avant le {seuils['date_limite'].date()} ignorees)."
    )

    for entree in entrees:
        try:
            a_produit = _traiter_une_entree(
                session, source, entree, selecteurs, seuils, stats
            )
            _marquer_dans_le_registre(session, source.id, connector, entree, a_produit)
            # Un commit par entree : une mise a jour du registre non commitee
            # garderait SQLite verrouillee en ecriture pendant l'analyse de
            # toutes les entrees suivantes, et ferait attendre - voire echouer -
            # le heartbeat du scheduler et le journal des autres sources.
            session.commit()
        except Exception as e:
            # enregistrer_exposition() commite en interne : sans rollback,
            # la session resterait en erreur et toutes les entrees suivantes
            # echoueraient en cascade.
            logger.exception(
                f"[pipeline] Entree ignoree ({connector.SOURCE_NAME}, "
                f"{entree['identifiant_entree']}) : {e}"
            )
            session.rollback()
            stats["nb_entrees_en_erreur"] += 1

    session.commit()

    logger.info(f"[pipeline] === Fin traitement {connector.SOURCE_NAME} : {stats} ===")

    supervision.emettre(
        TypeEvenementCollecte.FIN_SOURCE,
        f"{connector.SOURCE_NAME} : {stats['nb_entries_brutes']} entree(s) analysee(s), "
        f"{stats['nb_expositions_creees_ou_maj']} exposition(s), "
        + (f"{stats['nb_expositions_completees']} completee(s), "
           if stats["nb_expositions_completees"] else "")
        + f"{stats['nb_hors_periode']} hors periode"
        + (f", {stats['nb_details_en_attente']} en attente de page de detail"
           if stats["nb_details_en_attente"] else ""),
        source=connector.SOURCE_NAME,
        session=session,
    )

    return stats


def _detail_definitivement_perdu(ligne, entree, connector) -> bool:
    """
    Vrai quand la page de detail de cette annonce ne sera jamais lue : soit
    elle est deja abandonnee (StatutDetailEntree.ECHEC), soit l'echec de CE
    cycle est celui qui l'abandonne.

    L'echec courant est ANTICIPE parce que le registre n'est ecrit qu'APRES
    l'analyse (cf. _marquer_dans_le_registre) : au moment ou l'entree est
    analysee, nb_echecs_detail ne compte pas encore l'echec du cycle en
    cours. Sans cette anticipation, l'entree serait ecartee par
    _traiter_une_entree, puis passerait en ECHEC et ne reviendrait jamais
    dans le budget : le repli sur le titre ne se declencherait jamais.
    """
    if ligne is None:
        return False
    if ligne.statut_detail == StatutDetailEntree.ECHEC:
        return True
    return bool(entree["echec_detail"]) and (
        ligne.nb_echecs_detail + 1 >= connector.MAX_ECHECS_DETAIL
    )


def _marquer_dans_le_registre(session, source_id, connector, entree, a_produit):
    """
    Met a jour le registre APRES analyse de l'entree (cf. app.crawl.registre).

    Une entree nouvelle que le budget n'a pas servie n'est volontairement PAS
    marquee : elle reste A_TRAITER et sera drainee au cycle suivant. C'est le
    mecanisme de reprise du crawl.
    """
    identifiant = entree["identifiant_entree"]

    if entree["echec_detail"]:
        marquer_echec_detail(
            session, source_id, identifiant, max_echecs=connector.MAX_ECHECS_DETAIL
        )
    elif entree["niveau_detail"] == "detail" or not entree["a_page_detail"]:
        # Marque TRAITEE meme sans correspondance : sinon les entrees non
        # camerounaises, l'immense majorite, seraient reproposees a l'infini.
        #
        # La signature n'est rafraichie que quand la page de detail vient
        # d'etre lue : sur une simple relecture de titre, l'ancienne reste,
        # sans quoi un changement serait oublie avant d'avoir ete analyse.
        marquer_traitee(
            session, source_id, identifiant,
            a_produit_exposition=a_produit,
            signature_listing=(
                entree["signature_listing"] if entree["niveau_detail"] == "detail" else None
            ),
        )


def _repartir_budget(classes, budget_global) -> dict:
    """
    Repartit le budget de pages de detail entre les sources : une passe
    equitable, puis une passe de reliquat. Sans cela, le premier connecteur
    de la liste consommerait tout le budget et les derniers n'auraient
    jamais leur tour.
    """
    if not classes:
        return {}

    parts = {}
    equitable = budget_global // len(classes)
    for classe in classes:
        parts[classe.SOURCE_NAME] = min(classe.MAX_DETAILS_PAR_RUN, equitable)

    reliquat = budget_global - sum(parts.values())
    for classe in classes:
        if reliquat <= 0:
            break
        supplement = min(
            classe.MAX_DETAILS_PAR_RUN - parts[classe.SOURCE_NAME], reliquat
        )
        parts[classe.SOURCE_NAME] += supplement
        reliquat -= supplement

    return parts


def _traiter_isole(connector_class, budget_details, profondeur_max) -> dict:
    """
    Traite UNE source dans SA PROPRE session : une session SQLAlchemy ne se
    partage pas entre fils. Une erreur fatale devient un resultat d'echec,
    sans jamais interrompre les autres sources.
    """
    session = get_session()
    try:
        return traiter_connecteur(
            connector_class,
            db_session=session,
            budget_details=budget_details,
            profondeur_max=profondeur_max,
        )
    except Exception as e:
        logger.exception(
            f"[pipeline] Connecteur {connector_class.SOURCE_NAME} en erreur fatale : {e}"
        )
        session.rollback()
        return {
            "source": connector_class.SOURCE_NAME,
            "collecte_reussie": False,
            "erreur_fatale": f"{type(e).__name__}: {str(e)[:200]}",
        }
    finally:
        session.close()


def nombre_de_sources_en_parallele(paralleles, nb_sources) -> int:
    """
    Nombre de sources collectees en meme temps : la valeur demandee (sinon
    le reglage sources_en_parallele), bornee a [1, nombre de sources].
    1 = collecte sequentielle, une source apres l'autre.
    """
    demande = get_config_int("sources_en_parallele") if paralleles is None else paralleles
    return max(1, min(demande, nb_sources))


def executer_tous_les_connecteurs(budget_global=None, profondeur_max=None,
                                  classes=None, paralleles=None) -> list:
    """
    Execute le pipeline pour l'ensemble des connecteurs du registre
    (app.connectors.connecteurs_actifs). Respecte automatiquement le rate
    limiting (FR-06) via BaseConnector, et journalise chaque collecte (FR-17).

    paralleles : nombre de sources collectees en meme temps (par defaut :
    reglage sources_en_parallele ; cf. en-tete du module).

    Un connecteur qui echoue de maniere fatale n'interrompt pas les autres.
    Les resultats sont rendus dans l'ordre du registre, quel que soit
    l'ordre dans lequel les sources ont fini.
    """
    classes = classes if classes is not None else connecteurs_actifs()
    budget = BUDGET_DETAILS_GLOBAL_PAR_RUN if budget_global is None else budget_global
    parts = _repartir_budget(classes, budget)
    nb_fils = nombre_de_sources_en_parallele(paralleles, len(classes))

    logger.info(
        f"[pipeline] Cycle de collecte : {len(classes)} source(s), "
        f"{nb_fils} en parallele."
    )

    with ThreadPoolExecutor(max_workers=nb_fils, thread_name_prefix="collecte") as pool:
        futurs = [
            pool.submit(
                _traiter_isole, classe, parts.get(classe.SOURCE_NAME, 0), profondeur_max,
            )
            for classe in classes
        ]
        tous_les_stats = [futur.result() for futur in futurs]

    session = get_session()
    try:
        with verrou_base:
            purger_registre(session)
            supervision.purger_evenements(session)
    finally:
        session.close()
    return tous_les_stats


def _analyser_arguments():
    parseur = argparse.ArgumentParser(
        description="Execute un cycle de collecte (FR-03 a FR-13)."
    )
    parseur.add_argument(
        "--source",
        help="N'executer qu'un seul connecteur, par son SOURCE_NAME.",
    )
    parseur.add_argument(
        "--budget-details", type=int, default=None,
        help="Nombre maximum de pages de detail pour ce run, toutes sources confondues.",
    )
    parseur.add_argument(
        "--profondeur-max", type=int, default=None,
        help="Plafond de pages de listing par source pour ce run "
             "(par defaut : reglage pages_listing_max).",
    )
    parseur.add_argument(
        "--paralleles", type=int, default=None,
        help="Nombre de sources collectees en meme temps pour ce run "
             "(par defaut : reglage sources_en_parallele ; 1 = l'une apres l'autre).",
    )
    return parseur.parse_args()


if __name__ == "__main__":
    # threadName : avec la collecte parallele, les lignes des sources
    # s'entremelent ; le nom du fil ("collecte_0"...) permet de les suivre.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    )
    arguments = _analyser_arguments()
    init_db()

    resultats = executer_tous_les_connecteurs(
        budget_global=arguments.budget_details,
        profondeur_max=arguments.profondeur_max,
        classes=[connecteur_par_nom(arguments.source)] if arguments.source else None,
        paralleles=arguments.paralleles,
    )

    print("\n" + "=" * 60)
    print("RESUME GLOBAL DU PIPELINE")
    print("=" * 60)
    for r in resultats:
        print(f"\nSource : {r['source']}")
        print(f"  Collecte reussie : {r['collecte_reussie']}")
        if r.get("erreur_fatale"):
            print(f"  ERREUR FATALE : {r['erreur_fatale']}")
            continue
        print(f"  Pages de listing parcourues : {r.get('pages_listing', 0)}")
        print(f"  Entrees brutes analysees : {r.get('nb_entries_brutes', 0)}")
        print(f"  Entrees nouvelles : {r.get('nouvelles', 0)}")
        print(f"  Pages de detail recuperees : {r.get('details_ok', 0)}"
              f" (echecs : {r.get('details_echec', 0)},"
              f" hors budget : {r.get('details_ignores', 0)},"
              f" relues pour changement : {r.get('details_relus', 0)})")
        print(f"  Expositions creees/mises a jour : {r.get('nb_expositions_creees_ou_maj', 0)}")
        print(f"  Expositions completees (texte, selecteurs) : {r.get('nb_expositions_completees', 0)}")
        print(f"  Entrees sans date exploitable : {r.get('nb_sans_date', 0)}")
        print(f"  En attente de leur page de detail : {r.get('nb_details_en_attente', 0)}")
        print(f"  Rejetees (hors periode) : {r.get('nb_hors_periode', 0)}")
        print(f"  Rejetees (faux positif) : {r.get('nb_rejetees_faux_positif', 0)}")
        print(f"  Rejetees (criticite trop faible) : {r.get('nb_rejetees_criticite_faible', 0)}")
        print(f"  Entrees en erreur : {r.get('nb_entrees_en_erreur', 0)}")
        print(f"  Motif d'arret du crawl : {r.get('arret', '-')}"
              f" ({r.get('duree_s', 0)}s)")
