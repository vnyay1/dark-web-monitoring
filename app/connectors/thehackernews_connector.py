"""
FR-03 - Connecteur reel #6 : The Hacker News (source clairnet, actualite
cybersecurite / vulnerabilites).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

Structure REELLE confirmee (page categorie "Vulnerability") :

<a class="story-link" href="https://thehackernews.com/2026/08/....html">
    <div class="clear home-post-box cf">
        <div class="home-img clear">...</div>
        <div class="clear home-right">
            <h2 class="home-title">Unpatched GeoServer Zero-Day ...</h2>
            <div class="item-label">
                <span class="h-datetime">Aug 13, 2026</span>
                <span class="h-tags">Zero-Day / Vulnerability</span>
            </div>
            <div class="home-desc"> A newly disclosed zero-day flaw ... </div>
        </div>
    </div>
</a>

Site en clairnet (pas de Tor necessaire pour ce connecteur). Contrairement
aux leak sites, il s'agit d'actualite cybersecurite generale : le
Matching Engine se chargera de ne retenir que les articles mentionnant
reellement des entites camerounaises, le reste sera naturellement filtre
en amont par l'absence de correspondance de selecteurs.
"""

import logging
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class TheHackerNewsConnector(BaseConnector):
    SOURCE_NAME = "thehackernews"
    SOURCE_TYPE = "forum"  # classe comme "forum/actualite" au sens SC-01/SC-03

    TARGET_URL = "https://thehackernews.com/search/label/Vulnerability"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def fetch(self):
        """
        Site en clairnet - pas de proxy Tor necessaire pour ce connecteur,
        contrairement aux 5 leak sites .onion precedents.
        """
        response = requests.get(
            self.TARGET_URL,
            headers=self.HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        return response.text

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        articles = soup.select("a.story-link")

        for article in articles:
            lien_article = article.get("href")

            titre_tag = article.select_one("h2.home-title")
            titre = titre_tag.get_text(strip=True) if titre_tag else None

            date_tag = article.select_one("span.h-datetime")
            date_publication = date_tag.get_text(strip=True) if date_tag else None

            tags_tag = article.select_one("span.h-tags")
            tags = tags_tag.get_text(strip=True) if tags_tag else None

            desc_tag = article.select_one("div.home-desc")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            texte_complet = " ".join(filter(None, [titre, description]))

            entries.append({
                "titre": titre,
                "date_publication": date_publication,
                "tags": tags,
                "description": description,
                "lien_article": lien_article,
                "texte_brut": texte_complet,
            })

        logger.info(f"[thehackernews] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = TheHackerNewsConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Titre : {entry['titre']}")
            print(f"  Date : {entry['date_publication']}")
            print(f"  Tags : {entry['tags']}")
            print(f"  Lien : {entry['lien_article']}")
            print(f"  Description (150 premiers car.) : {entry['description'][:150] if entry['description'] else None}")
    else:
        print(f"[ECHEC] {result['error']}")