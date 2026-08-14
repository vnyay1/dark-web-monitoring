"""
FR-03 - Connecteur reel #2 : Data Leaks & Exposure / Orion Leaks (ransomware leak site).
STATUT : premiere version, structure de la ZONE DE LISTE non confirmee
(la capture disponible ne montrait que le header/hero, pas les entrees
elles-memes). A ajuster une fois teste en reel, comme pour Payload.

Structure partiellement connue :
- Site Bootstrap (navbar-dark bg-dark, container, etc.)
- Nom du site : "Data Leaks & Exposure" (visible dans un <h1 class="display-4">)
- La liste des entrees/victimes n'a pas ete vue dans la capture fournie
"""

import logging
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class OrionLeaksConnector(BaseConnector):
    SOURCE_NAME = "orion_leaks"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://cjfntkj5qeizxowuy3srceg7zo6namc3kfeor7pfn6bpdkl3w265ooid.onion/news/home"

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
            timeout=30,
        )
        response.raise_for_status()
        return response.text

    def parse(self, raw_content):
        """
        PREMIERE TENTATIVE - structure de liste non confirmee.

        On tente plusieurs selecteurs plausibles pour une structure
        Bootstrap classique (card, list-group, table...). A remplacer
        par le vrai selecteur une fois inspecte dans la VM.
        """
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []

        # Tentatives de selecteurs plausibles, par ordre de probabilite
        candidate_selectors = [
            ".card",
            ".list-group-item",
            "article",
            "tr",
        ]

        items = []
        selecteur_utilise = None
        for sel in candidate_selectors:
            found = soup.select(sel)
            if found:
                items = found
                selecteur_utilise = sel
                break

        logger.info(f"[orion_leaks] Selecteur utilise : '{selecteur_utilise}' -> {len(items)} element(s) brut(s)")

        for item in items:
            texte_complet = item.get_text(separator=" ", strip=True)
            if not texte_complet:
                continue
            entries.append({
                "texte_brut": texte_complet,
            })

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
            "selecteur_utilise": selecteur_utilise,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = OrionLeaksConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] Selecteur utilise : {data['selecteur_utilise']}")
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Texte brut (300 premiers car.) : {entry['texte_brut'][:300]}")
    else:
        print(f"[ECHEC] {result['error']}")