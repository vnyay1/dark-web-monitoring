"""
Pipeline complet : Connecteur -> Matching Engine -> Scoring -> Filtrage
faux positifs -> Categorisation -> Deduplication -> Persistance -> Audit.

Chaque connecteur retourne un dict {"entries": [...], "texte_global": ...,
"nb_entries": int}. Le pipeline traite CHAQUE entree individuellement
(une entree = une victime potentielle = une Exposition potentielle),
plutot que la page entiere d'un coup, pour rester precis sur FR-16.
"""

import logging

from app.db import get_session, init_db
from app.models import Selecteur, Source, TypeSource
from app.matching.engine import match_text_against_catalogue
from app.matching.exclusion import filtrer_faux_positifs
from app.matching.scoring import calculer_score_confiance
from app.matching.categorisation import categoriser_texte
from app.matching.deduplication import enregistrer_exposition

logger = logging.getLogger(__name__)


# Seuil minimum de score de confiance en-dessous duquel une entree
# n'est meme pas enregistree en base (evite de polluer la base avec
# du bruit pur). Ajustable - actuellement permissif pour ne rien perdre
# au debut, l'analyste peut ensuite marquer manuellement en False Positive.
SEUIL_ENREGISTREMENT_MINIMUM = 0.15


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
            url_ou_identifiant=getattr(connector, "TARGET_URL", "unknown"),
        )
        session.add(source)
        session.commit()
        logger.info(f"[pipeline] Nouvelle Source creee en base : {connector.SOURCE_NAME}")

    return source


def traiter_connecteur(connector_class, db_session=None) -> dict:
    """
    Execute le pipeline complet pour UN connecteur donne.

    connector_class : classe (pas instance) heritant de BaseConnector,
    ex: PayloadConnector, SafePayConnector, etc.

    Retourne un resume statistique de l'execution.
    """
    session = db_session or get_session()

    source = _get_or_create_source(session, connector_class)

    connector = connector_class(db_session=session, source_id=source.id)

    logger.info(f"[pipeline] === Debut traitement : {connector.SOURCE_NAME} ===")

    result = connector.collect()

    stats = {
        "source": connector.SOURCE_NAME,
        "collecte_reussie": result["success"],
        "nb_entries_brutes": 0,
        "nb_expositions_creees_ou_maj": 0,
        "nb_rejetees_faux_positif": 0,
        "nb_rejetees_score_faible": 0,
    }

    if not result["success"]:
        logger.error(f"[pipeline] Collecte echouee pour {connector.SOURCE_NAME} : {result['error']}")
        # Mise a jour du compteur d'erreurs de la source (FR-04)
        source.nombre_erreurs += 1
        session.commit()
        return stats

    # Mise a jour de la derniere collecte reussie (FR-04)
    from app.models import utc_now
    source.derniere_collecte_reussie = utc_now()
    session.commit()

    extracted = result["extracted_text"]

    # Compatibilite : tous nos connecteurs actuels retournent un dict
    # avec "entries", mais on protege contre un futur connecteur qui
    # retournerait juste une chaine de texte brute
    if isinstance(extracted, dict) and "entries" in extracted:
        entries = extracted["entries"]
    else:
        entries = [{"texte_brut": str(extracted)}]

    stats["nb_entries_brutes"] = len(entries)

    # Selecteurs actifs charges une seule fois pour toutes les entrees
    selecteurs = session.query(Selecteur).filter_by(actif=True).all()

    for entry in entries:
        texte = entry.get("texte_brut", "")
        if not texte:
            continue

        # FR-09 : matching
        matches_bruts = match_text_against_catalogue(texte, selecteurs)

        if not matches_bruts:
            continue  # aucune correspondance camerounaise, on ignore silencieusement

        # FR-11 : filtrage des faux positifs
        matches_filtres = filtrer_faux_positifs(texte, matches_bruts, session=session)

        if not matches_filtres:
            stats["nb_rejetees_faux_positif"] += 1
            continue

        # FR-10 : scoring
        score_detail = calculer_score_confiance(
            matches_filtres,
            nombre_erreurs_source=source.nombre_erreurs,
            nombre_collectes_total_source=None,  # historique detaille non trackee pour l'instant
        )

        if score_detail.score_final < SEUIL_ENREGISTREMENT_MINIMUM:
            stats["nb_rejetees_score_faible"] += 1
            continue

        # FR-13 : categorisation
        categorie_fuite, _ = categoriser_texte(texte)

        # Nom de l'entite : priorite au champ structure du connecteur,
        # sinon on prend le nom du sélecteur le plus précis trouvé comme repli
        nom_entite = (
            entry.get("nom_entite_detecte")
            or entry.get("titre")
            or (matches_filtres[0].selecteur_valeur if matches_filtres else "Entite inconnue")
        )

        # Reference de la source : lien de detail si disponible, sinon
        # l'URL de la page principale du connecteur
        reference_source = (
            entry.get("lien_detail")
            or entry.get("lien_article")
            or getattr(connector, "TARGET_URL", "unknown")
        )

        # FR-12 : deduplication + persistance
        exposition = enregistrer_exposition(
            session=session,
            nom_entite=nom_entite,
            categorie_fuite=categorie_fuite,
            type_source=source.type_source,
            reference_source=reference_source,
            score_confiance=score_detail.score_final,
            nombre_enregistrements=None,  # non deduit automatiquement du texte pour l'instant
        )

        stats["nb_expositions_creees_ou_maj"] += 1
        logger.info(
            f"[pipeline] Exposition traitee : '{nom_entite}' "
            f"(score={score_detail.score_final}, categorie={categorie_fuite.value})"
        )

    logger.info(f"[pipeline] === Fin traitement {connector.SOURCE_NAME} : {stats} ===")
    return stats


def executer_tous_les_connecteurs() -> list:
    """
    Execute le pipeline pour l'ensemble des 7 connecteurs actuellement
    disponibles. Respecte automatiquement le rate limiting (FR-06) via
    BaseConnector, et journalise chaque collecte (FR-17).
    """
    from app.connectors.payload_connector import PayloadConnector
    from app.connectors.orionleaks_connector import OrionLeaksConnector
    from app.connectors.dataexposurelogs_connector import DataExposureLogsConnector
    from app.connectors.blackwater_connector import BlackWaterConnector
    from app.connectors.safepay_connector import SafePayConnector
    from app.connectors.thehackernews_connector import TheHackerNewsConnector
    from app.connectors.cmdorganization_connector import CmdOrganizationConnector

    connecteurs = [
        PayloadConnector,
        OrionLeaksConnector,
        DataExposureLogsConnector,
        BlackWaterConnector,
        SafePayConnector,
        TheHackerNewsConnector,
        CmdOrganizationConnector,
    ]

    session = get_session()
    tous_les_stats = []

    for connector_class in connecteurs:
        stats = traiter_connecteur(connector_class, db_session=session)
        tous_les_stats.append(stats)

    session.close()
    return tous_les_stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    init_db()

    resultats = executer_tous_les_connecteurs()

    print("\n" + "=" * 60)
    print("RESUME GLOBAL DU PIPELINE")
    print("=" * 60)
    for r in resultats:
        print(f"\nSource : {r['source']}")
        print(f"  Collecte reussie : {r['collecte_reussie']}")
        print(f"  Entrees brutes analysees : {r['nb_entries_brutes']}")
        print(f"  Expositions creees/mises a jour : {r['nb_expositions_creees_ou_maj']}")
        print(f"  Rejetees (faux positif) : {r['nb_rejetees_faux_positif']}")
        print(f"  Rejetees (score trop faible) : {r['nb_rejetees_score_faible']}")