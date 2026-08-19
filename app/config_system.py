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

VALEURS_PAR_DEFAUT = {
    "seuil_alerte_minimum": ("0.6", "Score minimum pour declencher une alerte (FR-25)"),
    "seuil_alerte_critique": ("0.85", "Score a partir duquel WhatsApp/SMS sont declenches en plus de l'email"),
    "seuil_alerte_eleve": ("0.6", "Score a partir duquel SMS est declenche en plus de l'email"),
    "seuil_hausse_confirmation": ("0.15", "Hausse de score minimale pour declencher une alerte de confirmation sur une exposition existante"),
}


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


def set_config(cle: str, valeur: str):
    """Met a jour (ou cree) une valeur de configuration."""
    session = get_session()
    entry = session.query(ConfigurationSysteme).filter_by(cle=cle).first()

    if entry:
        entry.valeur = valeur
    else:
        description = VALEURS_PAR_DEFAUT.get(cle, (None, None))[1]
        entry = ConfigurationSysteme(cle=cle, valeur=valeur, description=description)
        session.add(entry)

    session.commit()
    session.close()
    logger.info(f"[config] {cle} mis a jour : {valeur}")


def init_config_defaults():
    """Insere les valeurs par defaut en base si elles n'existent pas encore."""
    session = get_session()

    for cle, (valeur, description) in VALEURS_PAR_DEFAUT.items():
        existing = session.query(ConfigurationSysteme).filter_by(cle=cle).first()
        if not existing:
            entry = ConfigurationSysteme(cle=cle, valeur=valeur, description=description)
            session.add(entry)

    session.commit()
    session.close()