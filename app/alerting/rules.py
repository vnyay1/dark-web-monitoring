"""
FR-25/FR-26 - Determination des canaux d'alerte selon le score de
confiance et la priorite sectorielle.

Les seuils sont desormais lus depuis la configuration systeme (modifiable
par admin/super_admin), plutot que fixes en dur dans le code.
"""

from app.models import CanalAlerte
from app.config_system import get_config_float

SECTEURS_PRIORITAIRES = [
    "finance", "banque", "telecommunications", "telecom",
    "administration publique", "gouvernement",
]


def est_secteur_prioritaire(exposition) -> bool:
    """FR-26 - Determine si l'exposition concerne un secteur prioritaire."""
    secteur = (exposition.secteur_activite or "").lower()
    nom = (exposition.nom_entite or "").lower()

    if ".gov.cm" in nom:
        return True

    return any(mot in secteur for mot in SECTEURS_PRIORITAIRES)


def determiner_canaux(exposition) -> list:
    """
    FR-25/FR-26 - Retourne la liste des canaux a utiliser pour une
    exposition donnee, selon son score de confiance et sa priorite
    sectorielle.
    """
    seuil_critique = get_config_float("seuil_alerte_critique")
    seuil_eleve = get_config_float("seuil_alerte_eleve")

    score = exposition.score_confiance
    prioritaire = est_secteur_prioritaire(exposition)

    canaux = [CanalAlerte.INTERFACE]

    if score >= seuil_critique:
        canaux.append(CanalAlerte.EMAIL)
        canaux.append(CanalAlerte.SMS)
        if prioritaire:
            canaux.append(CanalAlerte.WHATSAPP)
    elif score >= seuil_eleve:
        canaux.append(CanalAlerte.EMAIL)
        if prioritaire:
            canaux.append(CanalAlerte.SMS)
    else:
        canaux.append(CanalAlerte.EMAIL)

    return canaux