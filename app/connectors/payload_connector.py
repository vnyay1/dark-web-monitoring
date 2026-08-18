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

Le lien est le PARENT de la card, pas l'inverse.

MISE A JOUR : utilise desormais le module centralise app.tor pour la
connexion (renouvellement de circuit inclus automatiquement), au lieu
de dupliquer la logique de proxy SOCKS localement.
"""

import logging
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector
from app.tor import get_via_tor

logger = logging.getLogger(__name__)


class PayloadConnector(BaseConnector):
    SOURCE_NAME = "payload"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://payloadrz5yw227brtbvdqpnlhq3rdcdekdnn3rgucbcdeawq2v6vuyd.onion/"

    def fetch(self):
        response = get_via_tor(self.TARGET_URL)
        return response.text  # reste en memoire, jamais ecrit sur disque (CN-05)

    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        links = soup.select("a.card-link")

        for link_tag in links:
            href = link_tag.get("href")

            card = link_tag.select_one("article.card")
            if card is None:
                continue

            nom_tag = card.select_one(".title")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            size_tag = card.select_one("span.company-size")
            taille = size_tag.get_text(strip=True) if size_tag else None

            timer_tag = card.select_one("span.timer")
            timer = timer_tag.get_text(strip=True) if timer_tag else None

            texte_complet = card.get_text(separator=" ", strip=True)

            entries.append({
                "nom_entite_detecte": nom_entite,
                "taille": taille,
                "timer": timer,
                "lien_detail": href,
                "texte_brut": texte_complet,
            })

        logger.info(f"[payload] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = PayloadConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Nom detecte : {entry['nom_entite_detecte']}")
            print(f"  Taille : {entry['taille']}")
            print(f"  Timer : {entry['timer']}")
            print(f"  Lien : {entry['lien_detail']}")
    else:
        print(f"[ECHEC] {result['error']}")