"""
Test manuel du systeme d'alertes (FR-25/FR-26), avec les senders mockes.
"""

import logging
from app.db import get_session
from app.models import Exposition, CategorieFuite, TypeEntite, StatutExposition, utc_now
from app.alerting.dispatcher import declencher_alertes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_test():
    session = get_session()

    # Cas 1 : score critique + secteur prioritaire (gov.cm) -> tous canaux
    exp1 = Exposition(
        nom_entite="portal.gov.cm",
        secteur_activite="Administration publique",
        type_entite=TypeEntite.PUBLIQUE,
        categorie_fuite=CategorieFuite.CREDENTIALS,
        score_confiance=0.92,
        statut=StatutExposition.NEW,
    )
    session.add(exp1)
    session.flush()

    # Cas 2 : score eleve, secteur standard -> email seulement
    exp2 = Exposition(
        nom_entite="Universite Test",
        secteur_activite="Education",
        type_entite=TypeEntite.PUBLIQUE,
        categorie_fuite=CategorieFuite.DONNEES_PERSONNELLES,
        score_confiance=0.65,
        statut=StatutExposition.NEW,
    )
    session.add(exp2)
    session.flush()

    # Cas 3 : score faible -> aucune alerte (sous le seuil)
    exp3 = Exposition(
        nom_entite="Entite peu fiable",
        secteur_activite="Divers",
        type_entite=TypeEntite.PRIVEE,
        categorie_fuite=CategorieFuite.NON_PRECISEE,
        score_confiance=0.3,
        statut=StatutExposition.NEW,
    )
    session.add(exp3)
    session.flush()

    session.commit()

    print("\n--- Cas 1 : gov.cm, score 0.92 ---")
    alertes1 = declencher_alertes(session, exp1)
    print(f"Canaux declenches : {[a.canal.value for a in alertes1]}")

    print("\n--- Cas 2 : Universite, score 0.65 ---")
    alertes2 = declencher_alertes(session, exp2)
    print(f"Canaux declenches : {[a.canal.value for a in alertes2]}")

    print("\n--- Cas 3 : score 0.3 (sous le seuil) ---")
    alertes3 = declencher_alertes(session, exp3)
    print(f"Canaux declenches : {[a.canal.value for a in alertes3]} (attendu : aucun)")

    session.close()


if __name__ == "__main__":
    run_test()