"""
FR-12 - Deduplication des expositions detectees sur plusieurs sources.

Regle d'identite proposee (a valider avec l'encadrant si possible - aucune
formule n'est donnee dans le cahier des charges) : deux detections sont
considerees comme LE MEME incident si :
  1. Le nom d'entite est identique ou tres similaire (fuzzy)
  2. La premiere detection existante date de moins de FENETRE_JOURS jours
Les categories ne sont pas un critere : elles sont reunies (cf.
enregistrer_exposition).

Si une correspondance est trouvee : la date de derniere detection est mise
a jour, et une nouvelle SourceReference est ajoutee sans creer de nouvelle
Exposition. Sinon, une nouvelle Exposition est creee.
"""

import logging
from datetime import timedelta
from rapidfuzz import fuzz

from app.conservation import conserver_selecteurs, conserver_texte
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
                       source_id, date_publication, texte_brut=None,
                       selecteurs=None, noms_categories=None):
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
            conserver_texte(sr, texte_brut)
            conserver_selecteurs(sr, selecteurs, noms_categories or {})
            return False

    reference = SourceReference(
        exposition_id=exposition.id,
        source_id=source_id,
        type_source=type_source,
        reference_source=reference_source,
        date_publication=date_publication,
    )
    conserver_texte(reference, texte_brut)
    conserver_selecteurs(reference, selecteurs, noms_categories or {})
    session.add(reference)
    return True


def _actualiser(exposition, categories, criticite, niveau_criticite, date_publication):
    """
    Met a jour une exposition connue apres une nouvelle lecture de son
    incident. Tout y est MONOTONE : criticite, categories, date de
    publication ne font que progresser.
    """
    exposition.date_derniere_detection = utc_now()

    # Progression MONOTONE : une redetection partielle (moins de
    # selecteurs visibles sur cette source-la) ne doit pas faire
    # retomber une exposition deja qualifiee comme critique.
    if criticite > exposition.criticite:
        exposition.criticite = criticite
        exposition.niveau_criticite = niveau_criticite

    # Categories : UNION, jamais de retrait - meme logique monotone.
    # Une source peut ne citer que la banque la ou une autre citait
    # aussi le ministere : l'exposition releve des deux.
    for categorie in categories:
        if categorie not in exposition.categories:
            exposition.categories.append(categorie)

    # On garde la date de publication la plus RECENTE connue : elle
    # traduit la derniere activite constatee autour de l'incident.
    if date_publication is not None and (
        exposition.date_publication_source is None
        or date_publication > exposition.date_publication_source
    ):
        exposition.date_publication_source = date_publication


def completer_signalements(session, signalements, categorie_ids, criticite,
                           niveau_criticite, date_publication, texte_brut,
                           selecteurs) -> list:
    """
    Complete des signalements DEJA ENREGISTRES avec une lecture complete de
    leur annonce (cf. app.conservation, "completion") : texte, selecteurs,
    et exposition actualisee comme a toute redetection.

    Contrairement a enregistrer_exposition(), l'exposition n'est pas
    retrouvee par son NOM (rapprochement flou, limite a FENETRE_JOURS) mais
    par le signalement lui-meme : completer une annonce ancienne ne doit ni
    creer une exposition en double, ni la rattacher a un autre incident.

    Retourne [(exposition, ancienne_criticite)], pour les alertes.
    """
    categories = _charger_categories(session, categorie_ids)
    noms_categories = {c.id: c.nom for c in categories}

    resultats = []
    for signalement in signalements:
        exposition = signalement.exposition
        ancienne_criticite = exposition.criticite
        conserver_texte(signalement, texte_brut)
        conserver_selecteurs(signalement, selecteurs, noms_categories)
        if signalement.date_publication is None and date_publication is not None:
            signalement.date_publication = date_publication
        _actualiser(exposition, categories, criticite, niveau_criticite, date_publication)
        resultats.append((exposition, ancienne_criticite))

    session.commit()
    return resultats


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
    source_id: str = None,
    date_publication=None,
    texte_brut: str = None,
    selecteurs: list = None,
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

    texte_brut : texte COMPLET et DEJA MASQUE a conserver sur le
    signalement (cf. app.conservation), None si l'entree n'a ete lue que
    sur son titre.
    selecteurs : CriticiteDetail.details, enregistres sur le signalement.
    """
    categories = _charger_categories(session, categorie_ids)
    noms_categories = {c.id: c.nom for c in categories}
    exposition_existante = _trouver_exposition_existante(session, nom_entite)

    if exposition_existante:
        ancienne_criticite = exposition_existante.criticite

        if _ajouter_reference(session, exposition_existante, type_source,
                              reference_source, source_id, date_publication, texte_brut,
                              selecteurs, noms_categories):
            logger.info(
                f"[FR-12] Nouvelle SourceReference ajoutee a l'exposition existante '{nom_entite}'."
            )
        else:
            logger.info("[FR-12] Reference de source deja presente, aucun doublon ajoute.")

        _actualiser(exposition_existante, categories, criticite, niveau_criticite, date_publication)

        session.commit()
        return exposition_existante, False, ancienne_criticite

    # Aucun incident correspondant : creation d'une nouvelle Exposition
    nouvelle_exposition = Exposition(
        nom_entite=nom_entite,
        categories=categories,
        criticite=criticite,
        niveau_criticite=niveau_criticite,
        date_publication_source=date_publication,
    )
    session.add(nouvelle_exposition)
    session.flush()

    _ajouter_reference(session, nouvelle_exposition, type_source,
                       reference_source, source_id, date_publication, texte_brut,
                       selecteurs, noms_categories)
    session.commit()

    logger.info(
        f"[FR-12] Nouvelle exposition creee : '{nom_entite}' "
        f"({', '.join(c.nom for c in categories) or 'sans categorie'})."
    )
    return nouvelle_exposition, True, None
