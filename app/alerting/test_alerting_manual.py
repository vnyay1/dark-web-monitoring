"""
Test manuel du systeme d'alertes (FR-25/FR-26), avec les senders mockes.
Couvre : nouvelle exposition, mise a jour mineure (pas d'alerte), et
confirmation par hausse significative du score.
"""

import logging
from app.db import get_session
from app.models import Exposition, CategorieFuite, TypeEntite, StatutExposition, TypeSource
from app.matching.deduplication import enregistrer_exposition
from app.alerting.dispatcher import declencher_alertes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_test():
    session = get_session()

    print("\n=== Cas 1 : nouvelle exposition, gov.cm, score 0.92 ===")
    exp1, est_nouvelle1, ancien_score1 = enregistrer_exposition(
        session=session,
        nom_entite="portal.gov.cm",
        categorie_fuite=CategorieFuite.CREDENTIALS,
        type_source=TypeSource.RANSOMWARE_SITE,
        reference_source="http://siteA.onion/leak1",
        score_confiance=0.92,
        secteur_activite="Administration publique",
    )
    alertes1 = declencher_alertes(session, exp1, est_nouvelle=est_nouvelle1, ancien_score=ancien_score1)
    print(f"est_nouvelle={est_nouvelle1} | Canaux declenches : {[a.canal.value for a in alertes1]}")

    print("\n=== Cas 2 : meme entite, nouvelle source, score IDENTIQUE (mise a jour mineure) ===")
    exp2, est_nouvelle2, ancien_score2 = enregistrer_exposition(
        session=session,
        nom_entite="portal.gov.cm",
        categorie_fuite=CategorieFuite.CREDENTIALS,
        type_source=TypeSource.FORUM,
        reference_source="http://forumB.com/thread/1",
        score_confiance=0.92,
    )
    alertes2 = declencher_alertes(session, exp2, est_nouvelle=est_nouvelle2, ancien_score=ancien_score2)
    print(f"est_nouvelle={est_nouvelle2} | ancien_score={ancien_score2} | Canaux declenches : {[a.canal.value for a in alertes2]} (attendu : aucun, hausse insuffisante)")

    print("\n=== Cas 3 : meme entite, nouvelle source, score EN FORTE HAUSSE (confirmation) ===")
    exp3, est_nouvelle3, ancien_score3 = enregistrer_exposition(
        session=session,
        nom_entite="Universite Test",
        categorie_fuite=CategorieFuite.DONNEES_PERSONNELLES,
        type_source=TypeSource.PASTE,
        reference_source="http://pasteC.com/1",
        score_confiance=0.55,
        secteur_activite="Education",
    )
    alertes3a = declencher_alertes(session, exp3, est_nouvelle=est_nouvelle3, ancien_score=ancien_score3)
    print(f"Premiere creation, score 0.55 (sous le seuil 0.6) | Canaux : {[a.canal.value for a in alertes3a]} (attendu : aucun)")

    # Nouvelle source sur la meme entite, score qui grimpe fortement
    exp3b, est_nouvelle3b, ancien_score3b = enregistrer_exposition(
        session=session,
        nom_entite="Universite Test",
        categorie_fuite=CategorieFuite.DONNEES_PERSONNELLES,
        type_source=TypeSource.FORUM,
        reference_source="http://forumD.com/2",
        score_confiance=0.78,
    )
    alertes3b = declencher_alertes(session, exp3b, est_nouvelle=est_nouvelle3b, ancien_score=ancien_score3b)
    print(f"Mise a jour, score 0.55 -> 0.78 (hausse 0.23) | Canaux : {[a.canal.value for a in alertes3b]} (attendu : email, car hausse significative)")

    session.close()


if __name__ == "__main__":
    run_test()