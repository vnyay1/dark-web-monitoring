"""
FR-03 - Connecteur reel #1 : Payload (ransomware leak site).

Structure REELLE confirmee (VM, 08/2026) :

<a class="card-link" href="/posts/{id}">
    <article class="card">
        ...
        <span class="timer">05d 12h 56m</span>
        <span class="company-sep">.</span>
        <span class="company-size">64 GB</span>
        <span class="company-sep">.</span>
        <span class="company-linklike">/ site</span>
        ...
    </article>
</a>

Le lien est le PARENT de la card, pas l'inverse.
"""

import logging
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class PayloadConnector(BaseConnector):
    SOURCE_NAME = "payload"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://payloadrz5yw227brtbvdqpnlhq3rdcdekdnn3rgucbcdeawq2v6vuyd.onion/"

    TOR_SOCKS_PROXY = "socks5h://127.0.0.1:9050"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

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
        return response.text  # reste en memoire, jamais ecrit sur disque (CN-05)

    def parse(self, raw_content):
        """
        Extrait la liste des entrees (victimes annoncees) de la page.

        Le point d'entree de la boucle est le lien <a class="card-link">
        (parent), a l'interieur duquel on trouve <article class="card">.
        """
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        # Point d'entree : le LIEN, qui contient l'article, pas l'inverse
        links = soup.select("a.card-link")

        for link_tag in links:
            href = link_tag.get("href")

            card = link_tag.select_one("article.card")
            if card is None:
                # Securite : si jamais un lien card-link n'entoure pas
                # d'article (page partiellement chargee, variante), on
                # ignore proprement cette entree plutot que de planter
                continue

            size_tag = card.select_one("span.company-size")
            taille = size_tag.get_text(strip=True) if size_tag else None

            timer_tag = card.select_one("span.timer")
            timer = timer_tag.get_text(strip=True) if timer_tag else None

            # Le nom de la victime n'est toujours pas confirme avec
            # certitude dans la structure observee - a ajuster si besoin
            # une fois que tu vois le nom affiche reellement sur la page
            nom_tag = card.select_one(".title")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

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
            print(f"  Texte brut (200 premiers car.) : {entry['texte_brut'][:200]}")
    else:
        print(f"[ECHEC] {result['error']}")