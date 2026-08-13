"""
FR-10 - Calcul du score de confiance.

Formule proposee (a valider avec l'encadrant - voir ambiguite 7 du rapport
de suivi). Transparente et ajustable via les poids ci-dessous.

Le score final est compris entre 0.0 et 1.0.

CORRECTIF : deduplication par chevauchement de position ajoutee. Sans elle,
deux selecteurs proches dans le catalogue (ex: "Cameroon" et "Cameroun")
matchant sur le meme mot du texte etaient comptes comme deux correspondances
distinctes, faussant a la baisse la precision moyenne et pouvant faire passer
un score fuzzy au-dessus d'un score exact equivalent.
"""

import logging
from dataclasses import dataclass
from app.models import CategorieSelecteur

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Poids de precision par categorie de selecteur.
# Les selecteurs tres specifiques (nom de banque, domaine .gov.cm) sont
# plus fiables qu'un selecteur generique (nom d'une ville, "Cameroon").
# Valeurs entre 0.0 (peu fiable seul) et 1.0 (tres fiable seul).
# ---------------------------------------------------------------------
PRECISION_PAR_CATEGORIE = {
    CategorieSelecteur.DOMAINE: 0.9,
    CategorieSelecteur.TELEPHONE: 0.85,
    CategorieSelecteur.MINISTERE: 0.85,
    CategorieSelecteur.AGENCE_GOUVERNEMENTALE: 0.85,
    CategorieSelecteur.BANQUE: 0.9,
    CategorieSelecteur.MICROFINANCE: 0.8,
    CategorieSelecteur.TELECOM: 0.8,
    CategorieSelecteur.UNIVERSITE: 0.75,
    CategorieSelecteur.ENTREPRISE: 0.8,
    # Les selecteurs "ville/region" incluent des noms de pays generiques
    # (ex: "Cameroon") qui peuvent apparaitre hors contexte -> poids faible
    CategorieSelecteur.VILLE_REGION: 0.4,
}

DEFAULT_PRECISION = 0.5

# Poids du type de correspondance (exact > insensible casse > fuzzy)
POIDS_TYPE_CORRESPONDANCE = {
    "exact": 1.0,
    "insensible_casse": 0.95,
    "fuzzy": 0.75,  # penalise car moins fiable qu'une correspondance exacte
}

# Poids relatifs des 3 facteurs dans le score final (somme = 1.0)
POIDS_PRECISION_SELECTEUR = 0.5
POIDS_NB_CORRESPONDANCES = 0.3
POIDS_FIABILITE_SOURCE = 0.2

# Palier de saturation pour le facteur "nombre de correspondances"
# (au-dela de ce nombre de selecteurs distincts, le facteur plafonne a 1.0)
SATURATION_NB_SELECTEURS_DISTINCTS = 4


@dataclass
class ScoreDetail:
    score_final: float
    facteur_precision: float
    facteur_nb_correspondances: float
    facteur_fiabilite_source: float
    nb_selecteurs_distincts: int


def _precision_match(m) -> float:
    """Calcule la precision d'une correspondance individuelle (MatchResult)."""
    categorie = m.selecteur_categorie
    if isinstance(categorie, str):
        try:
            categorie = CategorieSelecteur(categorie)
        except ValueError:
            categorie = None

    base = PRECISION_PAR_CATEGORIE.get(categorie, DEFAULT_PRECISION)
    poids_type = POIDS_TYPE_CORRESPONDANCE.get(m.type_correspondance, 0.7)

    if m.type_correspondance == "fuzzy":
        facteur_similarite = m.similarite / 100.0
        return base * poids_type * facteur_similarite

    return base * poids_type


