"""
FR-08 - Seed initial du catalogue de selecteurs.

Ce script peuple la table Selecteur avec un echantillon representatif.
Les selecteurs concernant les ministeres utilisent les noms d'INSTITUTIONS
(stables), jamais les noms de ministres (personnes physiques, changeants,
et hors-sujet - CN-04 interdit tout nom de personne).

Cette liste est un POINT DE DEPART a valider/completer avec l'encadrant.
Le catalogue reste configurable (FR-08) : ajouter un selecteur ne
necessite qu'une insertion en base, aucune modification de code.
"""

import logging
from app.db import get_session, init_db
from app.models import Selecteur, CategorieSelecteur

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


SEED_SELECTEURS = [
    # --- Domaines ---
    (".cm", CategorieSelecteur.DOMAINE),
    (".gov.cm", CategorieSelecteur.DOMAINE),

    # --- Telephone ---
    ("+237", CategorieSelecteur.TELEPHONE),

    # --- Ministeres (noms d'institutions, jamais de noms de personnes - CN-04) ---
    ("Ministere des Finances", CategorieSelecteur.MINISTERE),
    ("MINFI", CategorieSelecteur.MINISTERE),
    ("Ministere de la Sante Publique", CategorieSelecteur.MINISTERE),
    ("MINSANTE", CategorieSelecteur.MINISTERE),
    ("Ministere de l'Administration Territoriale", CategorieSelecteur.MINISTERE),
    ("MINAT", CategorieSelecteur.MINISTERE),
    ("Ministere des Postes et Telecommunications", CategorieSelecteur.MINISTERE),
    ("MINPOSTEL", CategorieSelecteur.MINISTERE),
    ("Ministere de l'Enseignement Superieur", CategorieSelecteur.MINISTERE),
    ("MINESUP", CategorieSelecteur.MINISTERE),

    # --- Agences gouvernementales ---
    ("ANTIC", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ART", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),  # Agence de Regulation des Telecommunications
    ("CENADI", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CAMTEL", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    # --- Banques (echantillon a valider/completer) ---
    ("Afriland First Bank", CategorieSelecteur.BANQUE),
    ("BICEC", CategorieSelecteur.BANQUE),
    ("SGC Cameroun", CategorieSelecteur.BANQUE),
    ("UBA Cameroun", CategorieSelecteur.BANQUE),
    ("Ecobank Cameroun", CategorieSelecteur.BANQUE),

    # --- Microfinance (echantillon a valider/completer) ---
    ("Express Union", CategorieSelecteur.MICROFINANCE),
    ("CamCCUL", CategorieSelecteur.MICROFINANCE),

    # --- Telecoms ---
    ("MTN Cameroon", CategorieSelecteur.TELECOM),
    ("Orange Cameroun", CategorieSelecteur.TELECOM),
    ("Camtel", CategorieSelecteur.TELECOM),
    ("Nexttel", CategorieSelecteur.TELECOM),

    # --- Universites (echantillon a valider/completer) ---
    ("Universite de Yaounde I", CategorieSelecteur.UNIVERSITE),
    ("Universite de Douala", CategorieSelecteur.UNIVERSITE),
    ("Universite de Buea", CategorieSelecteur.UNIVERSITE),
    ("Universite de Dschang", CategorieSelecteur.UNIVERSITE),

    # --- Entreprises (echantillon a valider/completer) ---
    ("SONARA", CategorieSelecteur.ENTREPRISE),
    ("ENEO Cameroun", CategorieSelecteur.ENTREPRISE),
    ("Camair-Co", CategorieSelecteur.ENTREPRISE),

    # --- Villes et regions ---
    ("Yaounde", CategorieSelecteur.VILLE_REGION),
    ("Douala", CategorieSelecteur.VILLE_REGION),
    ("Bafoussam", CategorieSelecteur.VILLE_REGION),
    ("Garoua", CategorieSelecteur.VILLE_REGION),
    ("Bamenda", CategorieSelecteur.VILLE_REGION),
    ("Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Cameroun", CategorieSelecteur.VILLE_REGION),
]


def seed():
    init_db()
    session = get_session()

    added_count = 0
    skipped_count = 0

    for valeur, categorie in SEED_SELECTEURS:
        existing = session.query(Selecteur).filter_by(valeur=valeur, categorie=categorie).first()
        if existing:
            skipped_count += 1
            continue

        selecteur = Selecteur(
            valeur=valeur,
            categorie=categorie,
            actif=True,
            propose_par_ner=False,
            valide_par_analyste=True,
        )
        session.add(selecteur)
        added_count += 1

    session.commit()
    logger.info(f"Seed termine : {added_count} selecteurs ajoutes, {skipped_count} deja presents.")
    session.close()


if __name__ == "__main__":
    seed()