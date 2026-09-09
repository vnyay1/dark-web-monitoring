"""
FR-03 - Connecteur reel #7 : CMD Organization (forum/paste - annuaire de
victimes avec documents).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

ATTENTION CN-04/OS-03 : les liens dans "item-links" menent probablement
directement aux donnees divulguees. On enregistre uniquement le NOMBRE
de liens presents, jamais les URLs elles-memes.

MISE A JOUR : utilise desormais le module centralise app.tor.
"""

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class CmdOrganizationConnector(BaseConnector):
    SOURCE_NAME = "cmd_organization"
    SOURCE_TYPE = "forum"

    TARGET_URL = "http://cmdnkiqjije2tllr3biee2sjgj3i4robg2cbtilbnytdhh2wy3syrlyd.onion/"

    VOLUME_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(GB|MB|TB)", re.IGNORECASE)

    @staticmethod
    def _extraire_domaine(url):
        """
        Extrait le nom de domaine du site officiel de la victime, SANS
        jamais visiter ce site (collecte passive, CN-09/CN-10 : le site de
        la victime n'est pas une source surveillee).

        Le domaine est un signal fort : un ".cm" correspond directement aux
        selecteurs de categorie DOMAINE du catalogue.
        """
        if not url:
            return None
        hote = urlparse(url if "//" in url else "//" + url).netloc
        return hote[4:] if hote.startswith("www.") else hote or None


    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        cards = soup.select("div.items-grid > div.item-card")

        for card in cards:
            nom_tag = card.select_one(".item-header h2 a")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None
            site_officiel_victime = nom_tag.get("href") if nom_tag else None

            desc_before_tag = card.select_one(".description-before")
            description = desc_before_tag.get_text(separator=" ", strip=True) if desc_before_tag else None

            desc_after_tag = card.select_one(".description-after")
            volume_texte = desc_after_tag.get_text(strip=True) if desc_after_tag else None

            volume_extrait = None
            if volume_texte:
                match = self.VOLUME_PATTERN.search(volume_texte)
                if match:
                    volume_extrait = f"{match.group(1)} {match.group(2).upper()}"

            liens_documents = card.select(".item-links a")
            nb_liens_documents = len(liens_documents)

            domaine_victime = self._extraire_domaine(site_officiel_victime)

            texte_complet = " ".join(filter(None, [nom_entite, domaine_victime, description]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "site_officiel_victime": site_officiel_victime,
                "domaine_victime": domaine_victime,
                "description": description,
                "volume_revendique": volume_extrait,
                "nb_liens_documents": nb_liens_documents,
                "texte_brut": texte_complet,
            })

        logger.info(f"[cmd_organization] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = CmdOrganizationConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Nom detecte : {entry['nom_entite_detecte']}")
            print(f"  Volume revendique : {entry['volume_revendique']}")
            print(f"  Nb liens documents : {entry['nb_liens_documents']}")
    else:
        print(f"[ECHEC] {result['error']}")