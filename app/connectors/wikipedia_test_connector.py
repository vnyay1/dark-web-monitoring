"""
Connecteur de TEST uniquement - valide la chaine fetch/parse reelle
(pas Tor, pas de source clandestine) avant de brancher une vraie source.
Cible : Wikipedia (page stable, neutre, sans lien avec le sujet du projet).

A NE PAS GARDER comme connecteur final - sert uniquement a valider
que BaseConnector fonctionne avec de vraies requetes HTTP + parsing HTML.
"""

import logging
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


class WikipediaTestConnector(BaseConnector):
    SOURCE_NAME = "wikipedia_test"
    SOURCE_TYPE = "test_clairnet"

    TARGET_URL = "https://en.wikipedia.org/wiki/Cameroon"

    # Wikipedia (comme beaucoup de sites) bloque les requetes sans
    # User-Agent de navigateur. Ce n'est PAS du contournement d'authentification
    # (CN-09) : c'est une simple identification HTTP standard, aucune
    # protection n'est franchie, aucun compte n'est utilise.
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def fetch(self):
        response = requests.get(self.TARGET_URL, headers=self.HEADERS, timeout=15)
        response.raise_for_status()
        return response.text  # reste en memoire (str), jamais ecrit sur disque

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")
        paragraphs = soup.select("#mw-content-text p")
        text_parts = [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
        full_text = "\n".join(text_parts)
        return full_text


if __name__ == "__main__":
    connector = WikipediaTestConnector()
    result = connector.collect()

    if result["success"]:
        print(f"[OK] {len(result['extracted_text'])} caracteres extraits.")
        print("Extrait (200 premiers caracteres) :")
        print(result["extracted_text"][:200])
    else:
        print(f"[ECHEC] {result['error']}")