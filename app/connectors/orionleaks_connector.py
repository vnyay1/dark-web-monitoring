"""
FR-03 - Connecteur reel #2 : Data Leaks & Exposure / Orion Leaks (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

ATTENTION CN-04/OS-03 : le lien "Hidden Link Revealed" pointe
potentiellement vers les donnees volees elles-memes. Ce lien ne doit
JAMAIS etre suivi/telecharge - on enregistre uniquement son existence
(booleen), jamais l'URL ni le contenu qu'il pointe.

MISE A JOUR : utilise desormais le module centralise app.tor.

PAGINATION (reconnaissance VM, 11/09/2026) : ul.pagination a.page-link,
lien "Next" vers ../news/home?page=N.
"""

import logging
from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class OrionLeaksConnector(BaseConnector):
    SOURCE_NAME = "orion_leaks"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://cjfntkj5qeizxowuy3srceg7zo6namc3kfeor7pfn6bpdkl3w265ooid.onion/news/home"

    # Plafond propre au connecteur ; le plafond effectif est le plus petit
    # de celui-ci et du reglage pages_listing_max.
    SUPPORTE_PAGINATION = True
    MAX_PAGES_LISTING = 30


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

            lien_cache_present = card.select_one(".hidden-link-revealed a") is not None

            texte_complet = " ".join(filter(
                None, [nom_entite, url_victime, statut, date_publication, message]
            ))

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

    def url_page_suivante(self, raw_content, page_courante):
        soup = BeautifulSoup(raw_content, "html.parser")
        for lien in soup.select("ul.pagination a.page-link"):
            if lien.get_text(strip=True).lower() == "next":
                return self._page_suivante_validee(lien.get("href"), page_courante)
        return None
