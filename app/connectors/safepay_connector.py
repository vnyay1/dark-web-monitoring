"""
FR-03 - Connecteur reel #5 : SafePay (ransomware leak site).
STATUT : structure confirmee via inspection reelle (VM, 08/2026).

MISE A JOUR : utilise desormais le module centralise app.tor.

PAGE DE DETAIL - le listing ne date pas ses annonces ; la page de detail,
si. Structure confirmee par reconnaissance (VM, 10/09/2026, verdict de
liceite favorable : HTML, meme domaine, page d'annonce) :

    div.card.bg-dark.text-light
      div.card-header                 nom de l'entite (h2)
      div#countdown-header-bar        compte a rebours
      div.card-body.scrollable-content
        p.text-muted.mb-2             i.bi-calendar <DATE>  i.bi-eye <VUES>
        div.mb-3 > p  (x2)            description de l'annonce
        div#countdown-block
          div#countdown-link-block    NON LU : lien vers les donnees, affiche
                                      une fois le compte a rebours ecoule (CN-04)
      div.card-footer                 retour au blog

PAGINATION (reconnaissance VM, 11/09/2026) : a.page-link, lien ">>" (un
seul chevron) vers /?page=N ; ">>>>" (deux chevrons) mene a la derniere
page. Le listing n'etant pas date, la pagination s'arrete sur la date lue
par sonde sur la page de detail (DATE_SUR_DETAIL, cf. BaseConnector).
"""

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from app.connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)


class SafePayConnector(BaseConnector):
    SOURCE_NAME = "safepay"
    SOURCE_TYPE = "ransomware_site"

    TARGET_URL = "http://safepaypfxntwixwjrlcscft433ggemlhgkkdupi2ynhtcmvdgubmoyd.onion/"

    # Page de detail : seule source de la date de publication. Seules les
    # annonces NOUVELLES sont visitees, a raison d'une requete toutes les 30
    # a 45 s (FR-06) ; celles que le budget ne sert pas le sont au cycle
    # suivant. Les sondes de date (une par page de listing) s'y ajoutent.
    SUPPORTE_DETAIL = True
    MAX_DETAILS_PAR_RUN = 10

    SUPPORTE_PAGINATION = True
    DATE_SUR_DETAIL = True
    MAX_PAGES_LISTING = 30

    # Seule forme de lien verifiee comme page d'annonce (reconnaissance).
    PREFIXE_ANNONCE = "/blog/post/"


    def parse(self, raw_content):
        soup = BeautifulSoup(raw_content, "html.parser")

        entries = []
        cards = soup.select("div.card.bg-dark.text-light")

        for card in cards:
            nom_tag = card.select_one("h5.card-title")
            nom_entite = nom_tag.get_text(strip=True) if nom_tag else None

            flag_tag = card.select_one("img.country-flag")
            code_pays = flag_tag.get("alt") if flag_tag else None

            description_tag = card.select_one("p.card-text")
            description = description_tag.get_text(strip=True) if description_tag else None

            statut_tag = card.select_one(".published-text span")
            statut = statut_tag.get_text(strip=True) if statut_tag else None

            vues_tag = card.select_one(".badge.bg-secondary")
            vues = vues_tag.get_text(strip=True) if vues_tag else None

            lien_detail_tag = card.select_one("a.btn-primary")
            lien_detail = lien_detail_tag.get("href") if lien_detail_tag else None

            texte_complet = " ".join(filter(None, [nom_entite, description]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "code_pays": code_pays,
                "description": description,
                "statut": statut,
                "vues": vues,
                "lien_detail": lien_detail,
                "texte_brut": texte_complet,
            })

        logger.info(f"[safepay] {len(entries)} entree(s) trouvee(s) sur la page.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }


    def url_page_suivante(self, raw_content, page_courante):
        soup = BeautifulSoup(raw_content, "html.parser")
        for lien in soup.select("a.page-link"):
            if lien.get_text(strip=True) == "\u00bb":
                return self._page_suivante_validee(lien.get("href"), page_courante)
        return None

    def url_detail(self, entry):
        """
        Page d'annonce sur le domaine surveille, et SEULEMENT sous la forme
        verifiee /blog/post/<slug>/. Tout autre lien (domaine tiers, autre
        chemin) est refuse : CN-04, on ne visite que ce qui a ete qualifie.
        """
        chemin = self._chemin_interne(entry.get("lien_detail"))
        if not chemin or not chemin.startswith(self.PREFIXE_ANNONCE):
            return None
        racine = urlparse(self.TARGET_URL)
        return f"{racine.scheme}://{racine.netloc}{chemin}"

    def parse_detail(self, raw_content, entry):
        """
        Extrait la date de publication et la description de l'annonce.
        Le bloc #countdown-link-block n'est pas lu : il porte, une fois le
        compte a rebours ecoule, le lien vers les donnees divulguees.
        """
        soup = BeautifulSoup(raw_content, "html.parser")
        corps = soup.select_one("div.card-body")
        if corps is None:
            return {}

        # Le lien vers les donnees est retire AVANT toute lecture de texte.
        for bloc in corps.select("#countdown-block, #countdown-link-block"):
            bloc.decompose()

        description = " ".join(
            p.get_text(" ", strip=True) for p in corps.select("div.mb-3 p")
        )

        return {
            "date_publication": self._date_meta(corps),
            "texte_brut": self.nettoyer_urls(description),
        }

    @staticmethod
    def _date_meta(corps):
        """
        Texte situe entre l'icone calendrier et l'icone vues, dans la ligne
        de metadonnees : "<i class="bi-calendar"></i> DATE <i class="bi-eye"></i> VUES".
        """
        meta = corps.select_one("p.text-muted")
        icone = meta.select_one("i.bi-calendar") if meta else None
        if icone is None:
            return None

        morceaux = []
        for voisin in icone.next_siblings:
            if getattr(voisin, "name", None) == "i":
                break          # icone suivante (vues) : fin de la date
            texte = voisin.get_text(" ", strip=True) if hasattr(voisin, "get_text") else str(voisin)
            morceaux.append(texte)

        date = " ".join(" ".join(morceaux).split()).strip(" |·-,")
        return date or None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = SafePayConnector()
    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} entree(s) trouvee(s).")
        for i, entry in enumerate(data["entries"][:5], start=1):
            print(f"\n--- Entree {i} ---")
            print(f"  Nom detecte : {entry['nom_entite_detecte']}")
            print(f"  Pays : {entry['code_pays']}")
            print(f"  Statut : {entry['statut']}")
            print(f"  Vues : {entry['vues']}")
    else:
        print(f"[ECHEC] {result['error']}")
