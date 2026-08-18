"""
FR-03 - Connecteur reel #3 : Data Exposure logs (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

MISE A JOUR : utilise desormais le module centralise app.tor.
"""

import logging
import re
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector
from app.tor import get_via_tor

logger = logging.getLogger(__name__)


class DataExposureLogsConnector(BaseConnector):
    SOURCE_NAME = "data_exposure_logs"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://6tdqqaxftvradka5d2frzgwixis7fmro7rfh4ettzcx7jfapkebe6jad.onion/"

    ONCLICK_URL_PATTERN = re.compile(r"window\.open\('([^']+)'")
    STATUS_CLASS_PATTERN = re.compile(r"status-([A-Za-z_]+)")

    def fetch(self):
        response = get_via_tor(self.TARGET_URL)
        return response.text

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        cards = soup.select("div.grid > div.card")

        for card in cards:
            nom_tag = card.select_one(".title")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            meta_infos = card.select(".meta-info")
            audit_id = None
            discovery_date = None
            for meta in meta_infos:
                texte = meta.get_text(strip=True)
                if texte.startswith("AUDIT ID:"):
                    audit_id = texte.replace("AUDIT ID:", "").strip()
                elif texte.startswith("DISCOVERY DATE:"):
                    discovery_date = texte.replace("DISCOVERY DATE:", "").strip()

            onclick_attr = card.get("onclick", "")
            match = self.ONCLICK_URL_PATTERN.search(onclick_attr)
            lien_detail = match.group(1) if match else None

            flag_svg = card.select_one("svg[id^='flag-icons-']")
            code_pays_indicatif = None
            if flag_svg:
                flag_id = flag_svg.get("id", "")
                code_pays_indicatif = flag_id.replace("flag-icons-", "") or None

            status_div = card.select_one("[class*='status-']")
            statut = None
            if status_div:
                for cls in status_div.get("class", []):
                    m = self.STATUS_CLASS_PATTERN.match(cls)
                    if m:
                        statut = m.group(1)
                        break

            texte_complet = " ".join(filter(None, [nom_entite, audit_id, discovery_date, statut]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "audit_id": audit_id,
                "discovery_date": discovery_date,
                "lien_detail": lien_detail,
                "code_pays_indicatif": code_pays_indicatif,
                "statut": statut,
                "texte_brut": texte_complet,
            })

        logger.info(f"[data_exposure_logs] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = DataExposureLogsConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Nom detecte : {entry['nom_entite_detecte']}")
            print(f"  Audit ID : {entry['audit_id']}")
            print(f"  Date decouverte : {entry['discovery_date']}")
            print(f"  Pays (indicatif) : {entry['code_pays_indicatif']}")
            print(f"  Statut : {entry['statut']}")
            print(f"  Lien detail : {entry['lien_detail']}")
    else:
        print(f"[ECHEC] {result['error']}")