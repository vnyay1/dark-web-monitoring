"""
Test manuel de la journalisation FR-17, integree au flux collect().
"""

import logging
from app.db import get_session, init_db
from app.models import JournalAudit, Source, TypeSource
from app.connectors.example_connector import ExampleConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class FailingConnector(ExampleConnector):
    """Variante qui echoue volontairement, pour tester la journalisation d'echec."""
    SOURCE_NAME = "failing_test_source"

    def fetch(self):
        raise ConnectionError("Simulation d'echec de connexion pour test FR-17")


def run_test():
    init_db()
    session = get_session()

    # Cree une Source de test en base pour lier les entrees d'audit
    source = Source(
        nom="Source de test FR-17",
        type_source=TypeSource.TEST_CLAIRNET,
        url_ou_identifiant="https://example.com/test",
    )
    session.add(source)
    session.commit()

    print("--- Collecte reussie ---")
    connector_ok = ExampleConnector(db_session=session, source_id=source.id)
    result_ok = connector_ok.collect()
    print(f"Resultat : success={result_ok['success']}\n")

    print("--- Collecte en echec ---")
    connector_fail = FailingConnector(db_session=session, source_id=source.id)
    result_fail = connector_fail.collect()
    print(f"Resultat : success={result_fail['success']}\n")

    print("--- Contenu du journal d'audit pour cette source ---")
    entries = session.query(JournalAudit).filter_by(source_id=source.id).all()
    for e in entries:
        print(f"  [{e.horodatage}] resultat={e.resultat.value} details={e.details}")

    print(f"\nTotal entrees journalisees : {len(entries)} (attendu : 2)")

    session.close()


if __name__ == "__main__":
    run_test()