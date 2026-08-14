"""
FR-03 - Connecteur reel #5 : SafePay (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

Structure REELLE confirmee :

<div class="col-md-4 mb-4">
    <div class="card bg-dark text-light h-100">
        <div class="card-header ...">
            <div class="d-flex align-items-center flex-grow-1">
                <img ... class="favicon-img">
                <h5 class="card-title text-center mb-0">simonrack.com</h5>
            </div>
            <img src="https://flagcdn.com/16x12/es.png" alt="ES" class="country-flag" title="">
        </div>
        <div class="card-body">
            <p class="card-text">Headquartered in Alfamen, Zaragoza, Spain, ...</p>
        </div>
        <div class="published-text">
            <span class="text-success fw-bold">Published</span>
        </div>
        <div class="card-footer ...">
            <span class="badge bg-secondary"><i class="bi bi-eye"></i> 15798</span>
            <a href="/blog/post/simonrackcom/" class="btn btn-sm btn-primary">Learn More</a>
        </div>
    </div>
</div>

Le code pays est fiable ici : attribut alt="ES"/"IT"/"US" sur l'image
du drapeau (contrairement a Data Exposure logs ou l'id du SVG etait
moins certain). Aucun lien vers des donnees divulguees n'est present
dans cette structure - rien a nettoyer ici (contrairement a BlackWater).
"""

import logging
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class SafePayConnector(BaseConnector):
    SOURCE_NAME = "safepay"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://safepaypfxntwixwjrlcscft433ggemlhgkkdupi2ynhtcmvdgubmoyd.onion/"

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
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        cards = soup.select("div.card.bg-dark.text-light")

        for card in cards:
            nom_tag = card.select_one("h5.card-title")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            flag_tag = card.select_one("img.country-flag")
            code_pays = flag_tag.get("alt") if flag_tag else None

            description_tag = card.select_one("p.card-text")
            description = description_tag.get_text(strip=True) if description_tag else None

            statut_tag = card.select_one(".published-text span")
            statut = statut_tag.get_text(strip=True) if statut_tag else None

            vues_tag = card.select_one(".badge.bg-secondary")
            vues = vues_tag.get_text(strip=True) if vues_tag else None

            lien_detail_tag = card.select_one("a.btn-primary")
            lien_detail = lien_detail_tag.get("href") if lien_detail_tag else None

            texte_complet = " ".join(filter(None, [nom_entite, description]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "code_pays": code_pays,
                "description": description,
                "statut": statut,
                "vues": vues,
                "lien_detail": lien_detail,
                "texte_brut": texte_complet,
            })

        logger.info(f"[safepay] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = SafePayConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Nom detecte : {entry['nom_entite_detecte']}")
            print(f"  Pays : {entry['code_pays']}")
            print(f"  Statut : {entry['statut']}")
            print(f"  Vues : {entry['vues']}")
            print(f"  Description : {entry['description'][:100] if entry['description'] else None}")
    else:
        print(f"[ECHEC] {result['error']}")