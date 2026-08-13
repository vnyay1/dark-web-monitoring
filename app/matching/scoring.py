"""
FR-10 - Calcul du score de confiance.

Formule proposee (a valider avec l'encadrant - voir ambiguite 7 du rapport
de suivi). Transparente et ajustable via les poids ci-dessous.

Le score final est compris entre 0.0 et 1.0.
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


def _precision_selecteur(categorie: CategorieSelecteur, type_correspondance: str, similarite: float) -> float:
    """
    Calcule la precision d'une correspondance individuelle en combinant :
    - le poids de precision de la categorie du selecteur
    - le poids du type de correspondance (exact/insensible/fuzzy)
    - pour le fuzzy, la similarite reelle (0-100) vient encore moduler le score
    """
    base = PRECISION_PAR_CATEGORIE.get(categorie, DEFAULT_PRECISION)
    poids_type = POIDS_TYPE_CORRESPONDANCE.get(type_correspondance, 0.7)

    if type_correspondance == "fuzzy":
        # Une similarite de 85% (seuil minimum) pese moins qu'une similarite de 99%
        facteur_similarite = similarite / 100.0
        return base * poids_type * facteur_similarite

    return base * poids_type


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
              selecteur_categorie, type_correspondance, similarite
    """
    if not matches:
        return ScoreDetail(0.0, 0.0, 0.0, 0.0, 0)

    # Precision moyenne des correspondances trouvees (le meilleur match
    # par selecteur distinct est retenu pour eviter qu'un meme selecteur
    # trouve 10 fois ne fausse la moyenne)
    meilleur_par_selecteur = {}
    for m in matches:
        cle = m.selecteur_valeur
        precision = _precision_selecteur(
            categorie=m.selecteur_categorie if isinstance(m.selecteur_categorie, CategorieSelecteur)
            else CategorieSelecteur(m.selecteur_categorie) if m.selecteur_categorie else None,
            type_correspondance=m.type_correspondance,
            similarite=m.similarite,
        ) if m.selecteur_categorie else DEFAULT_PRECISION

        if cle not in meilleur_par_selecteur or precision > meilleur_par_selecteur[cle]:
            meilleur_par_selecteur[cle] = precision

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