"""
Pipeline complet : Connecteur -> Matching Engine -> Scoring -> Filtrage
faux positifs -> Categorisation -> Deduplication -> Persistance -> Audit.

Chaque connecteur retourne un dict {"entries": [...], "texte_global": ...,
"nb_entries": int}. Le pipeline traite CHAQUE entree individuellement
(une entree = une victime potentielle = une Exposition potentielle),
plutot que la page entiere d'un coup, pour rester precis sur FR-16.

Les entrees ont des schemas heterogenes selon les sources (thehackernews
expose "titre"/"lien_article" la ou les autres exposent
"nom_entite_detecte"/"lien_detail") : _normaliser_entry() les ramene a un
schema unique avant traitement.

ROBUSTESSE - une exception sur UNE entree ne doit jamais interrompre les
entrees suivantes, ni les sources suivantes : le crawl profond multiplie
le nombre d'entrees traitees, donc la surface d'exception. Chaque entree
et chaque connecteur sont isoles, avec rollback de la session (la
deduplication commite en interne : sans rollback, une session en erreur
ferait echouer toutes les entrees suivantes).
"""

import argparse
import logging

from app.config_system import get_config_float
from app.connectors import connecteurs_actifs, connecteur_par_nom
from app.crawl.registre import (
    enregistrer_entrees_vues,
    identifiants_traites,
    marquer_echec_detail,
    marquer_traitee,
    purger_registre,
)
from app.db import get_session, init_db
from app.models import Selecteur, Source, TypeSource, utc_now
from app.matching.engine import match_text_against_catalogue
from app.matching.exclusion import filtrer_faux_positifs
from app.matching.scoring import calculer_score_confiance
from app.matching.categorisation import categoriser_texte
from app.matching.deduplication import enregistrer_exposition
from app.alerting.dispatcher import declencher_alertes

logger = logging.getLogger(__name__)


# Budget global de pages de detail par cycle de collecte.
#
# Il n'est pas choisi arbitrairement : le scheduler tourne toutes les 6h avec
# max_instances=1, donc un run doit tenir dans 21600s. A 30s minimum par
# requete (FR-06), le plafond theorique absolu est 720 requetes. En tenant
# compte de la latence Tor (5-20s en plus du delai) et des reessais, on vise
# ~250 requetes, soit environ 3h - la moitie de la fenetre.
BUDGET_DETAILS_GLOBAL_PAR_RUN = 250

# Cles possibles pour un meme concept, par ordre de preference.
CLES_NOM = ("nom_entite_detecte", "titre", "nom_entite")
CLES_REFERENCE = ("reference_source", "lien_detail", "lien_article")

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

    return {
        "identifiant_entree": (
            entry.get("identifiant_entree") or connector.identifiant_entree(entry)
        ),
        "nom_entite": _premier_non_vide(entry, CLES_NOM),
        "texte_brut": entry.get("texte_brut") or "",
        "reference_source": str(reference)[:LONGUEUR_MAX_REFERENCE],
        "niveau_detail": entry.get("niveau_detail", "listing"),
        "a_page_detail": (
            bool(connector.url_detail(entry)) if connector.SUPPORTE_DETAIL else False
        ),
        "echec_detail": entry.get("echec_detail"),
    }


def _traiter_une_entree(session, source, entry, selecteurs, seuil, stats) -> bool:
    """
    Applique la chaine d'analyse a UNE entree normalisee.
    Retourne True si l'entree a produit (ou mis a jour) une Exposition.
    """
    texte = entry["texte_brut"]
    if not texte:
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

    # FR-10 : scoring
    score_detail = calculer_score_confiance(
        matches_filtres,
        nombre_erreurs_source=source.nombre_erreurs,
        nombre_collectes_total_source=None,  # historique detaille non tracke pour l'instant
    )

    if score_detail.score_final < seuil:
        stats["nb_rejetees_score_faible"] += 1
        return False

    # FR-13 : categorisation
    categorie_fuite, _ = categoriser_texte(texte)

    nom_entite = entry["nom_entite"] or matches_filtres[0].selecteur_valeur or "Entite inconnue"

    # FR-12 : deduplication + persistance
    exposition, est_nouvelle, ancien_score = enregistrer_exposition(
        session=session,
        nom_entite=nom_entite,
        categorie_fuite=categorie_fuite,
        type_source=source.type_source,
        reference_source=entry["reference_source"],
        score_confiance=score_detail.score_final,
        nombre_enregistrements=None,
    )

    # FR-25/FR-26 : declenchement des alertes (nouvelle detection ou
    # confirmation par hausse significative du score)
    declencher_alertes(session, exposition, est_nouvelle=est_nouvelle, ancien_score=ancien_score)

    stats["nb_expositions_creees_ou_maj"] += 1
    logger.info(
        f"[pipeline] Exposition traitee : '{nom_entite}' "
        f"(score={score_detail.score_final}, categorie={categorie_fuite.value})"
    )
    return True


