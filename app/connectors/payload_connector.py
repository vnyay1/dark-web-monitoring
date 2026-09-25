"""
FR-03 - Connecteur reel #1 : Payload (ransomware leak site).
STATUT : teste et valide en conditions reelles (VM isolee, 08/2026).

Structure REELLE confirmee :

<a class="card-link" href="/posts/{id}">
    <article class="card">
        ...
        <span class="title">{nom de la victime}</span>
        <span class="timer">05d 12h 56m</span>
        <span class="company-sep">.</span>
        <span class="company-size">64 GB</span>
        <span class="company-sep">.</span>
        <span class="company-linklike">/ site</span>
        ...
    </article>
</a>

Le lien est le PARENT de la card, pas l'inverse. Listing seul : aucune
page de detail, aucune date publiee.
"""

import logging
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class PayloadConnector(BaseConnector):
    SOURCE_NAME = "payload"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://payloadrz5yw227brtbvdqpnlhq3rdcdekdnn3rgucbcdeawq2v6vuyd.onion/"

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        for link_tag in soup.select("a.card-link"):
            card = link_tag.select_one("article.card")
            if card is None:
                continue

            nom_tag = card.select_one(".title")

            entries.append({
                "nom_entite_detecte": nom_tag.get_text(strip=True) if nom_tag else None,
                "lien_detail": link_tag.get("href"),
                # Texte COMPLET de la card (nom, volume revendique, compte a
                # rebours) : une mention camerounaise peut s'y trouver.
                "texte_brut": card.get_text(separator=" ", strip=True),
            })

        logger.info(f"[payload] {len(entries)} entree(s) trouvee(s) sur la page.")
        return {"entries": entries}
