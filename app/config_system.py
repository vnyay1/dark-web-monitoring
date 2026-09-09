"""
Acces centralise a la configuration systeme modifiable (seuils d'alerte,
etc.), stockee en base plutot qu'en dur dans le code.

Valeurs par defaut fournies si la cle n'existe pas encore en base
(premiere execution avant seed).
"""

import logging
from app.db import get_session
from app.models import ConfigurationSysteme

logger = logging.getLogger(__name__)

# Chaque cle declare sa valeur par defaut, sa description (affichee dans
# l'interface d'administration) et son TYPE. Le type est indispensable :
# l'ecran de configuration validait toute valeur par float(), ce qui
# rejetait desormais des reglages legitimes comme
# niveau_alerte_minimum = "moyenne".
VALEURS_PAR_DEFAUT = {
    # --- FR-10 : paliers de criticite (nombre de selecteurs distincts) ---
    "seuil_criticite_moyenne": (
        "2", "Nombre de selecteurs distincts a partir duquel la criticite est MOYENNE", "int",
    ),
    "seuil_criticite_elevee": (
        "3", "Nombre de selecteurs distincts a partir duquel la criticite est ELEVEE", "int",
    ),
    "seuil_criticite_critique": (
        "4", "Nombre de selecteurs distincts a partir duquel la criticite est CRITIQUE", "int",
    ),
    "criticite_minimum_enregistrement": (
        "1", "Nombre de selecteurs en dessous duquel une entree n'est meme pas enregistree en base", "int",
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

    # --- FR-07 : planification ---
    "collecte_heure_min": (
        "0", "Heure la plus tot a laquelle la collecte quotidienne peut se declencher (0-23, UTC)", "int",
    ),
    "collecte_heure_max": (
        "23", "Heure la plus tard a laquelle la collecte quotidienne peut se declencher (0-23, UTC)", "int",
    ),
}

# Paliers acceptes pour les cles de type "niveau", du moins au plus grave.
NIVEAUX_ORDONNES = ("faible", "moyenne", "elevee", "critique")

# Cles retirees lors du passage du score de confiance a la criticite
# (FR-10). Elles sont supprimees de la base au demarrage, sinon l'ecran
# d'administration continuerait a proposer des reglages sans effet.
CLES_OBSOLETES = (
    "seuil_alerte_minimum",
    "seuil_alerte_critique",
    "seuil_alerte_eleve",
    "seuil_hausse_confirmation",
    "seuil_enregistrement_minimum",
)


def type_de_cle(cle: str) -> str:
    """Type declare d'une cle de configuration ("int", "float" ou "niveau")."""
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
        return str(entier)

    if attendu == "float":
        try:
            return str(float(valeur))
        except ValueError:
            raise ValueError("Cette valeur doit etre un nombre.")

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


def get_config_float(cle: str) -> float:
    return float(get_config(cle))


def get_config_int(cle: str) -> int:
    return int(get_config(cle))


def get_config_niveau(cle: str):
    """
    Lit une cle de type "niveau" et renvoie le NiveauCriticite correspondant.

    Import local : app.models importe indirectement ce module, un import
    au niveau du fichier creerait un cycle.
    """
    from app.models import NiveauCriticite

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
    """Insere les valeurs par defaut en base si elles n'existent pas encore."""
    session = get_session()

    for cle, (valeur, description, _type) in VALEURS_PAR_DEFAUT.items():
        existing = session.query(ConfigurationSysteme).filter_by(cle=cle).first()
        if not existing:
            entry = ConfigurationSysteme(cle=cle, valeur=valeur, description=description)
            session.add(entry)

    supprimees = (
        session.query(ConfigurationSysteme)
        .filter(ConfigurationSysteme.cle.in_(CLES_OBSOLETES))
        .delete(synchronize_session=False)
    )
    if supprimees:
        logger.info(f"[config] {supprimees} cle(s) obsolete(s) supprimee(s).")

    session.commit()
    session.close()