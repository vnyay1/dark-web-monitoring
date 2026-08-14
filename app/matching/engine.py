"""
FR-09 - Moteur de correspondance (Matching Engine).

Recherche les selecteurs actifs dans un texte donne, en combinant :
- correspondance exacte
- comparaison insensible a la casse
- comparaison approximative (fuzzy matching) via RapidFuzz

Ne fait AUCUNE ecriture sur disque : opere entierement sur le texte
deja extrait en memoire par les connecteurs (CN-05).

CORRECTIF MAJEUR : les selecteurs courts (acronymes type "ART", "MINAT")
matchaient comme simples sous-chaines, capturant des mots anglais
courants ("Artificial", "start-of-the-art", "co-educational, multi-
denominational"). Une verification de FRONTIERE DE MOT est desormais
appliquee pour tout selecteur de longueur <= SEUIL_LONGUEUR_MOT_ENTIER,
afin de n'accepter que des correspondances sur des mots complets/isoles.
"""

import re
import logging
from dataclasses import dataclass
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


FUZZY_THRESHOLD = 85
FUZZY_WINDOW_MARGIN = 3

# En-dessous (ou egal) de cette longueur de caracteres, un selecteur est
# considere "court" et DOIT correspondre a un mot entier isole (frontiere
# de mot), jamais a une simple sous-chaine a l'interieur d'un mot plus
# long. Evite les faux positifs massifs de type "ART" trouve dans
# "Artificial" ou "start-of-the-art".
SEUIL_LONGUEUR_MOT_ENTIER = 6


@dataclass
class MatchResult:
    """Represente une correspondance trouvee entre un selecteur et un texte."""
    selecteur_valeur: str
    selecteur_categorie: str
    type_correspondance: str  # "exact", "insensible_casse", "fuzzy"
    similarite: float  # 100.0 pour exact, score RapidFuzz sinon
    segment_trouve: str  # extrait du texte ayant matche
    position: int  # position approximative dans le texte


def _est_selecteur_court(selecteur_valeur: str) -> bool:
    """Determine si un selecteur necessite une verification de mot entier."""
    return len(selecteur_valeur) <= SEUIL_LONGUEUR_MOT_ENTIER


def _construire_pattern_mot_entier(selecteur_valeur: str) -> re.Pattern:
    """
    Construit une regex exigeant une VRAIE frontiere de mot pour un
    selecteur court : espace, debut/fin de chaine, ou ponctuation de
    phrase (. , ; : ! ?) - mais PAS un tiret ou une apostrophe, qui
    laisseraient passer des faux positifs comme "state-of-the-art"
    matchant le selecteur "ART".

    On utilise des lookaround (?<!...) / (?!...) plutot que \\b, car \\b
    considere le tiret comme une frontiere valide, ce qui est insuffisant
    ici.
    """
    escaped = re.escape(selecteur_valeur)
    # Le caractere avant ne doit pas etre une lettre, un chiffre, ni un tiret
    # Le caractere apres ne doit pas etre une lettre, un chiffre, ni un tiret
    pattern = r"(?<![A-Za-z0-9\-])" + escaped + r"(?![A-Za-z0-9\-])"
    return re.compile(pattern, re.IGNORECASE)


def _match_exact(texte: str, selecteur_valeur: str) -> list[MatchResult]:
    """Recherche des occurrences exactes (sensible a la casse) du selecteur."""
    results = []

    if _est_selecteur_court(selecteur_valeur):
        escaped = re.escape(selecteur_valeur)
        pattern = re.compile(r"(?<![A-Za-z0-9\-])" + escaped + r"(?![A-Za-z0-9\-])")
        for m in pattern.finditer(texte):
            results.append(MatchResult(
                selecteur_valeur=selecteur_valeur,
                selecteur_categorie="",
                type_correspondance="exact",
                similarite=100.0,
                segment_trouve=m.group(),
                position=m.start(),
            ))
        return results

    # Selecteur long : comportement precedent (recherche de sous-chaine)
    start = 0
    while True:
        idx = texte.find(selecteur_valeur, start)
        if idx == -1:
            break
        results.append(MatchResult(
            selecteur_valeur=selecteur_valeur,
            selecteur_categorie="",
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

    if _est_selecteur_court(selecteur_valeur):
        # Selecteur court : frontiere de mot obligatoire, insensible a la casse
        pattern = _construire_pattern_mot_entier(selecteur_valeur)
        for m in pattern.finditer(texte):
            segment_reel = m.group()
            if segment_reel != selecteur_valeur:  # exclut les vrais matches exacts
                results.append(MatchResult(
                    selecteur_valeur=selecteur_valeur,
                    selecteur_categorie="",
                    type_correspondance="insensible_casse",
                    similarite=100.0,
                    segment_trouve=segment_reel,
                    position=m.start(),
                ))
        return results

    # Selecteur long : comportement precedent (sous-chaine insensible a la casse)
    texte_lower = texte.lower()
    selecteur_lower = selecteur_valeur.lower()
    start = 0
    while True:
        idx = texte_lower.find(selecteur_lower, start)
        if idx == -1:
            break
        segment_reel = texte[idx: idx + len(selecteur_valeur)]
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

    Le fuzzy matching compare deja des MOTS complets (segments issus de
    texte.split()), donc il n'est pas sujet au meme probleme de sous-chaine
    que exact/insensible_casse - un selecteur court y reste cependant
    naturellement plus sujet a des faux positifs de similarite (ex: "ART"
    vs un mot de 3 lettres proche), donc on l'exclut du fuzzy si trop court.
    """
    if _est_selecteur_court(selecteur_valeur):
        # Le fuzzy matching sur un selecteur de 2-6 caracteres genere trop
        # de faux positifs (trop de mots courts lui ressemblent a 85%+).
        # On le desactive pour ces selecteurs - ils restent couverts par
        # exact/insensible_casse avec frontiere de mot, ce qui est deja
        # strict et suffisant pour un acronyme.
        return []

    results = []
    mots = texte.split()
    nb_mots_selecteur = max(len(selecteur_valeur.split()), 1)

    seen_positions = set()

    for i in range(len(mots)):
        segment = " ".join(mots[i: i + nb_mots_selecteur])
        if not segment:
            continue

        score = fuzz.ratio(segment.lower(), selecteur_valeur.lower())

        if score >= threshold and segment.lower() != selecteur_valeur.lower():
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
    Retourne la liste de toutes les correspondances trouvees.
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