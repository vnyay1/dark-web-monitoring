"""
FR-03 - Connecteur reel #1 : Payload (ransomware leak site).

Structure observee (capture d'ecran fournie par l'encadrant, a
reconfirmer en conditions reelles depuis la VM) :

<article class="card">
    <a class="card-link" href="/posts/{id}">
        <div class="company-line">
            <span class="timer">05d 12h 56m</span>
            <span class="company-sep">.</span>
            <span class="company-size">64 GB</span>
            <span class="company-sep">.</span>
            <span class="company-linklike">/ site</span>
        </div>
    </a>
</article>

Le nom de l'entreprise/victime lui-meme n'apparaissait pas clairement
dans l'extrait capture (probablement dans un <h1>/<h2> ou <span> juste
avant "Support in Tox" - a VERIFIER et ajuster une fois teste en reel).
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

        NOTE IMPORTANTE : les selecteurs CSS ci-dessous sont bases sur une
        capture d'ecran statique fournie, pas sur une inspection live.
        A ajuster des le premier test reel si la structure differe
        (notamment pour recuperer le nom de l'entite, pas visible avec
        certitude dans l'extrait disponible).
        """
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        cards = soup.select("article.card")

        for card in cards:
            link_tag = card.select_one("a.card-link")
            href = link_tag.get("href") if link_tag else None

            size_tag = card.select_one("span.company-size")
            taille = size_tag.get_text(strip=True) if size_tag else None

            timer_tag = card.select_one("span.timer")
            timer = timer_tag.get_text(strip=True) if timer_tag else None

            # Le nom de la victime n'est pas confirme dans la structure
            # observee - on tente plusieurs candidats plausibles, a
            # ajuster une fois le vrai HTML inspecte
            nom_tag = (
                card.select_one("h1")
                or card.select_one("h2")
                or card.select_one(".company-name")
                or card.select_one(".card-title")
            )
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            # Texte complet de la card, utilise comme filet de securite
            # pour le Matching Engine meme si les champs structures
            # ci-dessus ne sont pas tous trouves
            texte_complet = card.get_text(separator=" ", strip=True)

            entries.append({
                "nom_entite_detecte": nom_entite,
                "taille": taille,
                "timer": timer,
                "lien_detail": href,
                "texte_brut": texte_complet,
            })

        logger.info(f"[payload] {len(entries)} entree(s) trouvee(s) sur la page.")

        # Le texte global (toutes entrees concatenees) est ce qui sera
        # transmis au Matching Engine - chaque entree individuelle reste
        # aussi disponible si on veut affiner le traitement par la suite
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