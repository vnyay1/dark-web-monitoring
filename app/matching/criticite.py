"""
FR-10 - Criticite d'une exposition.

Remplace l'ancien score de confiance (app/matching/scoring.py, supprime).

POURQUOI CE CHANGEMENT - le score etait un flottant 0-1 issu de trois
facteurs ponderes (precision du selecteur, nombre de correspondances,
fiabilite de la source). Deux problemes :

  1. Un des trois facteurs etait mort : le pipeline passait toujours
     nombre_collectes_total_source=None, donc _facteur_fiabilite_source()
     retournait sa constante neutre 0.7. 20% du score etait figé.
  2. Surtout, un "0.72" n'est pas defendable devant un analyste : il
     fallait relire le code pour savoir d'ou il venait.

La criticite repond a une question verifiable a l'oeil nu : COMBIEN de
selecteurs DISTINCTS du catalogue camerounais apparaissent dans cette
entree ? Une annonce citant "MINFI", "CAMTEL" et "Douala" est plus
surement une exposition camerounaise qu'une annonce n'en citant qu'un.

Les paliers sont regles par l'administrateur (app.config_system), pas
figes ici : le bon reglage depend du bruit reel des sources, qui ne se
connait qu'a l'usage.

POIDS - tous les selecteurs ne se valent pas : "Cameroun" dans une annonce
en dit plus qu'un acronyme de trois lettres. L'administrateur peut donc
donner a un selecteur un poids superieur a 1 (Selecteur.poids, il est
alors "prioritaire"). La criticite enregistree est le SCORE : la somme des
poids des selecteurs distincts. Tant que tous les poids valent 1, le score
est exactement le nombre de selecteurs distincts d'avant.
"""

import logging
from dataclasses import dataclass, field

from app.config_system import get_config_int
from app.models import NiveauCriticite

logger = logging.getLogger(__name__)


@dataclass
class CriticiteDetail:
    """Resultat du calcul, pour UNE entree analysee."""

    nb_selecteurs: int
    niveau: NiveauCriticite
    # Somme des poids des selecteurs distincts : c'est la criticite
    # enregistree et comparee aux paliers.
    score: int = 0
    # Valeurs des selecteurs distincts trouves, pour le log et la console
    # de supervision.
    selecteurs: list = field(default_factory=list)
    # Un dict par selecteur distinct (valeur, categorie_id, poids,
    # occurrences, niveaux de correspondance) : c'est ce qui est enregistre
    # sur le signalement et affiche dans le detail de l'exposition. Des
    # termes du CATALOGUE, jamais un segment du texte analyse.
    details: list = field(default_factory=list)
    # Ceux d'entre eux dont le poids depasse 1.
    prioritaires: list = field(default_factory=list)
    # Identifiants des categories de ces selecteurs : elles deviennent les
    # categories de l'exposition (FR-13).
    categories: list = field(default_factory=list)

    def resume(self) -> str:
        """Libelle court destine aux logs et aux messages d'alerte."""
        pluriel = "s" if self.nb_selecteurs > 1 else ""
        compte = f"{self.nb_selecteurs} selecteur{pluriel}"
        if self.prioritaires:
            nb = len(self.prioritaires)
            compte = f"score {self.score} : {compte} dont {nb} prioritaire{'s' if nb > 1 else ''}"
        return f"{self.niveau.value.upper()} ({compte})"


def _paliers() -> tuple:
    """
    Seuils lus depuis la configuration systeme, dans l'ordre croissant.

    Ils sont tries defensivement : l'interface d'administration laisse
    saisir trois entiers independants, rien n'empeche un reglage
    incoherent (critique < elevee) qui rendrait un palier inatteignable.
    """
    moyenne = get_config_int("seuil_criticite_moyenne")
    elevee = get_config_int("seuil_criticite_elevee")
    critique = get_config_int("seuil_criticite_critique")
    return tuple(sorted((moyenne, elevee, critique)))


def niveau_pour(score: int) -> NiveauCriticite:
    """Traduit un score (selecteurs distincts ponderes) en palier."""
    moyenne, elevee, critique = _paliers()

    if score >= critique:
        return NiveauCriticite.CRITIQUE
    if score >= elevee:
        return NiveauCriticite.ELEVEE
    if score >= moyenne:
        return NiveauCriticite.MOYENNE
    return NiveauCriticite.FAIBLE


def calculer_criticite(matches: list) -> CriticiteDetail:
    """
    Calcule la criticite pour l'ensemble des correspondances trouvees sur
    UNE meme entree.

    matches : liste de MatchResult (cf. app.matching.engine). Le moteur
    emet un MatchResult par OCCURRENCE : "MINFI" cite trois fois donne
    trois resultats. On deduplique donc sur selecteur_valeur, sinon une
    annonce repetant un seul nom paraitrait aussi critique qu'une annonce
    en citant trois differents.

    Chaque selecteur distinct compte pour son poids. Une meme valeur peut
    figurer dans deux categories ("Republic of Cameroon") : elle ne compte
    qu'une fois, pour le plus grand de ses poids.
    """
    if not matches:
        return CriticiteDetail(nb_selecteurs=0, niveau=NiveauCriticite.FAIBLE)

    # Dictionnaire plutot que set() : conserve l'ordre de decouverte, ce
    # qui rend les logs reproductibles et lisibles.
    par_valeur = {}
    for m in matches:
        detail = par_valeur.setdefault(m.selecteur_valeur, {
            "valeur": m.selecteur_valeur,
            "categorie_id": m.selecteur_categorie,
            "poids": 0,
            "occurrences": 0,
            "correspondances": {},
        })
        if (m.selecteur_poids or 1) > detail["poids"]:
            detail["poids"] = m.selecteur_poids or 1
            detail["categorie_id"] = m.selecteur_categorie
        detail["occurrences"] += 1
        niveaux = detail["correspondances"]
        niveaux[m.type_correspondance] = niveaux.get(m.type_correspondance, 0) + 1

    distincts = list(par_valeur)
    score = sum(d["poids"] for d in par_valeur.values())

    return CriticiteDetail(
        nb_selecteurs=len(distincts),
        niveau=niveau_pour(score),
        score=score,
        selecteurs=distincts,
        details=list(par_valeur.values()),
        prioritaires=[valeur for valeur in distincts if par_valeur[valeur]["poids"] > 1],
        categories=list(dict.fromkeys(
            m.selecteur_categorie for m in matches if m.selecteur_categorie
        )),
    )
