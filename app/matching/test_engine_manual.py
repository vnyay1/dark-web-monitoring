"""
Test manuel du Matching Engine (FR-09), avec des donnees simulees.
Ne touche a aucune vraie source - sert uniquement a valider la logique.
"""

import logging
from app.db import get_session
from app.models import Selecteur
from app.matching.engine import match_text_against_catalogue

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


SAMPLE_TEXTS = [
    # Cas 1 : correspondance exacte evidente
    "A major bank in Cameroon, Afriland First Bank, has reportedly been breached.",

    # Cas 2 : variante de casse
    "The leak allegedly affects CAMEROON government systems, specifically MINFI.",

    # Cas 3 : faute de frappe / variante orthographique (fuzzy)
    "Sources claim data from Camerooon institutions was exposed, including Afriland Frist Bank.",

    # Cas 4 : faux positif potentiel (a filtrer plus tard par FR-11)
    "Countries affected: USA, France, Cameroon, Germany, Brazil - full list of victims.",

    # Cas 5 : aucune correspondance attendue
    "This leak only concerns companies based in South America and Europe.",
]


def run_test():
    session = get_session()
    selecteurs = session.query(Selecteur).filter_by(actif=True).all()
    print(f"Catalogue charge : {len(selecteurs)} selecteurs actifs.\n")

    for i, texte in enumerate(SAMPLE_TEXTS, start=1):
        print(f"--- Texte {i} ---")
        print(f"Contenu : {texte}")
        results = match_text_against_catalogue(texte, selecteurs)

        if not results:
            print("Aucune correspondance.\n")
            continue

        for r in results:
            print(f"  [{r.type_correspondance}] '{r.selecteur_valeur}' "
                  f"(cat: {r.selecteur_categorie}) -> trouve: '{r.segment_trouve}' "
                  f"(similarite: {r.similarite:.1f})")
        print()

    session.close()


if __name__ == "__main__":
    run_test()