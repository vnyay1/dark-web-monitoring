"""
FR-03 - Connecteur reel #3 : Data Exposure logs (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

Structure REELLE confirmee :

<div class="grid">
    <div class="card" onclick="window.open('/entity/D1DDFB2A56855328', '_blank')">
        <div class="title ">I-SYS</div>
        <div class="meta-row">
            <div class="meta-texts">
                <div class="meta-info">AUDIT ID: C66B828414389C27</div>
                <div class="meta-info">DISCOVERY DATE: 2026-06-15</div>
            </div>
            <svg ... id="flag-icons-ru" ...>...</svg>
        </div>
        <div class="card-bottom ">
            <div class="status-PUBLIC_TRANSPARENCY">[ STATUS: PUBLIC TRANSPARENCY ]</div>
        </div>
    </div>
    ...
</div>

Notes :
- Pas de <a href>, le lien vers le detail est dans l'attribut onclick
  (window.open('/entity/{id}', '_blank')) -> extrait par regex simple.
- Le drapeau SVG porte un id du type "flag-icons-{code_pays}" qui semble
  indiquer le pays associe a l'entree - a confirmer sur un plus grand
  echantillon (peut varier selon la librairie d'icones utilisee).
- Le statut ("PUBLIC TRANSPARENCY" ici) fait partie de la classe CSS
  elle-meme (status-PUBLIC_TRANSPARENCY), pratique pour categoriser
  sans dependre du texte affiche.
"""

import logging
import re
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class DataExposureLogsConnector(BaseConnector):
    SOURCE_NAME = "data_exposure_logs"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://6tdqqaxftvradka5d2frzgwixis7fmro7rfh4ettzcx7jfapkebe6jad.onion/"

    TOR_SOCKS_PROXY = "socks5h://127.0.0.1:9050"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    ONCLICK_URL_PATTERN = re.compile(r"window\.open\('([^']+)'")
    STATUS_CLASS_PATTERN = re.compile(r"status-([A-Za-z_]+)")

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

            # Lien de detail extrait depuis l'attribut onclick
            onclick_attr = card.get("onclick", "")
            match = self.ONCLICK_URL_PATTERN.search(onclick_attr)
            lien_detail = match.group(1) if match else None

            # Code pays indicatif, depuis l'id du SVG (ex: "flag-icons-ru" -> "ru")
            flag_svg = card.select_one("svg[id^='flag-icons-']")
            code_pays_indicatif = None
            if flag_svg:
                flag_id = flag_svg.get("id", "")
                code_pays_indicatif = flag_id.replace("flag-icons-", "") or None

            # Statut extrait depuis le nom de la classe CSS (plus fiable
            # que le texte affiche, qui peut changer de formulation)
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