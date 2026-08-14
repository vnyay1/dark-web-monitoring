"""
FR-03 - Connecteur reel #4 : BlackWater (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

Structure REELLE confirmee :

<div class="col-md-8 col-12 mx-auto" data-key="10">
    <div class="card h-100 flex-md-row p-4 gap-3">
        <img src="logo?uuid=..." class="col-md-4" alt="msgas.com.br" ...>
        <div class="col-md-8">
            <h5 class="card-title">msgas.com.br</h5>
            <p class="card-text text-muted">Publicated at 2026-07-25 13:06:24</p>
            <p class="card-text text-muted" style="...line-clamp...">
                customers' personal data, contract information, internal company data:
                http://ucfhnoihzgx...onion/s/7f89713825a4376e/
            </p>
            <a class="btn btn-secondary btn-sm" href="/blog?uuid=...">See more</a>
        </div>
    </div>
</div>

ATTENTION CN-04/OS-03 : le paragraphe de description contient souvent une
URL .onion pointant DIRECTEMENT vers les donnees divulguees. Cette URL est
systematiquement retiree du texte conserve - seul le texte descriptif
(type de donnees revendique) est garde, jamais le lien d'acces aux
donnees elles-memes.
"""

import logging
import re
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class BlackWaterConnector(BaseConnector):
    SOURCE_NAME = "blackwater"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://ejzl7cjxmkx7lzhiqwidmrwtfjv45pkczbc4fnyaut3t7gll3yaiq5id.onion/"

    TOR_SOCKS_PROXY = "socks5h://127.0.0.1:9050"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    # Detecte toute URL .onion (ou http/https generique) presente dans un texte,
    # afin de la retirer avant conservation (CN-04/OS-03)
    URL_PATTERN = re.compile(r"https?://\S+")

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

    def _nettoyer_description(self, texte: str) -> str:
        """
        Retire toute URL presente dans la description (lien potentiel vers
        les donnees divulguees elles-memes - CN-04/OS-03), ne garde que le
        texte descriptif du type de donnees revendique.
        """
        if not texte:
            return texte
        texte_sans_url = self.URL_PATTERN.sub("[LIEN RETIRE]", texte)
        return texte_sans_url.strip()

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        # Chaque entree est un bloc col-md-8.col-12.mx-auto avec un data-key,
        # contenant lui-meme le .card
        blocs = soup.select("div[data-key] > div.card")

        for card in blocs:
            nom_tag = card.select_one("h5.card-title")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            paragraphs = card.select("p.card-text")

            date_publication = None
            description = None

            for p in paragraphs:
                texte = p.get_text(strip=True)
                if texte.lower().startswith("publicated at"):
                    date_publication = texte.replace("Publicated at", "").strip()
                else:
                    # Le paragraphe de description (potentiellement avec URL a nettoyer)
                    description = self._nettoyer_description(texte)

            lien_detail_tag = card.select_one("a.btn")
            lien_detail = lien_detail_tag.get("href") if lien_detail_tag else None

            texte_complet = " ".join(filter(None, [nom_entite, description]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "date_publication": date_publication,
                "description": description,
                "lien_detail": lien_detail,
                "texte_brut": texte_complet,
            })

        logger.info(f"[blackwater] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = BlackWaterConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Nom detecte : {entry['nom_entite_detecte']}")
            print(f"  Date : {entry['date_publication']}")
            print(f"  Description (nettoyee) : {entry['description']}")
            print(f"  Lien detail : {entry['lien_detail']}")
    else:
        print(f"[ECHEC] {result['error']}")