def traiter_connecteur(connector_class, db_session=None, budget_details=None,
                       profondeur_max=None) -> dict:
    """
    Execute le pipeline complet pour UN connecteur donne.

    connector_class : classe (pas instance) heritant de BaseConnector.
    budget_details  : nombre maximum de pages de detail pour ce run.
    profondeur_max  : nombre maximum de pages de listing pour ce run.

    Retourne un resume statistique de l'execution.
    """
    session = db_session or get_session()

    source = _get_or_create_source(session, connector_class)
    connector = connector_class(db_session=session, source_id=source.id)

    logger.info(f"[pipeline] === Debut traitement : {connector.SOURCE_NAME} ===")

    # Le connecteur ne lit pas la base : on lui passe ce qu'il doit ignorer.
    connues = identifiants_traites(session, source.id)

    result = connector.collect(
        entrees_connues=connues,
        budget_details=budget_details,
        profondeur_max=profondeur_max,
    )

    stats = {
        "source": connector.SOURCE_NAME,
        "collecte_reussie": result["success"],
        "nb_entries_brutes": 0,
        "nb_expositions_creees_ou_maj": 0,
        "nb_rejetees_faux_positif": 0,
        "nb_rejetees_score_faible": 0,
        "nb_entrees_en_erreur": 0,
    }
    stats.update(result.get("statistiques_crawl", {}))

    if not result["success"]:
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

    extracted = result["extracted_text"]

    # Compatibilite : tous nos connecteurs actuels retournent un dict
    # avec "entries", mais on protege contre un futur connecteur qui
    # retournerait juste une chaine de texte brute
    if isinstance(extracted, dict) and "entries" in extracted:
        entries_brutes = extracted["entries"]
    else:
        entries_brutes = [{"texte_brut": str(extracted)}]

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
    enregistrer_entrees_vues(session, source.id, entrees)

    # Selecteurs actifs charges une seule fois pour toutes les entrees
    selecteurs = session.query(Selecteur).filter_by(actif=True).all()
    seuil = get_config_float("seuil_enregistrement_minimum")

    for entree in entrees:
        try:
            a_produit = _traiter_une_entree(
                session, source, entree, selecteurs, seuil, stats
            )
            _marquer_dans_le_registre(session, source.id, connector, entree, a_produit)
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
    return stats


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
        marquer_traitee(session, source_id, identifiant, a_produit_exposition=a_produit)


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


def executer_tous_les_connecteurs(budget_global=None, profondeur_max=None,
                                  classes=None) -> list:
    """
    Execute le pipeline pour l'ensemble des connecteurs du registre
    (app.connectors.connecteurs_actifs). Respecte automatiquement le rate
    limiting (FR-06) via BaseConnector, et journalise chaque collecte (FR-17).

    Un connecteur qui echoue de maniere fatale n'interrompt pas les suivants.
    """
    classes = classes if classes is not None else connecteurs_actifs()
    budget = BUDGET_DETAILS_GLOBAL_PAR_RUN if budget_global is None else budget_global
    parts = _repartir_budget(classes, budget)

    session = get_session()
    tous_les_stats = []

    for connector_class in classes:
        try:
            stats = traiter_connecteur(
                connector_class,
                db_session=session,
                budget_details=parts.get(connector_class.SOURCE_NAME, 0),
                profondeur_max=profondeur_max,
            )
        except Exception as e:
            logger.exception(
                f"[pipeline] Connecteur {connector_class.SOURCE_NAME} en erreur fatale : {e}"
            )
            session.rollback()
            stats = {
                "source": connector_class.SOURCE_NAME,
                "collecte_reussie": False,
                "erreur_fatale": f"{type(e).__name__}: {str(e)[:200]}",
            }
        tous_les_stats.append(stats)

    purger_registre(session)
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
        help="Nombre maximum de pages de listing par source (rattrapage ponctuel).",
    )
    return parseur.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    arguments = _analyser_arguments()
    init_db()

    resultats = executer_tous_les_connecteurs(
        budget_global=arguments.budget_details,
        profondeur_max=arguments.profondeur_max,
        classes=[connecteur_par_nom(arguments.source)] if arguments.source else None,
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
              f" hors budget : {r.get('details_ignores', 0)})")
        print(f"  Expositions creees/mises a jour : {r.get('nb_expositions_creees_ou_maj', 0)}")
        print(f"  Rejetees (faux positif) : {r.get('nb_rejetees_faux_positif', 0)}")
        print(f"  Rejetees (score trop faible) : {r.get('nb_rejetees_score_faible', 0)}")
        print(f"  Entrees en erreur : {r.get('nb_entrees_en_erreur', 0)}")
        print(f"  Motif d'arret du crawl : {r.get('arret', '-')}"
              f" ({r.get('duree_s', 0)}s)")
