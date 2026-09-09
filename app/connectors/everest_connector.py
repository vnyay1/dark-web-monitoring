"""
FR-03 - Connecteur reel #8 : Everest (Laravel + Inertia.js + React).
STATUT : structure de page CATEGORIE confirmee et validee en conditions
reelles. Structure de la page D'ACCUEIL (liste des categories) non
encore confirmee - HOME_URL est une hypothese a valider.

Architecture particuliere : Laravel (backend) sert une page HTML unique
contenant tout le state de la page dans un bloc :

<script data-page="app" type="application/json">{...}</script>

Ce JSON est injecte cote SERVEUR avant tout rendu React - il n'est donc
PAS necessaire d'executer le JavaScript pour l'obtenir. Une simple
requete HTTP + extraction regex + json.loads suffit (pas de headless
browser necessaire).

Strategie de collecte :
1. Requete sur la page d'accueil -> extraction de props.categories
   (liste de toutes les victimes/sections connues)
2. Pour CHAQUE categorie, requete sur sa page individuelle
   -> extraction de props.active (infos victime) + props.posts
      (texte integral des annonces)

Rate limiting FR-06 INCHANGE : 30s minimum entre deux requetes sur
cette source. Le parcours multi-page (collecter_toutes_les_categories)
applique ce delai entre CHAQUE categorie visitee.

ATTENTION CN-04/OS-03 : certains posts contiennent des chemins de
fichiers internes tres detailles. Le texte est conserve TEL QUEL pour
le Matching Engine (recherche de mentions camerounaises), mais aucun
champ structure individuel (montants, identifiants clients, etc.)
n'est jamais extrait ou stocke separement - seul le texte brut sert de
base au matching.
"""

import re
import json
import logging

from app.connectors.base_connector import BaseConnector
from app.tor import get_via_tor

logger = logging.getLogger(__name__)


INERTIA_JSON_PATTERN = re.compile(
    r'<script\s+data-page="app"\s+type="application/json">(.*?)</script>',
    re.DOTALL
)


class EverestConnector(BaseConnector):
    SOURCE_NAME = "everest"
    SOURCE_TYPE = "ransomware_site"

    BASE_URL = "http://everestndkvzcibcje2cqxhre2hmmybl3rn2gwzwsblz7gx6uryn5rad.onion"
    HOME_URL = f"{BASE_URL}/" 

    def _extraire_json_inertia(self, raw_html: str) -> dict:
        """Extrait et parse le bloc JSON Inertia present dans le HTML brut."""
        match = INERTIA_JSON_PATTERN.search(raw_html)
        if not match:
            raise ValueError("Bloc JSON Inertia introuvable dans la page (structure inattendue).")
        return json.loads(match.group(1))

    def fetch(self):
        """
        Recupere UNIQUEMENT la page d'accueil (liste des categories).
        Le parcours des categories individuelles est gere separement
        par collecter_toutes_les_categories(), pas par ce fetch()
        standard, pour respecter le contrat BaseConnector (1 requete
        rate-limitee par appel a collect()).
        """
        response = get_via_tor(self.HOME_URL)
        return response.text

    def parse(self, raw_content):
        """
        Parse la page d'accueil : extrait la liste des categories
        connues (sans le detail des posts, disponible uniquement en
        visitant chaque page individuelle via
        collecter_toutes_les_categories()).
        """
        data = self._extraire_json_inertia(raw_content)
        categories = data.get("props", {}).get("categories", [])

        entries = []
        for cat in categories:
            entries.append({
                "nom_entite_detecte": cat.get("title"),
                "slug": cat.get("slug"),
                "nb_posts": cat.get("postCount"),
                "date": cat.get("date"),
                "verrouille": cat.get("locked"),
                "texte_brut": cat.get("title") or "",
            })

        logger.info(f"[everest] {len(entries)} categorie(s) trouvee(s) sur la page d'accueil.")

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
        }

    def parse_page_categorie(self, raw_content: str) -> dict:
        """
        Parse le contenu d'UNE page de categorie individuelle (ex:
        /news/cca-bank), en extrayant le texte integral des posts
        associes. STRUCTURE CONFIRMEE ET VALIDEE en conditions reelles.
        """
        data = self._extraire_json_inertia(raw_content)
        props = data.get("props", {})

        active = props.get("active", {})
        posts = props.get("posts", [])

        nom_entite = active.get("title")

        entries = []
        for post in posts:
            titre = post.get("title", "")
            body_lignes = post.get("body", [])
            texte_body = " ".join(body_lignes) if isinstance(body_lignes, list) else str(body_lignes)

            texte_complet = " ".join(filter(None, [nom_entite, titre, texte_body]))

            entries.append({
                "nom_entite_detecte": nom_entite,
                "titre_post": titre,
                "date_publication": post.get("date"),
                "requiert_mot_de_passe": post.get("requiresPassword"),
                "vues": post.get("views"),
                "texte_brut": texte_complet,
            })

        logger.info(
            f"[everest] Categorie '{nom_entite}' : {len(entries)} post(s) analyse(s)."
        )

        texte_global = "\n".join(e["texte_brut"] for e in entries)

        return {
            "entries": entries,
            "texte_global": texte_global,
            "nb_entries": len(entries),
            "categorie_slug": active.get("slug"),
        }

    def collecter_toutes_les_categories(self, categories_slugs: list) -> list:
        """
        Parcourt CHAQUE categorie individuellement, en respectant le
        rate limiting (30s min, FR-06) entre chaque requete.

        A appeler APRES un premier collect() qui aura recupere la
        liste des slugs depuis la page d'accueil.
        """
        tous_resultats = []

        for slug in categories_slugs:
            self._respect_rate_limit()  # FR-06 - 30s min entre CHAQUE categorie

            url_categorie = f"{self.BASE_URL}/news/{slug}"

            try:
                response = get_via_tor(url_categorie)
                resultat_page = self.parse_page_categorie(response.text)
                tous_resultats.append(resultat_page)
            except Exception as e:
                logger.error(f"[everest] Echec sur la categorie '{slug}' : {e}")
                continue

        return tous_resultats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    connector = EverestConnector()

    result = connector.collect()

    if result["success"]:
        data = result["extracted_text"]
        print(f"[OK] {data['nb_entries']} categorie(s) trouvee(s) sur la page d'accueil.")
        for e in data["entries"][:5]:
            print(f"  - {e['nom_entite_detecte']} (slug={e['slug']}, {e['nb_posts']} posts)")

        slugs = [e["slug"] for e in data["entries"] if e["slug"]]
        print(f"\n[INFO] Parcours de {len(slugs)} categories (rate limite a 30s/requete)...")

        resultats_categories = connector.collecter_toutes_les_categories(slugs)

        for r in resultats_categories:
            print(f"\n--- Categorie {r['categorie_slug']} ---")
            print(f"  {r['nb_entries']} post(s)")
            for entry in r["entries"]:
                print(f"    - Titre: {entry['titre_post']}")
                print(f"      Texte complet: {entry['texte_brut']}")
                print()
    else:
        print(f"[ECHEC page d'accueil] {result['error']}")