def _deduplicate_overlapping(matches: list) -> list:
    """
    Si plusieurs correspondances se chevauchent sur la meme zone de texte,
    ne garde que celle avec la meilleure precision.

    Evite qu'un meme mot du texte soit compte comme "plusieurs selecteurs
    distincts" a cause de doublons/variantes linguistiques presents dans
    le catalogue (ex: "Cameroon" et "Cameroun" matchant tous deux sur le
    meme mot du texte source).

    Les correspondances avec position == -1 (non localisables, cas rare
    du fuzzy sur un segment reconstruit) sont conservees telles quelles,
    sans logique de chevauchement.
    """
    localisables = [m for m in matches if m.position is not None and m.position >= 0]
    non_localisables = [m for m in matches if m.position is None or m.position < 0]

    scored = [(m, _precision_match(m)) for m in localisables]
    # Tri par position croissante, puis par precision decroissante
    # (en cas d'egalite de position, le plus precis est examine en premier)
    scored.sort(key=lambda x: (x[0].position, -x[1]))

    kept = []
    last_end = -1

    for m, prec in scored:
        start = m.position
        end = start + max(len(m.segment_trouve), 1)
        if start < last_end:
            # Chevauche un match deja retenu et plus precis (ou egal) -> ignore
            continue
        kept.append((m, prec))
        last_end = end

    # Les non-localisables sont ajoutes sans deduplication (best effort)
    kept.extend((m, _precision_match(m)) for m in non_localisables)

    return kept


def _facteur_nb_correspondances(nb_selecteurs_distincts: int) -> float:
    """
    Plus il y a de selecteurs DISTINCTS trouves (pas juste d'occurrences),
    plus la confiance augmente, avec saturation pour eviter qu'un texte
    tres long ne gonfle artificiellement le score.
    """
    if nb_selecteurs_distincts <= 0:
        return 0.0
    ratio = min(nb_selecteurs_distincts / SATURATION_NB_SELECTEURS_DISTINCTS, 1.0)
    return ratio


def _facteur_fiabilite_source(nombre_erreurs: int, nombre_collectes_total: int = None) -> float:
    """
    Fiabilite de la source basee sur son historique d'erreurs (FR-04).
    Si l'historique n'est pas encore disponible (nouvelle source), on
    retourne une fiabilite neutre par defaut.
    """
    if nombre_collectes_total is None or nombre_collectes_total == 0:
        return 0.7  # valeur neutre par defaut pour une source sans historique

    taux_succes = 1.0 - (nombre_erreurs / max(nombre_collectes_total, 1))
    return max(0.0, min(taux_succes, 1.0))


def calculer_score_confiance(matches: list, nombre_erreurs_source: int = 0,
                               nombre_collectes_total_source: int = None) -> ScoreDetail:
    """
    Calcule le score de confiance global pour un ensemble de correspondances
    (MatchResult) trouvees sur UN MEME texte/incident.

    matches : liste de MatchResult (voir engine.py), doit contenir
              selecteur_categorie, type_correspondance, similarite, position

    Applique d'abord une deduplication par chevauchement de position, afin
    que des selecteurs quasi-identiques du catalogue (ex: variantes
    orthographiques d'un meme nom) ne soient pas comptes plusieurs fois
    pour le meme mot du texte source.
    """
    if not matches:
        return ScoreDetail(0.0, 0.0, 0.0, 0.0, 0)

    deduped = _deduplicate_overlapping(matches)

    # En cas de plusieurs matches deduplique portant sur le MEME selecteur
    # (ex: "MINFI" trouve en exact ET en fuzzy a des positions differentes
    # non chevauchantes), on garde la meilleure precision par selecteur.
    meilleur_par_selecteur = {}
    for m, prec in deduped:
        cle = m.selecteur_valeur
        if cle not in meilleur_par_selecteur or prec > meilleur_par_selecteur[cle]:
            meilleur_par_selecteur[cle] = prec

    nb_selecteurs_distincts = len(meilleur_par_selecteur)
    facteur_precision = sum(meilleur_par_selecteur.values()) / nb_selecteurs_distincts

    facteur_nb = _facteur_nb_correspondances(nb_selecteurs_distincts)
    facteur_source = _facteur_fiabilite_source(nombre_erreurs_source, nombre_collectes_total_source)

    score_final = (
        facteur_precision * POIDS_PRECISION_SELECTEUR
        + facteur_nb * POIDS_NB_CORRESPONDANCES
        + facteur_source * POIDS_FIABILITE_SOURCE
    )
    score_final = round(min(max(score_final, 0.0), 1.0), 3)

    return ScoreDetail(
        score_final=score_final,
        facteur_precision=round(facteur_precision, 3),
        facteur_nb_correspondances=round(facteur_nb, 3),
        facteur_fiabilite_source=round(facteur_source, 3),
        nb_selecteurs_distincts=nb_selecteurs_distincts,
    )