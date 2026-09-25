"""
FR-11 - Filtrage des faux positifs connus.

Deux mecanismes complementaires :
1. Regle structurelle "liste de pays" : un nom de lieu generique entoure
   d'autres noms de pays signe un en-tete recapitulatif plutot qu'un
   contenu reellement lie au Cameroun
2. Liste d'exclusion tenue par les analystes (table ExclusionFauxPositif),
   pour les cas specifiques identifies au fil de l'usage reel du systeme

Une regle de la liste porte un TYPE - elle confronte son motif au nom
d'entite retenu pour l'entree, ou au texte de l'annonce - et une PORTEE :
toutes les sources, ou une seule. Un en-tete recurrent propre a une source
n'a aucune raison d'aveugler la detection sur les autres.

Ce fichier est le SEUL lecteur de la table : c'est le point d'audit unique
de FR-11, celui ou l'on verifie ce que le systeme s'autorise a ignorer.
Une regle n'est jamais retroactive - elle ecarte des entrees a l'analyse,
elle n'efface ni ne declasse une exposition deja enregistree.
"""

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Regle structurelle : detection de "liste de pays / victimes"
# ---------------------------------------------------------------------

# Echantillon de noms de pays frequemment cites dans des en-tetes de leak
# sites (listes de victimes multi-pays). Volontairement large et generique,
# pas specifique au Cameroun.
AUTRES_PAYS_COURANTS = [
    "usa", "united states", "france", "germany", "brazil", "india", "china",
    "russia", "uk", "united kingdom", "italy", "spain", "canada", "japan",
    "australia", "mexico", "nigeria", "south africa", "egypt", "kenya",
    "ghana", "senegal", "ivory coast", "gabon", "chad", "congo",
]

# Nombre minimum d'autres pays devant apparaitre a proximite pour
# considerer qu'on est dans un "en-tete de liste de victimes"
SEUIL_AUTRES_PAYS_PROXIMITE = 2

# Fenetre de caracteres autour du match consideree comme "proximite"
FENETRE_PROXIMITE_CARACTERES = 150


# Noms de pays cherches comme MOTS ENTIERS. En simple sous-chaine, "uk"
# etait trouve dans "Ukraine" ou "duke", "usa" dans "usage", "india" dans
# "indian", "chad" dans "Chadwick" : un "Cameroun" parfaitement legitime
# pouvait etre rejete comme s'il figurait dans une liste de pays.
MOTIFS_PAYS = {
    pays: re.compile(r"(?<!\w)" + re.escape(pays) + r"(?!\w)")
    for pays in AUTRES_PAYS_COURANTS
}


def _pays_a_proximite(texte: str, position: int, segment_trouve: str) -> list:
    """Autres noms de pays presents dans la fenetre de proximite du match."""
    debut = max(0, position - FENETRE_PROXIMITE_CARACTERES)
    fin = min(len(texte), position + len(segment_trouve) + FENETRE_PROXIMITE_CARACTERES)
    contexte = texte[debut:fin].lower()

    return [pays for pays, motif in MOTIFS_PAYS.items() if motif.search(contexte)]


# ---------------------------------------------------------------------
# Application des regles structurelles
# ---------------------------------------------------------------------

def motif_rejet_structurel(texte: str, m):
    """
    Motif pour lequel une regle structurelle ecarte ce match, ou None s'il
    est retenu. Expose pour la reconnaissance (phase correspondance), qui
    doit dire POURQUOI un selecteur n'a pas compte.

    Il n'y a plus de regle "cm dans un mot" : elle rejetait tout ".cm"
    precede d'une lettre, c'est-a-dire tout vrai domaine ("camtel.cm"), et
    les frontieres de mot du moteur (app.matching.engine) couvrent deja un
    "cm" colle a un mot.
    """
    if m.position is None or m.position < 0:
        return None

    # La regle "liste de pays" ne s'applique qu'aux noms de lieux
    # generiques. Elle suit l'indicateur de la categorie, et non plus son
    # nom : les categories sont renommables par l'administrateur.
    if m.categorie_lieu_generique:
        pays = _pays_a_proximite(texte, m.position, m.segment_trouve)
        if len(pays) >= SEUIL_AUTRES_PAYS_PROXIMITE:
            return f"contexte de liste de pays/victimes detecte ({', '.join(pays)})"

    return None


