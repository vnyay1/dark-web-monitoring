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

from app.models import (
    Categorie, Exposition, SourceReference, NiveauCriticite, TypeSource, utc_now,
)

logger = logging.getLogger(__name__)


SEUIL_SIMILARITE_NOM_ENTITE = 90  # score RapidFuzz (0-100)
FENETRE_JOURS = 30


def _trouver_exposition_existante(session, nom_entite: str):
    """
    Cherche parmi les expositions existantes (recentes) celle qui
    correspond probablement au meme incident.

    Les categories ne sont PAS un critere de correspondance : deux annonces
    sur la meme victime peuvent citer des selecteurs differents. C'est le
    NOM DE L'ENTITE (avec tolerance fuzzy) et la fenetre temporelle qui
    definissent l'identite de l'incident.
    """
    seuil_date = utc_now() - timedelta(days=FENETRE_JOURS)

    candidates = (
        session.query(Exposition)
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

def _ajouter_reference(session, exposition, type_source, reference_source,
                       source_id, date_publication):
    """
    Ajoute un signalement de source a une exposition, sans doublon.
    Retourne True si une reference a effectivement ete ajoutee.
    """
    for sr in exposition.sources:
        if sr.reference_source == reference_source and sr.type_source == type_source:
            # Meme signalement revu : on complete ce qu'on ignorait alors.
            if sr.source_id is None and source_id is not None:
                sr.source_id = source_id
            if sr.date_publication is None and date_publication is not None:
                sr.date_publication = date_publication
            return False

    session.add(SourceReference(
        exposition_id=exposition.id,
        source_id=source_id,
        type_source=type_source,
        reference_source=reference_source,
        date_publication=date_publication,
    ))
    return True


def _charger_categories(session, categorie_ids) -> list:
    """Categories correspondant aux identifiants, dans l'ordre fourni."""
    if not categorie_ids:
        return []
    trouvees = {
        c.id: c for c in session.query(Categorie).filter(Categorie.id.in_(categorie_ids))
    }
    return [trouvees[i] for i in dict.fromkeys(categorie_ids) if i in trouvees]


def enregistrer_exposition(
    session,
    nom_entite: str,
    categorie_ids: list,
    type_source: TypeSource,
    reference_source: str,
    criticite: int,
    niveau_criticite: NiveauCriticite,
    nombre_enregistrements: int = None,
    type_entite=None,
    source_id: str = None,
    date_publication=None,
) -> tuple:
    """
    Point d'entree principal FR-12 : enregistre une detection en
    deduppliquant si un incident correspondant existe deja.

    Retourne un tuple (exposition, est_nouvelle, ancienne_criticite) :
    - exposition : l'Exposition (nouvelle ou existante mise a jour)
    - est_nouvelle : True si l'exposition vient d'etre creee
    - ancienne_criticite : la criticite AVANT mise a jour (None si
      nouvelle exposition) - utile pour detecter une hausse significative
      (cf FR-25/FR-26, alerte de confirmation)
    """
    categories = _charger_categories(session, categorie_ids)
    exposition_existante = _trouver_exposition_existante(session, nom_entite)

    if exposition_existante:
        ancienne_criticite = exposition_existante.criticite

        exposition_existante.date_derniere_detection = utc_now()

        if _ajouter_reference(session, exposition_existante, type_source,
                              reference_source, source_id, date_publication):
            logger.info(
                f"[FR-12] Nouvelle SourceReference ajoutee a l'exposition existante '{nom_entite}'."
            )
        else:
            logger.info("[FR-12] Reference de source deja presente, aucun doublon ajoute.")

        # Progression MONOTONE : une redetection partielle (moins de
        # selecteurs visibles sur cette source-la) ne doit pas faire
        # retomber une exposition deja qualifiee comme critique.
        if criticite > exposition_existante.criticite:
            exposition_existante.criticite = criticite
            exposition_existante.niveau_criticite = niveau_criticite

        # Categories : UNION, jamais de retrait - meme logique monotone.
        # Une source peut ne citer que la banque la ou une autre citait
        # aussi le ministere : l'exposition releve des deux.
        for categorie in categories:
            if categorie not in exposition_existante.categories:
                exposition_existante.categories.append(categorie)

        # On garde la date de publication la plus RECENTE connue : elle
        # traduit la derniere activite constatee autour de l'incident.
        if date_publication is not None and (
            exposition_existante.date_publication_source is None
            or date_publication > exposition_existante.date_publication_source
        ):
            exposition_existante.date_publication_source = date_publication

        session.commit()
        return exposition_existante, False, ancienne_criticite

    # Aucun incident correspondant : creation d'une nouvelle Exposition
    nouvelle_exposition = Exposition(
        nom_entite=nom_entite,
        type_entite=type_entite,
        categories=categories,
        nombre_enregistrements_revendique=nombre_enregistrements,
        criticite=criticite,
        niveau_criticite=niveau_criticite,
        date_publication_source=date_publication,
    )
    session.add(nouvelle_exposition)
    session.flush()

    _ajouter_reference(session, nouvelle_exposition, type_source,
                       reference_source, source_id, date_publication)
    session.commit()

    logger.info(
        f"[FR-12] Nouvelle exposition creee : '{nom_entite}' "
        f"({', '.join(c.nom for c in categories) or 'sans categorie'})."
    )
    return nouvelle_exposition, True, None
