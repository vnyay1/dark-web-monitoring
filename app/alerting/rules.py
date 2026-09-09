"""
FR-25/FR-26 - Determination des canaux d'alerte selon la CRITICITE de
l'exposition et la priorite sectorielle.

La criticite (nombre de selecteurs distincts, cf. app.matching.criticite)
remplace l'ancien score de confiance : le routage se fait desormais sur
des paliers nommes plutot que sur des seuils flottants.
"""

from app.models import CanalAlerte, NiveauCriticite

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
    exposition donnee, selon sa criticite et sa priorite sectorielle.

    L'interface recoit TOUTE alerte : c'est la trace consultable par
    l'analyste. Les canaux intrusifs (SMS, WhatsApp) sont reserves aux
    niveaux hauts, et WhatsApp au seul croisement criticite maximale x
    secteur prioritaire.
    """
    niveau = exposition.niveau_criticite
    prioritaire = est_secteur_prioritaire(exposition)

    canaux = [CanalAlerte.INTERFACE]

    if niveau == NiveauCriticite.CRITIQUE:
        canaux.append(CanalAlerte.EMAIL)
        canaux.append(CanalAlerte.SMS)
        if prioritaire:
            canaux.append(CanalAlerte.WHATSAPP)
    elif niveau == NiveauCriticite.ELEVEE:
        canaux.append(CanalAlerte.EMAIL)
        if prioritaire:
            canaux.append(CanalAlerte.SMS)
    elif niveau == NiveauCriticite.MOYENNE:
        canaux.append(CanalAlerte.EMAIL)

    # NiveauCriticite.FAIBLE : interface uniquement. Une seule mention
    # camerounaise dans une annonce ne justifie pas de reveiller une
    # astreinte ; elle reste consultable dans le tableau de bord.

    return canaux
