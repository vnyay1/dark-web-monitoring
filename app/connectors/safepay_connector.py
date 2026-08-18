"""
FR-03 - Connecteur reel #5 : SafePay (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

MISE A JOUR : utilise desormais le module centralise app.tor.
"""

import logging
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector
from app.tor import get_via_tor

logger = logging.getLogger(__name__)


class SafePayConnector(BaseConnector):
    SOURCE_NAME = "safepay"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://safepaypfxntwixwjrlcscft433ggemlhgkkdupi2ynhtcmvdgubmoyd.onion/"

    def fetch(self):
        response = get_via_tor(self.TARGET_URL)
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
    else:
        print(f"[ECHEC] {result['error']}")