# app/connectors/example_connector.py
"""
Exemple minimal montrant comment etendre BaseConnector.
Ceci n'est PAS un connecteur reel - juste une validation de l'interface,
en attendant le premier vrai connecteur (prochaine etape).
"""

from app.connectors.base_connector import BaseConnector


class ExampleConnector(BaseConnector):
    SOURCE_NAME = "example_source"
    SOURCE_TYPE = "ransomware_site"

    def fetch(self):
        # Simulation - sera remplace par un vrai appel via Tor
        return "<html><body>Exemple de contenu recupere</body></html>"

    def parse(self, raw_content):
        # Simulation - sera remplace par du vrai parsing BeautifulSoup
        return "Exemple de contenu recupere"


if __name__ == "__main__":
    connector = ExampleConnector()
    result = connector.collect()
    print(result)