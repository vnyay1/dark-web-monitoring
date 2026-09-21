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

Strategie de collecte, desormais portee par le contrat BaseConnector :
1. LISTING - page d'accueil -> props.categories (une entree par victime)
2. DETAIL  - pour chaque categorie NOUVELLE et dans la limite du budget,
   sa page /news/{slug} -> props.active + props.posts (texte integral)

C'est la phase de detail qui porte toute la valeur : la page d'accueil ne
donne que le TITRE d'une categorie, bien trop pauvre pour que le Matching
Engine reconnaisse une entite camerounaise.

Chaque categorie = une victime = une Exposition. Les posts d'une meme
categorie sont donc concatenes en un seul texte, et non transformes en
autant d'entrees distinctes.

ATTENTION CN-04/OS-03 : certains posts contiennent des chemins de
fichiers internes tres detailles. Le texte alimente le Matching Engine en
memoire uniquement (CN-05) et aucun champ structure individuel (montants,
identifiants clients) n'est extrait ni stocke. Les URL presentes dans les
posts sont retirees avant conservation.
"""

import re
import json
import logging

from app.connectors.base_connector import BaseConnector

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

    # Le pipeline enregistre TARGET_URL comme url_ou_identifiant de la Source
    # et comme reference_source de repli. Sans lui, everest enregistrait
    # litteralement "unknown" en base.
    TARGET_URL = HOME_URL

    # La page d'accueil liste toutes les categories en une requete : pas de
    # pagination a gerer, seulement des pages de detail a visiter.
    SUPPORTE_DETAIL = True
    MAX_DETAILS_PAR_RUN = 20

    def _extraire_json_inertia(self, raw_html: str) -> dict:
        """Extrait et parse le bloc JSON Inertia present dans le HTML brut."""
        match = INERTIA_JSON_PATTERN.search(raw_html)
        if not match:
            raise ValueError("Bloc JSON Inertia introuvable dans la page (structure inattendue).")
        return json.loads(match.group(1))

    def parse(self, raw_content):
        """
        Parse la page d'accueil : liste des categories connues. Le texte
        disponible ici se limite au titre - le contenu reel est recupere
        par parse_detail().
        """
        data = self._extraire_json_inertia(raw_content)
        categories = data.get("props", {}).get("categories", [])

        entries = []
        for cat in categories:
            slug = cat.get("slug")
            entries.append({
                "nom_entite_detecte": cat.get("title"),
                "slug": slug,
                # Expose le chemin de la page de publication sous la cle
                # commune : identifiant_entree et reference_source du
                # pipeline s'en servent alors sans traitement particulier.
                "lien_detail": f"/news/{slug}" if slug else None,
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

    def url_detail(self, entry):
        """
        Page de publication de la categorie, sur le domaine surveille
        lui-meme. CN-04 : c'est l'annonce, jamais un lien vers les donnees.
        """
        lien = entry.get("lien_detail")
        return f"{self.BASE_URL}{lien}" if lien else None

    def signature_listing(self, entry):
        """
        La page d'accueil annonce, par categorie, son nombre de posts
        (postCount) et sa date. Une categorie qui gagne un post voit donc sa
        signature changer, et sa page /news/<slug> est relue au cycle
        suivant meme si elle est deja TRAITEE.

        CN-03/CN-04 : un compteur et une date, rien d'autre - ni le titre de
        la categorie (qui nommerait la victime), ni le moindre extrait.
        """
        return self.empreinte_signature(entry.get("nb_posts"), entry.get("date"))

    def parse_detail(self, raw_content, entry):
        """
        Parse UNE page de categorie (ex: /news/cca-bank) et concatene le
        texte integral de tous ses posts.
        STRUCTURE CONFIRMEE ET VALIDEE en conditions reelles.
        """
        data = self._extraire_json_inertia(raw_content)
        props = data.get("props", {})

        active = props.get("active", {})
        posts = props.get("posts", [])
        nom_entite = active.get("title")

        morceaux = [nom_entite]
        for post in posts:
            morceaux.append(post.get("title", ""))
            body = post.get("body", [])
            morceaux.append(" ".join(body) if isinstance(body, list) else str(body))

        logger.info(f"[everest] Categorie '{nom_entite}' : {len(posts)} post(s) analyse(s).")

        return {
            "nom_entite_detecte": nom_entite,
            "nb_posts_analyses": len(posts),
            "date_publication": posts[0].get("date") if posts else None,
            "texte_brut": self.nettoyer_urls(" ".join(filter(None, morceaux))),
        }
