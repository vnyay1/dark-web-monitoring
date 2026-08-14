"""
FR-03 - Connecteur reel #2 : Data Leaks & Exposure / Orion Leaks (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

Structure REELLE confirmee :

<div class="card h-100 post-card">
    <div class="position-relative">
        <img ... class="card-img-top post-thumbnail" alt="...">
        <div class="views-count"><i class="bi bi-eye"></i> 21458</div>
    </div>
    <div class="card-body">
        <div class="leak-card-header">
            <small class="leak-date">Jul 27, 2026</small>
            <span class="company-name">Nitrex Chemicals India</span>
        </div>
        <h5 class="card-title">https://www.nitrex.in</h5>
        <div class="status-badge status-published">
            <span class="status-text">PUBLISHED</span>
        </div>
        <p class="card-text">We only seek money. ...</p>
        <div class="hidden-link-revealed">
            <a href="https://mega.nz/...">Access Hidden Content</a>
        </div>
    </div>
    <div class="card-footer ...">
        <a href="../news/article?id=37" class="btn ...">View Details</a>
    </div>
</div>

IMPORTANT (CN-03/CN-04/CN-05) : le lien "Hidden Link Revealed" pointe
potentiellement vers les donnees volees elles-memes (ex: lien Mega.nz).
Ce lien ne doit JAMAIS etre suivi/telecharge par le connecteur - on se
contente d'enregistrer qu'un tel lien existe (booleen), jamais l'URL
complete ni le contenu qu'il pointe. Cf. OS-03 (interdiction de
telecharger/stocker le contenu des donnees divulguees).
"""

import logging
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class OrionLeaksConnector(BaseConnector):
    SOURCE_NAME = "orion_leaks"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://cjfntkj5qeizxowuy3srceg7zo6namc3kfeor7pfn6bpdkl3w265ooid.onion/news/home"

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

            # On note seulement l'EXISTENCE d'un lien vers les donnees,
            # jamais l'URL elle-meme ni son contenu (OS-03, CN-04)
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