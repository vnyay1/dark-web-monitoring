"""
Acces centralise a la configuration systeme modifiable (seuils d'alerte,
etc.), stockee en base plutot qu'en dur dans le code.

Valeurs par defaut fournies si la cle n'existe pas encore en base
(premiere execution avant seed).
"""

import logging
from app.db import get_session
from app.models import ConfigurationSysteme, NiveauCriticite

logger = logging.getLogger(__name__)

# Chaque cle declare sa valeur par defaut, sa description (affichee dans
# l'interface d'administration) et son TYPE. Le type est indispensable :
# l'ecran de configuration validait toute valeur par float(), ce qui
# rejetait desormais des reglages legitimes comme
# niveau_alerte_minimum = "moyenne".
VALEURS_PAR_DEFAUT = {
    # --- FR-10 : paliers de criticite (score : selecteurs distincts ponderes par leur poids) ---
    "seuil_criticite_moyenne": (
        "2", "Score (selecteurs distincts ponderes par leur poids) a partir duquel la criticite est MOYENNE", "int",
    ),
    "seuil_criticite_elevee": (
        "3", "Score (selecteurs distincts ponderes par leur poids) a partir duquel la criticite est ELEVEE", "int",
    ),
    "seuil_criticite_critique": (
        "4", "Score (selecteurs distincts ponderes par leur poids) a partir duquel la criticite est CRITIQUE", "int",
    ),
    "criticite_minimum_enregistrement": (
        "1", "Score en dessous duquel une entree n'est meme pas enregistree en base", "int",
    ),

    # --- FR-25/FR-26 : alertes ---
    "niveau_alerte_minimum": (
        "moyenne", "Niveau de criticite a partir duquel une alerte est emise (faible/moyenne/elevee/critique)", "niveau",
    ),
    "hausse_criticite_confirmation": (
        "1", "Hausse de criticite minimale declenchant une alerte de confirmation sur une exposition connue", "int",
    ),

    # --- FR-03 : fenetre temporelle de collecte ---
    "periode_collecte_jours": (
        "30", "Anciennete maximale (en jours) des entrees analysees : au-dela, l'entree est ignoree", "int",
    ),

    "pages_listing_max": (
        "10", "Nombre maximum de pages parcourues par source et par cycle (sources paginees)", "int",
    ),

    "sources_en_parallele": (
        "4", "Nombre de sources collectees en meme temps (1 = l'une apres l'autre) ; chacune "
             "garde son delai minimum entre deux requetes", "int",
    ),

    # --- FR-07 : planification ---
    "collecte_heure_min": (
        "0", "Heure la plus tot a laquelle la collecte quotidienne peut se declencher (0-23, UTC)", "int",
    ),
    "collecte_heure_max": (
        "23", "Heure la plus tard a laquelle la collecte quotidienne peut se declencher (0-23, UTC)", "int",
    ),
}

# Paliers acceptes pour les cles de type "niveau", du moins au plus grave
# (ordre de declaration de NiveauCriticite).
NIVEAUX_ORDONNES = tuple(niveau.value for niveau in NiveauCriticite)

# Borne SUPERIEURE par cle "int". Seule la negativite etait refusee, si bien
# qu'un seuil de criticite fixe a 100000 desactivait silencieusement toute
# alerte, et pages_listing_max=100000 transformait un cycle de collecte en
# parcours interminable de la source. Ces valeurs pilotent le comportement
# operationnel : elles meritent un plafond, pas seulement un plancher.
BORNES_MAXIMALES = {
    "seuil_criticite_moyenne": 100,
    "seuil_criticite_elevee": 100,
    "seuil_criticite_critique": 100,
    "criticite_minimum_enregistrement": 100,
    "hausse_criticite_confirmation": 100,
    "periode_collecte_jours": 3650,
    "pages_listing_max": 500,
    "sources_en_parallele": 10,
    "collecte_heure_min": 23,
    "collecte_heure_max": 23,
}


