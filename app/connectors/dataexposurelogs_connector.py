"""
FR-03 - Connecteur reel #3 : Data Exposure logs (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

PAGINATION (reconnaissance VM, 11/09/2026) : div.pagination, lien
a.page-btn "NEXT >>" vers /?page=N.

DATES (reconnaissance VM, 11/09/2026) : une partie des cartes n'affiche ni
AUDIT ID ni DISCOVERY DATE - 5 sur 10 en page 2. Les cartes datees sont
rangees de la plus recente a la plus ancienne sur les deux pages : une
carte sans date est donc bornee par la carte datee qui la precede
(LISTING_CHRONOLOGIQUE, cf. BaseConnector._poser_dates_plafond).
"""

import logging
import re
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class DataExposureLogsConnector(BaseConnector):
    SOURCE_NAME = "data_exposure_logs"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://6tdqqaxftvradka5d2frzgwixis7fmro7rfh4ettzcx7jfapkebe6jad.onion/"

    ONCLICK_URL_PATTERN = re.compile(r"window\.open\('([^']+)'")

    SUPPORTE_PAGINATION = True
    MAX_PAGES_LISTING = 30
    LISTING_CHRONOLOGIQUE = True

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        for card in soup.select("div.grid > div.card"):
            nom_tag = card.select_one(".title")

            discovery_date = None
            for meta in card.select(".meta-info"):
                texte = meta.get_text(strip=True)
                if texte.startswith("DISCOVERY DATE:"):
                    discovery_date = texte.replace("DISCOVERY DATE:", "").strip()

            # Lien de la card : sert d'identifiant de crawl quand il pointe
            # sur le domaine surveille, jamais visite (listing seul).
            match = self.ONCLICK_URL_PATTERN.search(card.get("onclick", ""))

            entries.append({
                "nom_entite_detecte": nom_tag.get_text(strip=True) if nom_tag else None,
                "discovery_date": discovery_date,
                "lien_detail": match.group(1) if match else None,
                # On analyse le texte COMPLET de la card, pas seulement les
                # quelques champs structures : une mention camerounaise peut
                # apparaitre n'importe ou (secteur, pays, note), et ce texte
                # est deja telecharge - le restreindre ne coutait rien en
                # reseau mais rendait le matching quasi impossible.
                "texte_brut": self.nettoyer_urls(card.get_text(separator=" ", strip=True)),
            })

        logger.info(f"[data_exposure_logs] {len(entries)} entree(s) trouvee(s) sur la page.")
        return {"entries": entries}

    def url_page_suivante(self, raw_content, page_courante):
        soup = BeautifulSoup(raw_content, "html.parser")
        for lien in soup.select(".pagination a.page-btn"):
            if "next" in lien.get_text(strip=True).lower():
                return self._page_suivante_validee(lien.get("href"), page_courante)
        return None
