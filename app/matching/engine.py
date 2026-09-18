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

PERFORMANCE - le moteur tourne sur CHAQUE annonce collectee, contre tout
le catalogue (~380 selecteurs), et un texte de detail peut compter 3 000
mots. Les pretraitements du texte (minuscules, mots, fenetres de mots) ne
dependent pas du selecteur : ils sont faits UNE fois par texte
(_ContexteTexte) au lieu d'une fois par selecteur, et la comparaison
approximative passe par rapidfuzz.process.extract, qui boucle en C.
"""

import re
import logging
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


FUZZY_THRESHOLD = 85

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
    selecteur_categorie: str  # identifiant de la Categorie du selecteur
    type_correspondance: str  # "exact", "insensible_casse", "fuzzy"
    similarite: float  # 100.0 pour exact, score RapidFuzz sinon
    segment_trouve: str  # extrait du texte ayant matche
    position: int  # position approximative dans le texte
    # Le selecteur est un nom de lieu generique (cf. Categorie.lieu_generique) :
    # la regle "liste de pays" de app.matching.exclusion s'y applique.
    categorie_lieu_generique: bool = False
    # Poids du selecteur dans la criticite (cf. Selecteur.poids).
    selecteur_poids: int = 1


class _ContexteTexte:
    """
    Pretraitements d'UN texte, partages par tous les selecteurs du
    catalogue. Les fenetres de mots sont construites a la demande, une
    fois par taille (1 mot, 2 mots...), puis gardees.
    """

    def __init__(self, texte: str):
        self.texte = texte
        self.texte_lower = texte.lower()
        self.mots = texte.split()
        self._fenetres = {}

    def fenetres(self, nb_mots: int) -> tuple:
        """(segments, segments en minuscules) de nb_mots mots consecutifs."""
        if nb_mots not in self._fenetres:
            segments = [
                " ".join(self.mots[i: i + nb_mots]) for i in range(len(self.mots))
            ]
            self._fenetres[nb_mots] = (segments, [s.lower() for s in segments])
        return self._fenetres[nb_mots]


def _est_selecteur_court(selecteur_valeur: str) -> bool:
    """Determine si un selecteur necessite une verification de mot entier."""
    return len(selecteur_valeur) <= SEUIL_LONGUEUR_MOT_ENTIER


@lru_cache(maxsize=None)
def _pattern_mot_entier(selecteur_valeur: str) -> re.Pattern:
    """
    Regex exigeant une VRAIE frontiere de mot autour d'un selecteur court,
    SENSIBLE a la casse : espace, debut/fin de chaine ou ponctuation de
    phrase - mais PAS un tiret, qui laisserait passer "state-of-the-art"
    pour le selecteur "ART".

    Lookaround (?<!...) / (?!...) plutot que \\b, car \\b considere le
    tiret comme une frontiere valide. Compilee une seule fois par
    selecteur : le catalogue est le meme pour toutes les annonces.
    """
    escaped = re.escape(selecteur_valeur)
    return re.compile(r"(?<![A-Za-z0-9\-])" + escaped + r"(?![A-Za-z0-9\-])")


def _match_exact(texte: str, selecteur_valeur: str) -> list[MatchResult]:
    """Recherche des occurrences exactes (sensible a la casse) du selecteur."""
    results = []

    if _est_selecteur_court(selecteur_valeur):
        for m in _pattern_mot_entier(selecteur_valeur).finditer(texte):
            results.append(MatchResult(
                selecteur_valeur=selecteur_valeur,
                selecteur_categorie="",
                type_correspondance="exact",
                similarite=100.0,
                segment_trouve=m.group(),
                position=m.start(),
            ))
        return results

    # Selecteur long : recherche de sous-chaine
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


def _match_case_insensitive(texte: str, selecteur_valeur: str,
                            texte_lower: str = None) -> list[MatchResult]:
    """
    Recherche des occurrences insensibles a la casse (hors matches deja
    exacts).

    CORRECTIF : desactive pour les selecteurs courts (<= 6 caracteres).
    Les acronymes institutionnels camerounais (ART, CCA, MINFI, ANTIC...)
    s'ecrivent toujours en MAJUSCULES dans un contexte reel de reference
    a l'entite - jamais en minuscules ou casse mixte. L'insensibilite a
    la casse sur ces selecteurs courts capturait massivement des faux
    positifs (le mot anglais "art" dans "state-of-the-art", l'abreviation
    juridique "Art." dans les references d'articles de loi/reglement,
    etc.) meme avec la frontiere de mot stricte deja en place. Les
    selecteurs courts ne sont donc plus detectes QUE sous leur forme
    exacte en majuscules (via _match_exact), jamais en minuscules ou
    casse mixte.
    """
    if _est_selecteur_court(selecteur_valeur):
        return []

    # Selecteur long : sous-chaine insensible a la casse
    results = []
    if texte_lower is None:
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


def _match_fuzzy(texte: str, selecteur_valeur: str, threshold: int = FUZZY_THRESHOLD,
                 contexte: _ContexteTexte = None) -> list[MatchResult]:
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

    contexte = contexte or _ContexteTexte(texte)
    nb_mots_selecteur = max(len(selecteur_valeur.split()), 1)
    segments, segments_lower = contexte.fenetres(nb_mots_selecteur)
    selecteur_lower = selecteur_valeur.lower()

    # Tous les segments au-dessus du seuil, calcules en C. Tries ensuite
    # par position dans le texte : l'ordre des resultats compte (le premier
    # selecteur trouve sert de nom d'entite de repli dans le pipeline).
    trouves = sorted(
        process.extract(
            selecteur_lower, segments_lower,
            scorer=fuzz.ratio, score_cutoff=threshold, limit=None,
        ),
        key=lambda resultat: resultat[2],
    )

    results = []
    for segment_lower, score, index in trouves:
        # Identique au selecteur : deja couvert par exact/insensible_casse.
        if segment_lower == selecteur_lower:
            continue
        segment = segments[index]
        results.append(MatchResult(
            selecteur_valeur=selecteur_valeur,
            selecteur_categorie="",
            type_correspondance="fuzzy",
            similarite=score,
            segment_trouve=segment,
            position=texte.find(segment),
        ))

    return results


def match_text_against_selecteur(texte: str, selecteur_valeur: str, selecteur_categorie: str,
                                   enable_fuzzy: bool = True,
                                   lieu_generique: bool = False,
                                   contexte: _ContexteTexte = None,
                                   poids: int = 1) -> list[MatchResult]:
    """
    Applique les trois niveaux de correspondance pour UN selecteur donne.
    Retourne la liste de toutes les correspondances trouvees.

    contexte : pretraitements du texte, partages entre selecteurs par
    match_text_against_catalogue ; construit ici s'il n'est pas fourni.
    """
    contexte = contexte or _ContexteTexte(texte)
    all_matches: list[MatchResult] = []

    all_matches.extend(_match_exact(texte, selecteur_valeur))
    all_matches.extend(_match_case_insensitive(texte, selecteur_valeur, contexte.texte_lower))

    if enable_fuzzy:
        all_matches.extend(_match_fuzzy(texte, selecteur_valeur, contexte=contexte))

    for m in all_matches:
        m.selecteur_categorie = selecteur_categorie
        m.categorie_lieu_generique = lieu_generique
        m.selecteur_poids = poids

    return all_matches


def match_text_against_catalogue(texte: str, selecteurs: list, enable_fuzzy: bool = True) -> list[MatchResult]:
    """
    Applique le matching pour l'ensemble du catalogue de selecteurs actifs.

    selecteurs : liste d'objets Selecteur, charges AVEC leur categorie
    (joinedload, sinon une requete par selecteur), ou tuples
    (valeur, categorie_id[, lieu_generique[, poids]]) pour les tests.
    Retourne toutes les correspondances trouvees, tous selecteurs confondus.
    """
    contexte = _ContexteTexte(texte)
    all_results: list[MatchResult] = []

    for selecteur in selecteurs:
        if hasattr(selecteur, "valeur"):
            valeur = selecteur.valeur
            categorie = selecteur.categorie_id
            lieu_generique = bool(selecteur.categorie and selecteur.categorie.lieu_generique)
            poids = selecteur.poids or 1
        else:
            valeur, categorie = selecteur[0], selecteur[1]
            lieu_generique = bool(selecteur[2]) if len(selecteur) > 2 else False
            poids = selecteur[3] if len(selecteur) > 3 else 1

        matches = match_text_against_selecteur(
            texte, valeur, categorie,
            enable_fuzzy=enable_fuzzy, lieu_generique=lieu_generique,
            contexte=contexte, poids=poids,
        )
        all_results.extend(matches)

    # Une ligne par annonce analysee : niveau DEBUG, sinon elle noie le
    # journal d'un cycle de plusieurs centaines d'annonces.
    logger.debug(f"Matching termine : {len(all_results)} correspondance(s) trouvee(s).")
    return all_results
