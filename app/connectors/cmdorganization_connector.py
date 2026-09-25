"""
FR-03 - Connecteur reel #6 : CMD Organization (forum/paste - annuaire de
victimes avec documents).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

ATTENTION CN-04/OS-03 : les liens dans "item-links" menent probablement
directement aux donnees divulguees. Ils ne sont ni suivis, ni lus, ni
conserves. Le lien du nom de la victime pointe vers son site officiel :
seul son DOMAINE en est tire, sans jamais le visiter. Listing seul.
"""

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class CmdOrganizationConnector(BaseConnector):
    SOURCE_NAME = "cmd_organization"
    SOURCE_TYPE = "forum"

    TARGET_URL = "http://cmdnkiqjije2tllr3biee2sjgj3i4robg2cbtilbnytdhh2wy3syrlyd.onion/"

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
        for card in soup.select("div.items-grid > div.item-card"):
            nom_tag = card.select_one(".item-header h2 a")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None
            domaine_victime = self._extraire_domaine(nom_tag.get("href") if nom_tag else None)

            desc_tag = card.select_one(".description-before")
            description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else None

            entries.append({
                "nom_entite_detecte": nom_entite,
                "texte_brut": " ".join(filter(None, [nom_entite, domaine_victime, description])),
            })

        logger.info(f"[cmd_organization] {len(entries)} entree(s) trouvee(s) sur la page.")
        return {"entries": entries}
