"""
FR-25/FR-26 - Determination des canaux d'alerte selon le score de
confiance et la priorite sectorielle (secteurs .gov.cm, finance,
telecommunications).
"""

from app.models import CanalAlerte

SEUIL_CRITIQUE = 0.85
SEUIL_ELEVE = 0.6
# FR-25/FR-26 - Hausse de score consideree comme "significative" pour
# declencher une alerte de confirmation sur une exposition existante
# (evite le bruit d'une alerte a chaque micro-variation)
SEUIL_HAUSSE_SIGNIFICATIVE = 0.15
# Mots-cles indiquant un secteur prioritaire (FR-26). Bases sur le
# secteur_activite ou le nom de l'entite (ex: domaine .gov.cm).
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
    score = exposition.score_confiance
    prioritaire = est_secteur_prioritaire(exposition)

    canaux = [CanalAlerte.INTERFACE]  # toujours visible dans l'interface

    if score >= SEUIL_CRITIQUE:
        canaux.append(CanalAlerte.EMAIL)
        canaux.append(CanalAlerte.SMS)
        if prioritaire:
            canaux.append(CanalAlerte.WHATSAPP)
    elif score >= SEUIL_ELEVE:
        canaux.append(CanalAlerte.EMAIL)
        if prioritaire:
            canaux.append(CanalAlerte.SMS)
    else:
        canaux.append(CanalAlerte.EMAIL)

    return canaux