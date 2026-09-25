"""
FR-03 - Connecteur reel #4 : BlackWater (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

ATTENTION CN-04/OS-03 : le paragraphe de description contient souvent
une URL .onion pointant DIRECTEMENT vers les donnees divulguees. Cette
URL est systematiquement retiree du texte analyse et conserve.

PAGINATION (reconnaissance VM, 11/09/2026) : ul.pagination, element
li.next vers /?page=N&per-page=M ; sur la derniere page, li.next porte la
classe "disabled" et ne contient plus de lien.
"""

import logging
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class BlackWaterConnector(BaseConnector):
    SOURCE_NAME = "blackwater"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://ejzl7cjxmkx7lzhiqwidmrwtfjv45pkczbc4fnyaut3t7gll3yaiq5id.onion/"

    SUPPORTE_PAGINATION = True
    MAX_PAGES_LISTING = 30

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        for card in soup.select("div[data-key] > div.card"):
            nom_tag = card.select_one("h5.card-title")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            date_publication = None
            description = None
            for p in card.select("p.card-text"):
                texte = p.get_text(strip=True)
                if texte.lower().startswith("publicated at"):
                    date_publication = texte.replace("Publicated at", "").strip()
                else:
                    description = self.nettoyer_urls(texte)

            lien_detail_tag = card.select_one("a.btn")

            entries.append({
                "nom_entite_detecte": nom_entite,
                "date_publication": date_publication,
                "lien_detail": lien_detail_tag.get("href") if lien_detail_tag else None,
                "texte_brut": " ".join(filter(None, [nom_entite, description])),
            })

        logger.info(f"[blackwater] {len(entries)} entree(s) trouvee(s) sur la page.")
        return {"entries": entries}

    def url_page_suivante(self, raw_content, page_courante):
        soup = BeautifulSoup(raw_content, "html.parser")
        lien = soup.select_one("ul.pagination li.next:not(.disabled) a")
        return self._page_suivante_validee(lien.get("href"), page_courante) if lien else None
