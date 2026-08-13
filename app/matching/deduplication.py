"""
FR-12 - Deduplication des expositions detectees sur plusieurs sources.

Regle d'identite proposee (a valider avec l'encadrant si possible - aucune
formule n'est donnee dans le cahier des charges) : deux detections sont
considerees comme LE MEME incident si :
  1. Le nom d'entite est identique ou tres similaire (fuzzy)
  2. La categorie de fuite est identique
  3. La premiere detection existante date de moins de FENETRE_JOURS jours

Si une correspondance est trouvee : la date de derniere detection est mise
a jour, et une nouvelle SourceReference est ajoutee sans creer de nouvelle
Exposition. Sinon, une nouvelle Exposition est creee.
"""

import logging
from datetime import timedelta
from rapidfuzz import fuzz

from app.models import Exposition, SourceReference, CategorieFuite, TypeSource, utc_now

logger = logging.getLogger(__name__)


SEUIL_SIMILARITE_NOM_ENTITE = 90  # score RapidFuzz (0-100)
FENETRE_JOURS = 30


def _trouver_exposition_existante(session, nom_entite: str, categorie_fuite: CategorieFuite):
    """
    Cherche parmi les expositions existantes (recentes) celle qui correspond
    probablement au meme incident, selon la regle d'identite definie.
    """
    seuil_date = utc_now() - timedelta(days=FENETRE_JOURS)

    candidates = (
        session.query(Exposition)
        .filter(Exposition.categorie_fuite == categorie_fuite)
        .filter(Exposition.date_premiere_detection >= seuil_date)
        .all()
    )

    meilleure_correspondance = None
    meilleur_score = 0

    for exposition in candidates:
        score = fuzz.ratio(nom_entite.lower(), exposition.nom_entite.lower())
        if score >= SEUIL_SIMILARITE_NOM_ENTITE and score > meilleur_score:
            meilleure_correspondance = exposition
            meilleur_score = score

    if meilleure_correspondance:
        logger.info(
            f"[FR-12] Incident existant trouve pour '{nom_entite}' "
            f"-> '{meilleure_correspondance.nom_entite}' (similarite={meilleur_score})"
        )

    return meilleure_correspondance


def enregistrer_exposition(
    session,
    nom_entite: str,
    categorie_fuite: CategorieFuite,
    type_source: TypeSource,
    reference_source: str,
    score_confiance: float,
    nombre_enregistrements: int = None,
    secteur_activite: str = None,
    type_entite=None,
) -> Exposition:
    """
    Point d'entree principal FR-12 : enregistre une detection en
    deduppliquant si un incident correspondant existe deja.

    Retourne l'Exposition (nouvelle ou existante mise a jour).
    """
    exposition_existante = _trouver_exposition_existante(session, nom_entite, categorie_fuite)

    if exposition_existante:
        # Incident deja connu : on met a jour la date de derniere detection
        # et on ajoute une nouvelle reference de source, sans dupliquer
        exposition_existante.date_derniere_detection = utc_now()

        # On ne rajoute pas deux fois la meme reference exacte pour la
        # meme exposition (ex: si le meme connecteur repasse sur la meme page)
        reference_deja_presente = any(
            sr.reference_source == reference_source and sr.type_source == type_source
            for sr in exposition_existante.sources
        )

        if not reference_deja_presente:
            nouvelle_reference = SourceReference(
                exposition_id=exposition_existante.id,
                type_source=type_source,
                reference_source=reference_source,
            )
            session.add(nouvelle_reference)
            logger.info(f"[FR-12] Nouvelle SourceReference ajoutee a l'exposition existante '{nom_entite}'.")
        else:
            logger.info("[FR-12] Reference de source deja presente, aucun doublon ajoute.")

        # Le score de confiance peut etre reevalue a la hausse si confirme
        # par plusieurs sources independantes (coherent avec FR-10 - le
        # nombre de correspondances independantes augmente la confiance)
        if score_confiance > exposition_existante.score_confiance:
            exposition_existante.score_confiance = score_confiance

        session.commit()
        return exposition_existante

    # Aucun incident correspondant : creation d'une nouvelle Exposition
    nouvelle_exposition = Exposition(
        nom_entite=nom_entite,
        secteur_activite=secteur_activite,
        type_entite=type_entite,
        categorie_fuite=categorie_fuite,
        nombre_enregistrements_revendique=nombre_enregistrements,
        score_confiance=score_confiance,
    )
    session.add(nouvelle_exposition)
    session.flush()  # pour obtenir l'id avant de creer la SourceReference

    reference = SourceReference(
        exposition_id=nouvelle_exposition.id,
        type_source=type_source,
        reference_source=reference_source,
    )
    session.add(reference)
    session.commit()

    logger.info(f"[FR-12] Nouvelle exposition creee : '{nom_entite}' ({categorie_fuite.value}).")
    return nouvelle_exposition