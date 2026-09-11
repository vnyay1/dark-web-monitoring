"""
Test manuel du systeme d'alertes (FR-25/FR-26), avec les senders mockes.

Couvre : nouvelle exposition, mise a jour sans gain de criticite (aucune
alerte attendue), et confirmation par hausse de criticite.

Le routage repose desormais sur la CRITICITE (nombre de selecteurs
camerounais distincts) et non plus sur un score flottant ; la priorite
sectorielle, sur les categories marquees prioritaires.

Usage : python -m app.alerting.test_alerting_manual
"""

import logging

from app.db import get_session
from app.models import Categorie, TypeSource
from app.matching.criticite import niveau_pour
from app.matching.deduplication import enregistrer_exposition
from app.alerting.dispatcher import declencher_alertes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _enregistrer(session, nom, type_source, reference, criticite, categorie=None):
    """Raccourci : la criticite pilote le niveau, comme dans le pipeline."""
    trouvee = session.query(Categorie).filter_by(nom=categorie).first() if categorie else None
    return enregistrer_exposition(
        session=session,
        nom_entite=nom,
        categorie_ids=[trouvee.id] if trouvee else [],
        type_source=type_source,
        reference_source=reference,
        criticite=criticite,
        niveau_criticite=niveau_pour(criticite),
    )


def run_test():
    session = get_session()

    print("\n=== Cas 1 : nouvelle exposition, gov.cm, 4 selecteurs (CRITIQUE) ===")
    exp1, nouvelle1, ancienne1 = _enregistrer(
        session, "portal.gov.cm",
        TypeSource.RANSOMWARE_SITE, "http://siteA.onion/leak1", 4,
        categorie="Ministère",
    )
    alertes1 = declencher_alertes(session, exp1, est_nouvelle=nouvelle1,
                                  ancienne_criticite=ancienne1)
    print(f"est_nouvelle={nouvelle1} | Canaux : {[a.canal.value for a in alertes1]}")
    print("  attendu : interface, email, sms, whatsapp (.gov.cm, categorie prioritaire)")

    print("\n=== Cas 2 : meme entite, nouvelle source, criticite IDENTIQUE ===")
    exp2, nouvelle2, ancienne2 = _enregistrer(
        session, "portal.gov.cm",
        TypeSource.FORUM, "http://forumB.com/thread/1", 4,
    )
    alertes2 = declencher_alertes(session, exp2, est_nouvelle=nouvelle2,
                                  ancienne_criticite=ancienne2)
    print(f"est_nouvelle={nouvelle2} | ancienne_criticite={ancienne2} | "
          f"Canaux : {[a.canal.value for a in alertes2]}")
    print("  attendu : aucun (pas de gain de criticite)")

    print("\n=== Cas 3 : criticite sous le niveau minimum, puis hausse ===")
    exp3, nouvelle3, ancienne3 = _enregistrer(
        session, "Universite Test",
        TypeSource.PASTE, "http://pasteC.com/1", 1,
        categorie="Université",
    )
    alertes3 = declencher_alertes(session, exp3, est_nouvelle=nouvelle3,
                                  ancienne_criticite=ancienne3)
    print(f"Creation avec 1 selecteur (FAIBLE) | Canaux : {[a.canal.value for a in alertes3]}")
    print("  attendu : aucun (sous niveau_alerte_minimum = moyenne)")

    exp3b, nouvelle3b, ancienne3b = _enregistrer(
        session, "Universite Test",
        TypeSource.FORUM, "http://forumD.com/2", 3,
    )
    alertes3b = declencher_alertes(session, exp3b, est_nouvelle=nouvelle3b,
                                   ancienne_criticite=ancienne3b)
    print(f"Mise a jour 1 -> 3 selecteurs (ELEVEE) | "
          f"Canaux : {[a.canal.value for a in alertes3b]}")
    print("  attendu : interface, email (confirmation)")

    print(f"\nSources rattachees a '{exp3b.nom_entite}' : {len(exp3b.sources)} (attendu : 2)")

    session.close()


if __name__ == "__main__":
    run_test()