def appliquer_regles_structurelles(texte: str, matches: list) -> list:
    """
    Filtre une liste de MatchResult en appliquant les regles structurelles
    generiques. Retourne uniquement les matches consideres pertinents.
    """
    filtered = []

    for m in matches:
        motif = motif_rejet_structurel(texte, m)
        if motif:
            logger.info(f"[FR-11] Rejet '{m.segment_trouve}' : {motif}")
            continue
        filtered.append(m)

    return filtered


# ---------------------------------------------------------------------
# Liste d'exclusion tenue par les analystes (base de donnees)
# ---------------------------------------------------------------------

def _regles_applicables(session, type_exclusion, source_id):
    """
    Regles ACTIVES du type demande qui valent pour cette source : celles
    sans portee (toutes les sources) et celles portant sur elle.

    Une source inconnue (source_id None, cas de la reconnaissance qui
    rejoue une analyse hors collecte) ne voit que les regles generales :
    rien ne dit a quelle source rattacher l'entree.
    """
    from app.models import ExclusionFauxPositif

    regles = (
        session.query(ExclusionFauxPositif)
        .filter(ExclusionFauxPositif.actif.is_(True))
        .filter(ExclusionFauxPositif.type_exclusion == type_exclusion)
        .all()
    )

    return [
        regle for regle in regles
        if regle.source_id is None or regle.source_id == source_id
    ]


def _premier_motif_correspondant(regles, valeur: str):
    """
    Motif de la premiere regle qui correspond a cette valeur, ou None.

    Un motif invalide est IGNORE plutot que fatal : une regex cassee ne
    doit pas interrompre une collecte. L'API la refuse deja a
    l'enregistrement (re.compile), le cas ne se produit donc qu'avec une
    ligne ecrite directement en base.
    """
    for regle in regles:
        try:
            if re.search(regle.motif, valeur, re.IGNORECASE):
                logger.info(
                    f"[FR-11] Ecarte par la regle '{regle.motif}' "
                    f"({regle.type_exclusion.value}, ajoutee par {regle.ajoute_par})"
                )
                return regle.motif
        except re.error:
            logger.warning(f"[FR-11] Motif d'exclusion invalide (regex), ignore : '{regle.motif}'")
            continue

    return None


def appliquer_liste_exclusion(texte: str, session, source_id=None) -> bool:
    """
    Verifie si le texte correspond a un motif d'exclusion enregistre par
    les analystes (table ExclusionFauxPositif). Le champ "motif" est
    traite comme une expression reguliere simple pour permettre une
    certaine flexibilite (ex: motif = "en-tete.*pays" pour capter un
    pattern recurrent observe sur une source donnee).

    Retourne True si le texte doit etre exclu (faux positif connu).
    """
    return motif_exclusion_configuree(texte, session, source_id) is not None


def motif_exclusion_configuree(texte: str, session, source_id=None):
    """Motif de la liste d'exclusion qui ecarte ce TEXTE, ou None."""
    from app.models import TypeExclusion

    regles = _regles_applicables(session, TypeExclusion.TEXTE, source_id)

    return _premier_motif_correspondant(regles, texte)


def motif_exclusion_entite(nom_entite, session, source_id=None):
    """
    Motif de la liste d'exclusion qui ecarte ce NOM D'ENTITE, ou None.

    Couvre le faux positif le plus courant, qu'aucune regle structurelle
    ne peut deviner : une societe etrangere dont le nom contient un
    selecteur ("Cameroon Holdings Ltd"), qui revient a chaque publication.
    """
    from app.models import TypeExclusion

    if not nom_entite:
        return None

    regles = _regles_applicables(session, TypeExclusion.ENTITE, source_id)

    return _premier_motif_correspondant(regles, nom_entite)


def filtrer_faux_positifs(texte: str, matches: list, session=None, source_id=None) -> list:
    """
    Point d'entree principal FR-11 : applique successivement les regles
    structurelles puis, si une session DB est fournie, les regles de type
    TEXTE de la liste tenue par les analystes.

    Les regles de type ENTITE ne s'appliquent PAS ici : le nom d'entite
    n'est arrete qu'une fois les matches filtres (cf. app.pipeline).
    """
    matches_filtres = appliquer_regles_structurelles(texte, matches)

    if session is not None and appliquer_liste_exclusion(texte, session, source_id):
        logger.info("[FR-11] Texte entierement exclu par la liste de faux positifs.")
        return []

    return matches_filtres