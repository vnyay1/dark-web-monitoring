"""
Test manuel du Matching Engine (FR-09) + Filtrage faux positifs (FR-11)
+ Scoring (FR-10).
"""

import logging
from app.db import get_session
from app.models import Selecteur
from app.matching.engine import match_text_against_catalogue
from app.matching.exclusion import filtrer_faux_positifs
from app.matching.scoring import calculer_score_confiance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


SAMPLE_TEXTS = [
    "A major bank in Cameroon, Afriland First Bank, has reportedly been breached.",
    "The leak allegedly affects CAMEROON government systems, specifically MINFI.",
    "Sources claim data from Camerooon institutions was exposed, including Afriland Frist Bank.",
    "Countries affected: USA, France, Cameroon, Germany, Brazil - full list of victims.",
    "This leak only concerns companies based in South America and Europe.",
]


def run_test():
    session = get_session()
    selecteurs = session.query(Selecteur).filter_by(actif=True).all()
    print(f"Catalogue charge : {len(selecteurs)} selecteurs actifs.\n")

    for i, texte in enumerate(SAMPLE_TEXTS, start=1):
        print(f"--- Texte {i} ---")
        print(f"Contenu : {texte}")

        results_bruts = match_text_against_catalogue(texte, selecteurs)
        results = filtrer_faux_positifs(texte, results_bruts, session=session)

        if not results:
            statut = "filtre (faux positif)" if results_bruts else "aucune correspondance"
            print(f"Aucune correspondance retenue ({statut}). Score : 0.0\n")
            continue

        for r in results:
            print(f"  [{r.type_correspondance}] '{r.selecteur_valeur}' "
                  f"(cat: {r.selecteur_categorie}) -> '{r.segment_trouve}' "
                  f"(similarite: {r.similarite:.1f})")

        score = calculer_score_confiance(results, nombre_erreurs_source=0, nombre_collectes_total_source=None)
        print(f"  >> SCORE DE CONFIANCE : {score.score_final} "
              f"(precision={score.facteur_precision}, "
              f"nb_selecteurs={score.facteur_nb_correspondances}, "
              f"fiabilite_source={score.facteur_fiabilite_source}, "
              f"nb_distincts={score.nb_selecteurs_distincts})")
        print()

    session.close()


if __name__ == "__main__":
    run_test()