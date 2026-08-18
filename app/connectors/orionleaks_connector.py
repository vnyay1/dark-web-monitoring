"""
FR-03 - Connecteur reel #2 : Data Leaks & Exposure / Orion Leaks (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

ATTENTION CN-04/OS-03 : le lien "Hidden Link Revealed" pointe
potentiellement vers les donnees volees elles-memes. Ce lien ne doit
JAMAIS etre suivi/telecharge - on enregistre uniquement son existence
(booleen), jamais l'URL ni le contenu qu'il pointe.

MISE A JOUR : utilise desormais le module centralise app.tor.
"""

import logging
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector
from app.tor import get_via_tor

logger = logging.getLogger(__name__)


class OrionLeaksConnector(BaseConnector):
    SOURCE_NAME = "orion_leaks"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://cjfntkj5qeizxowuy3srceg7zo6namc3kfeor7pfn6bpdkl3w265ooid.onion/news/home"

    def fetch(self):
        response = get_via_tor(self.TARGET_URL)
        return response.text

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        cards = soup.select("div.card.post-card")

        for card in cards:
            nom_tag = card.select_one("span.company-name")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            url_victime_tag = card.select_one("h5.card-title")
            url_victime = url_victime_tag.get_text(strip=True) if url_victime_tag else None

            date_tag = card.select_one("small.leak-date")
            date_publication = date_tag.get_text(strip=True) if date_tag else None

            message_tag = card.select_one("p.card-text")
            message = message_tag.get_text(strip=True) if message_tag else None

            statut_tag = card.select_one(".status-text")
            statut = statut_tag.get_text(strip=True) if statut_tag else None

            lien_cache_present = card.select_one(".hidden-link-revealed a") is not None

            texte_complet = " ".join(filter(None, [nom_entite, url_victime, message]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "url_victime": url_victime,
                "date_publication": date_publication,
                "message": message,
                "statut": statut,
                "lien_donnees_present": lien_cache_present,
                "texte_brut": texte_complet,
            })

        logger.info(f"[orion_leaks] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = OrionLeaksConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Nom detecte : {entry['nom_entite_detecte']}")
            print(f"  URL victime : {entry['url_victime']}")
            print(f"  Date : {entry['date_publication']}")
            print(f"  Statut : {entry['statut']}")
            print(f"  Lien donnees present : {entry['lien_donnees_present']}")
            print(f"  Message : {entry['message']}")
    else:
        print(f"[ECHEC] {result['error']}")