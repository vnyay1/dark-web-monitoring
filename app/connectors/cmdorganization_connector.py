"""
FR-03 - Connecteur reel #7 : CMD Organization (forum/paste - annuaire de
victimes avec documents).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

Structure REELLE confirmee :

<div class="items-grid">
    <div class="item-card">
        <div class="item-header">
            <img src="/image/..." alt="Stewart Belland & Associates Inc." class="title-image">
            <h2>
                <a href="https://stewartbellandassociates.ca" target="_blank">Stewart Belland & Associates Inc.</a>
            </h2>
        </div>
        <div class="description-before">
            Stewart Belland & Associates Inc. (SBA) is a Civil Enforcement Agency ...
        </div>
        <div class="item-images"> ... galerie de captures ... </div>
        <div class="item-links inline">
            <a href="/click/138" target="_blank">Documents</a>
            <a href="/click/139" target="_blank">Document tree</a>
        </div>
        <div class="description-after">
            We have 296 GB of downloaded data.
        </div>
    </div>
    ...
</div>

ATTENTION CN-04/OS-03 : les liens dans "item-links" (Documents, Document
tree) menent tres probablement DIRECTEMENT aux donnees divulguees. On
enregistre uniquement le NOMBRE de liens presents (booleen/compteur),
jamais les URLs /click/{id} elles-memes ni leur contenu.

Le lien <a href> dans le <h2> est different : c'est le site web LEGITIME
de la victime (ex: stewartbellandassociates.ca), pas un lien vers des
donnees volees - celui-la peut etre conserve sans probleme, c'est une
reference publique a l'entite elle-meme.
"""

import logging
import re
import requests
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class CmdOrganizationConnector(BaseConnector):
    SOURCE_NAME = "cmd_organization"
    SOURCE_TYPE = "forum"

    TARGET_URL = "http://cmdnkiqjije2tllr3biee2sjgj3i4robg2cbtilbnytdhh2wy3syrlyd.onion/"

    TOR_SOCKS_PROXY = "socks5h://127.0.0.1:9050"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    # Detecte les volumes de donnees revendiques (ex: "296 GB", "1.2 TB")
    VOLUME_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(GB|MB|TB)", re.IGNORECASE)

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
        cards = soup.select("div.items-grid > div.item-card")

        for card in cards:
            # Nom de l'entite + lien vers son site LEGITIME (pas un lien de donnees volees)
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

            # Liens vers les documents/donnees volees : on compte seulement,
            # on ne conserve JAMAIS les URLs /click/{id} elles-memes
            liens_documents = card.select(".item-links a")
            nb_liens_documents = len(liens_documents)

            texte_complet = " ".join(filter(None, [nom_entite, description]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "site_officiel_victime": site_officiel_victime,
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
            print(f"  Site officiel : {entry['site_officiel_victime']}")
            print(f"  Volume revendique : {entry['volume_revendique']}")
            print(f"  Nb liens documents : {entry['nb_liens_documents']}")
            print(f"  Description (150 premiers car.) : {entry['description'][:150] if entry['description'] else None}")
    else:
        print(f"[ECHEC] {result['error']}")