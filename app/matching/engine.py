"""
FR-09 - Moteur de correspondance (Matching Engine).

Recherche les selecteurs actifs dans un texte donne, en combinant :
- correspondance exacte
- comparaison insensible a la casse
- comparaison approximative (fuzzy matching) via RapidFuzz

Ne fait AUCUNE ecriture sur disque : opere entierement sur le texte
deja extrait en memoire par les connecteurs (CN-05).
"""

import logging
from dataclasses import dataclass, field
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


# Seuil de similarite (0-100) en-dessous duquel une correspondance floue
# n'est pas retenue. A ajuster empiriquement.
FUZZY_THRESHOLD = 85

# Taille de la fenetre de mots glissante utilisee pour le fuzzy matching
# (evite de comparer le selecteur au texte entier d'un coup, trop couteux
# et peu pertinent - on compare a des segments de longueur comparable).
FUZZY_WINDOW_MARGIN = 3  # mots de marge au-dela de la longueur du selecteur


@dataclass
class MatchResult:
    """Represente une correspondance trouvee entre un selecteur et un texte."""
    selecteur_valeur: str
    selecteur_categorie: str
    type_correspondance: str  # "exact", "insensible_casse", "fuzzy"
    similarite: float  # 100.0 pour exact, score RapidFuzz sinon
    segment_trouve: str  # extrait du texte ayant matche
    position: int  # position approximative dans le texte


def _match_exact(texte: str, selecteur_valeur: str) -> list[MatchResult]:
    """Recherche des occurrences exactes (sensible a la casse) du selecteur."""
    results = []
    start = 0
    while True:
        idx = texte.find(selecteur_valeur, start)
        if idx == -1:
            break
        results.append(MatchResult(
            selecteur_valeur=selecteur_valeur,
            selecteur_categorie="",  # rempli par l'appelant
            type_correspondance="exact",
            similarite=100.0,
            segment_trouve=selecteur_valeur,
            position=idx,
        ))
        start = idx + len(selecteur_valeur)
    return results


def _match_case_insensitive(texte: str, selecteur_valeur: str) -> list[MatchResult]:
    """Recherche des occurrences insensibles a la casse (hors matches deja exacts)."""
    results = []
    texte_lower = texte.lower()
    selecteur_lower = selecteur_valeur.lower()
    start = 0
    while True:
        idx = texte_lower.find(selecteur_lower, start)
        if idx == -1:
            break
        segment_reel = texte[idx: idx + len(selecteur_valeur)]
        # On ne compte pas comme "insensible_casse" si c'est en fait deja
        # une correspondance exacte (meme casse)
        if segment_reel != selecteur_valeur:
            results.append(MatchResult(
                selecteur_valeur=selecteur_valeur,
                selecteur_categorie="",
                type_correspondance="insensible_casse",
                similarite=100.0,
                segment_trouve=segment_reel,
                position=idx,
            ))
        start = idx + len(selecteur_valeur)
    return results


def _match_fuzzy(texte: str, selecteur_valeur: str, threshold: int = FUZZY_THRESHOLD) -> list[MatchResult]:
    """
    Recherche des correspondances approximatives via une fenetre glissante
    de mots, comparee au selecteur avec RapidFuzz (ratio de similarite).
    Capte fautes de frappe, variantes orthographiques, translitterations legeres.
    """
    results = []
    mots = texte.split()
    nb_mots_selecteur = max(len(selecteur_valeur.split()), 1)
    fenetre = nb_mots_selecteur + FUZZY_WINDOW_MARGIN

    seen_positions = set()

    for i in range(len(mots)):
        segment = " ".join(mots[i: i + nb_mots_selecteur])
        if not segment:
            continue

        score = fuzz.ratio(segment.lower(), selecteur_valeur.lower())

        if score >= threshold and segment.lower() != selecteur_valeur.lower():
            # Evite les doublons de position approximative
            position_key = i
            if position_key in seen_positions:
                continue
            seen_positions.add(position_key)

            results.append(MatchResult(
                selecteur_valeur=selecteur_valeur,
                selecteur_categorie="",
                type_correspondance="fuzzy",
                similarite=score,
                segment_trouve=segment,
                position=texte.find(segment) if segment in texte else -1,
            ))

    return results


def match_text_against_selecteur(texte: str, selecteur_valeur: str, selecteur_categorie: str,
                                   enable_fuzzy: bool = True) -> list[MatchResult]:
    """
    Applique les trois niveaux de correspondance pour UN selecteur donne.
    Retourne la liste de toutes les correspondances trouvees, dedupliquees
    par (type_correspondance, position).
    """
    all_matches: list[MatchResult] = []

    all_matches.extend(_match_exact(texte, selecteur_valeur))
    all_matches.extend(_match_case_insensitive(texte, selecteur_valeur))

    if enable_fuzzy:
        all_matches.extend(_match_fuzzy(texte, selecteur_valeur))

    for m in all_matches:
        m.selecteur_categorie = selecteur_categorie

    return all_matches


def match_text_against_catalogue(texte: str, selecteurs: list, enable_fuzzy: bool = True) -> list[MatchResult]:
    """
    Applique le matching pour l'ensemble du catalogue de selecteurs actifs.

    selecteurs : liste d'objets Selecteur (ou tuples (valeur, categorie))
    Retourne toutes les correspondances trouvees, tous selecteurs confondus.
    """
    all_results: list[MatchResult] = []

    for selecteur in selecteurs:
        valeur = selecteur.valeur if hasattr(selecteur, "valeur") else selecteur[0]
        categorie = (
            selecteur.categorie.value
            if hasattr(selecteur, "categorie")
            else selecteur[1]
        )

        matches = match_text_against_selecteur(texte, valeur, categorie, enable_fuzzy=enable_fuzzy)
        all_results.extend(matches)

    logger.info(f"Matching termine : {len(all_results)} correspondance(s) trouvee(s).")
    return all_results