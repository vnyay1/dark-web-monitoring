"""
FR-25/FR-26 - Determination des canaux d'alerte selon la CRITICITE de
l'exposition et la priorite sectorielle.

La priorite sectorielle se lit sur les CATEGORIES de l'exposition (celles
des selecteurs trouves, cf. Categorie.prioritaire) : le champ texte
secteur_activite qu'on consultait auparavant n'etait jamais renseigne, si
bien que seul le domaine .gov.cm declenchait les canaux renforces.

La criticite (nombre de selecteurs distincts, cf. app.matching.criticite)
remplace l'ancien score de confiance : le routage se fait desormais sur
des paliers nommes plutot que sur des seuils flottants.
"""

from app.models import CanalAlerte, NiveauCriticite

def est_prioritaire(exposition) -> bool:
    """
    FR-26 - L'exposition concerne-t-elle un secteur prioritaire ? Oui si
    l'une de ses categories est marquee prioritaire par l'administrateur,
    ou si l'entite est un domaine gouvernemental.
    """
    if ".gov.cm" in (exposition.nom_entite or "").lower():
        return True
    return any(categorie.prioritaire for categorie in exposition.categories)


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
    prioritaire = est_prioritaire(exposition)

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
