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
    # Valeurs des selecteurs distincts trouves. Sert au log et a la console
    # de supervision ; n'est JAMAIS persistee (CN-03).
    selecteurs: list = field(default_factory=list)
    # Identifiants des categories de ces selecteurs : elles deviennent les
    # categories de l'exposition (FR-13).
    categories: list = field(default_factory=list)

    def resume(self) -> str:
        """Libelle court destine aux logs et aux messages d'alerte."""
        pluriel = "s" if self.nb_selecteurs > 1 else ""
        return f"{self.niveau.value.upper()} ({self.nb_selecteurs} selecteur{pluriel})"


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


def niveau_pour(nb_selecteurs: int) -> NiveauCriticite:
    """Traduit un nombre de selecteurs distincts en palier."""
    moyenne, elevee, critique = _paliers()

    if nb_selecteurs >= critique:
        return NiveauCriticite.CRITIQUE
    if nb_selecteurs >= elevee:
        return NiveauCriticite.ELEVEE
    if nb_selecteurs >= moyenne:
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
    """
    if not matches:
        return CriticiteDetail(nb_selecteurs=0, niveau=NiveauCriticite.FAIBLE)

    # dict.fromkeys plutot que set() : conserve l'ordre de decouverte,
    # ce qui rend les logs reproductibles et lisibles.
    distincts = list(dict.fromkeys(m.selecteur_valeur for m in matches))

    return CriticiteDetail(
        nb_selecteurs=len(distincts),
        niveau=niveau_pour(len(distincts)),
        selecteurs=distincts,
        categories=list(dict.fromkeys(
            m.selecteur_categorie for m in matches if m.selecteur_categorie
        )),
    )
