"""
FR-13 - Categorisation automatique de la fuite detectee.

Approche par mots-cles indicateurs : chaque categorie possede une liste de
termes frequemment associes a ce type de fuite dans les annonces de leak
sites / forums. Le texte est scanne (insensible a la casse) et la
categorie avec le plus de correspondances est retenue.

Si aucun mot-cle ne matche, la categorie "NON_PRECISEE" est utilisee
(valeur par defaut du modele, cf FR-13 : "Categorie non precisee").

Ce module ne fait QUE de la categorisation textuelle indicative - il ne
remplace pas la validation finale par un analyste (FR-21, changement de
statut manuel).
"""

import logging
from app.models import CategorieFuite

logger = logging.getLogger(__name__)


MOTS_CLES_PAR_CATEGORIE = {
    CategorieFuite.CREDENTIALS: [
        "credentials", "login", "password", "passwords", "username",
        "combo list", "combolist", "auth", "authentication", "access token",
        "api key", "session token",
    ],
    CategorieFuite.DONNEES_PERSONNELLES: [
        "personal data", "personally identifiable", "pii", "full name",
        "date of birth", "national id", "passport", "address", "customer data",
        "user records", "citizens data",
    ],
    CategorieFuite.DONNEES_FINANCIERES: [
        "financial data", "bank account", "credit card", "card number",
        "iban", "swift", "transaction", "payment data", "invoice",
        "financial records", "banking",
    ],
    CategorieFuite.DONNEES_SANTE: [
        "medical record", "health data", "patient data", "diagnosis",
        "healthcare", "hospital records", "medical history", "clinical data",
    ],
    CategorieFuite.DOCUMENTS_INTERNES: [
        "internal documents", "confidential", "internal memo", "contract",
        "internal report", "internal files", "proprietary documents",
        "internal communication",
    ],
    CategorieFuite.CODE_SOURCE: [
        "source code", "repository", "codebase", "github", "gitlab",
        "proprietary code", "api source", "software code",
    ],
}


def categoriser_texte(texte: str) -> tuple[CategorieFuite, dict]:
    """
    Determine la categorie de fuite la plus probable a partir du texte.

    Retourne un tuple (categorie, details) ou details contient le nombre
    de mots-cles trouves par categorie, utile pour la tracabilite/debug.
    """
    texte_lower = texte.lower()
    scores_par_categorie = {}

    for categorie, mots_cles in MOTS_CLES_PAR_CATEGORIE.items():
        nb_trouves = sum(1 for mot in mots_cles if mot in texte_lower)
        if nb_trouves > 0:
            scores_par_categorie[categorie] = nb_trouves

    if not scores_par_categorie:
        return CategorieFuite.NON_PRECISEE, {}

    categorie_retenue = max(scores_par_categorie, key=scores_par_categorie.get)

    logger.info(
        f"[FR-13] Categorisation : {categorie_retenue.value} "
        f"(scores: { {c.value: n for c, n in scores_par_categorie.items()} })"
    )

    return categorie_retenue, {c.value: n for c, n in scores_par_categorie.items()}