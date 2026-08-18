"""
FR-03 - Connecteur reel #4 : BlackWater (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

ATTENTION CN-04/OS-03 : le paragraphe de description contient souvent
une URL .onion pointant DIRECTEMENT vers les donnees divulguees. Cette
URL est systematiquement retiree du texte conserve.

MISE A JOUR : utilise desormais le module centralise app.tor.
"""

import logging
import re
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector
from app.tor import get_via_tor

logger = logging.getLogger(__name__)


class BlackWaterConnector(BaseConnector):
    SOURCE_NAME = "blackwater"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://ejzl7cjxmkx7lzhiqwidmrwtfjv45pkczbc4fnyaut3t7gll3yaiq5id.onion/"

    URL_PATTERN = re.compile(r"https?://\S+")

    def fetch(self):
        response = get_via_tor(self.TARGET_URL)
        return response.text

    def _nettoyer_description(self, texte: str) -> str:
        """Retire toute URL presente dans la description (CN-04/OS-03)."""
        if not texte:
            return texte
        texte_sans_url = self.URL_PATTERN.sub("[LIEN RETIRE]", texte)
        return texte_sans_url.strip()

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
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