def type_de_cle(cle: str) -> str:
    """Type declare d'une cle de configuration ("int" ou "niveau")."""
    if cle not in VALEURS_PAR_DEFAUT:
        raise KeyError(f"Cle de configuration inconnue : {cle}")
    return VALEURS_PAR_DEFAUT[cle][2]


def valider_valeur(cle: str, valeur: str) -> str:
    """
    Verifie qu'une valeur est acceptable pour cette cle et la renvoie
    normalisee. Leve ValueError sinon (message destine a l'utilisateur).
    """
    valeur = (valeur or "").strip()
    attendu = type_de_cle(cle)

    if attendu == "int":
        try:
            entier = int(valeur)
        except ValueError:
            raise ValueError("Cette valeur doit etre un nombre entier.")
        if entier < 0:
            raise ValueError("Cette valeur ne peut pas etre negative.")

        maximum = BORNES_MAXIMALES.get(cle)
        if maximum is not None and entier > maximum:
            raise ValueError(f"Cette valeur ne peut pas depasser {maximum}.")

        # Coherence croisee : une fenetre de collecte inversee ne leve aucune
        # erreur a l'enregistrement, mais fait echouer le tirage de l'heure
        # au moment de la planification, loin d'ici.
        if cle == "collecte_heure_min" and entier > int(get_config("collecte_heure_max")):
            raise ValueError("L'heure de debut ne peut pas etre posterieure a l'heure de fin.")
        if cle == "collecte_heure_max" and entier < int(get_config("collecte_heure_min")):
            raise ValueError("L'heure de fin ne peut pas etre anterieure a l'heure de debut.")

        return str(entier)

    if attendu == "niveau":
        if valeur.lower() not in NIVEAUX_ORDONNES:
            attendus = ", ".join(NIVEAUX_ORDONNES)
            raise ValueError(f"Valeur attendue parmi : {attendus}.")
        return valeur.lower()

    raise ValueError(f"Type de configuration non gere : {attendu}")


def get_config(cle: str) -> str:
    """Recupere une valeur de configuration, avec repli sur la valeur par defaut."""
    session = get_session()
    entry = session.query(ConfigurationSysteme).filter_by(cle=cle).first()
    session.close()

    if entry:
        return entry.valeur

    if cle in VALEURS_PAR_DEFAUT:
        return VALEURS_PAR_DEFAUT[cle][0]

    raise KeyError(f"Cle de configuration inconnue : {cle}")


def get_config_int(cle: str) -> int:
    return int(get_config(cle))


def get_config_niveau(cle: str):
    """
    Lit une cle de type "niveau" et renvoie le NiveauCriticite correspondant.
    """
    return NiveauCriticite(get_config(cle))


def set_config(cle: str, valeur: str):
    """Met a jour (ou cree) une valeur de configuration."""
    session = get_session()
    entry = session.query(ConfigurationSysteme).filter_by(cle=cle).first()

    if entry:
        entry.valeur = valeur
    else:
        description = VALEURS_PAR_DEFAUT.get(cle, (None, None, None))[1]
        entry = ConfigurationSysteme(cle=cle, valeur=valeur, description=description)
        session.add(entry)

    session.commit()
    session.close()
    logger.info(f"[config] {cle} mis a jour : {valeur}")


def init_config_defaults():
    """
    Insere les valeurs par defaut en base si elles n'existent pas encore.

    Les cles retirees lors du passage a la criticite ne sont plus purgees
    ici : la migration a1c7e3f42b90 les supprime, et init_db() impose que
    la base soit a la derniere revision avant tout demarrage.
    """
    session = get_session()
    try:
        presentes = {cle for (cle,) in session.query(ConfigurationSysteme.cle)}
        for cle, (valeur, description, _type) in VALEURS_PAR_DEFAUT.items():
            if cle not in presentes:
                session.add(ConfigurationSysteme(cle=cle, valeur=valeur, description=description))
        session.commit()
    finally:
        session.close()
    session.close()