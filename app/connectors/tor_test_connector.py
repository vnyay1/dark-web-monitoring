"""
Connecteur de TEST uniquement - valide la connexion .onion reelle via Tor,
combinee avec BaseConnector (FR-01 + FR-02).
Cible : miroir .onion officiel du Tor Project (site neutre, lecture publique,
aucune inscription requise - conforme OS-01/CN-09).

A NE PAS GARDER comme connecteur final. En attente de validation des sources
reelles par l'encadrant (ambiguite 4).
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


class TorTestConnector(BaseConnector):
    SOURCE_NAME = "tor_project_onion_test"
    SOURCE_TYPE = "test_clairnet"  # ce n'est pas une vraie source clandestine

    # Adresse .onion officielle du Tor Project (verifiee via source officielle)
    TARGET_URL = "http://2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion"

    TOR_SOCKS_PROXY = "socks5h://127.0.0.1:9050"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def fetch(self):
        proxies = {
            "http": self.TOR_SOCKS_PROXY,
            "https": self.TOR_SOCKS_PROXY,
        }
        response = requests.get(
            self.TARGET_URL,
            proxies=proxies,
            headers=self.HEADERS,
            timeout=30,  # les requetes .onion sont plus lentes qu'en clairnet
        )
        response.raise_for_status()
        return response.text  # reste en memoire, jamais ecrit sur disque (CN-05)

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")
        title = soup.find("title")
        paragraphs = soup.find_all("p")
        text_parts = [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
        full_text = "\n".join(text_parts)
        return {
            "title": title.get_text().strip() if title else None,
            "text_excerpt": full_text[:500],
        }


if __name__ == "__main__":
    connector = TorTestConnector()
    result = connector.collect()

    if result["success"]:
        print("[OK] Connexion .onion reussie.")
        print("Titre de la page :", result["extracted_text"]["title"])
        print("Extrait :", result["extracted_text"]["text_excerpt"][:200])
    else:
        print(f"[ECHEC] {result['error']}")