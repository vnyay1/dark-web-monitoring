"""
Test manuel de la deduplication FR-12, avec des donnees simulees.
"""

import logging
from app.db import get_session, init_db
from app.models import CategorieFuite, TypeSource, Exposition
from app.matching.deduplication import enregistrer_exposition

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_test():
    init_db()
    session = get_session()

    print("--- Detection 1 : MINFI, source A (ransomware site) ---")
    exp1 = enregistrer_exposition(
        session, nom_entite="MINFI", categorie_fuite=CategorieFuite.CREDENTIALS,
        type_source=TypeSource.RANSOMWARE_SITE, reference_source="http://siteA.onion/leak1",
        score_confiance=0.6, nombre_enregistrements=5000,
    )
    print(f"Exposition id={exp1.id}, sources={len(exp1.sources)}\n")

    print("--- Detection 2 : MINFI (meme incident), source B (forum) ---")
    exp2 = enregistrer_exposition(
        session, nom_entite="MINFI", categorie_fuite=CategorieFuite.CREDENTIALS,
        type_source=TypeSource.FORUM, reference_source="http://forumB.com/thread/42",
        score_confiance=0.75,
    )
    print(f"Exposition id={exp2.id}, sources={len(exp2.sources)}")
    print(f"Deduplication reussie (meme id) : {exp1.id == exp2.id}\n")

    print("--- Detection 3 : entite differente (Afriland First Bank) ---")
    exp3 = enregistrer_exposition(
        session, nom_entite="Afriland First Bank", categorie_fuite=CategorieFuite.DONNEES_FINANCIERES,
        type_source=TypeSource.PASTE, reference_source="http://pasteC.com/raw/xyz",
        score_confiance=0.8,
    )
    print(f"Exposition id={exp3.id}")
    print(f"Nouvelle exposition distincte : {exp3.id != exp1.id}\n")

    total = session.query(Exposition).count()
    print(f"Total expositions en base : {total} (attendu selon l'etat prealable de la base : +2 par rapport a avant ce test)")

    session.close()


if __name__ == "__main__":
    run_test()