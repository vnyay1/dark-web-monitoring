"""
Factory Flask.

L'interface est une application React monopage (frontend/), servie par
Flask en production. Le serveur ne rend donc plus de pages : il expose une
API JSON (app/web/api/) et quelques TELECHARGEMENTS (rapports, exports),
qui restent des liens natifs pour conserver nom de fichier et progression
du navigateur.

Seul gabarit Jinja subsistant : rapport_mensuel.html, qui n'est pas une
page d'interface mais un document d'impression mis en page pour WeasyPrint.
"""

import base64
import hashlib
import re
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from app.config import Config
from app.db import init_db


# Build de l'interface React, produit par `npm run build`. Il est versionne :
# la VM de collecte n'a donc pas besoin de Node.
RACINE_BUILD = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Prefixes servis par Flask lui-meme. La route attrape-tout de l'application
# monopage ne doit jamais les intercepter.
PREFIXES_SERVEUR = ("api", "reports", "compliance", "assets", "static")

# Duree de validite d'une session d'analyste. Une session sans expiration
# reste exploitable indefiniment sur une VM laissee ouverte ; 8 heures
# couvrent une journee de travail sans reconnexion intempestive.
DUREE_SESSION = timedelta(hours=8)

# Scripts inline autorises par la CSP. index.html en contient un : le
# bootstrap de theme, qui doit s'executer avant le premier affichage pour ne
# pas montrer la page dans le mauvais theme.
#
# Son empreinte est CALCULEE AU DEMARRAGE a partir du build reel, et non
# recopiee en dur : un `npm run build` qui modifie ce bloc invaliderait
# silencieusement une empreinte figee, et le theme cesserait de s'appliquer
# sans que rien ne le signale.
def _empreintes_scripts_inline() -> list:
    index = RACINE_BUILD / "index.html"
    if not index.is_file():
        return []

    html = index.read_text(encoding="utf-8")
    empreintes = []
    for corps in re.findall(r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", html, re.DOTALL):
        condense = hashlib.sha256(corps.encode("utf-8")).digest()
        empreintes.append(f"'sha256-{base64.b64encode(condense).decode()}'")
    return empreintes


def _entetes_securite() -> dict:
    """
    En-tetes de securite poses sur TOUTE reponse.

    La CSP est la protection de fond contre le XSS : meme si un script
    etranger parvenait dans la page, le navigateur refuserait de l'executer.
    Deux assouplissements necessaires et assumes :
      - 'unsafe-inline' sur style-src : React et Recharts posent des attributs
        style= en ligne, et le gabarit d'impression a un bloc <style>. Il
        n'existe pas d'equivalent des empreintes pour les attributs style.
      - data: sur img-src : les graphiques utilisent des URI data:.
    script-src, lui, reste strict : 'self' plus les empreintes exactes des
    scripts inline du build, jamais 'unsafe-inline'.
    """
    script_src = " ".join(["'self'"] + _empreintes_scripts_inline())

    return {
        "Content-Security-Policy": (
            "default-src 'self'; "
            f"script-src {script_src}; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        ),
        # Empeche le navigateur de "deviner" un type MIME : un export CSV ne
        # doit jamais etre reinterprete comme du HTML executable.
        "X-Content-Type-Options": "nosniff",
        # Double de frame-ancestors, pour les navigateurs anciens (clickjacking).
        "X-Frame-Options": "DENY",
        # Aucune URL de l'application ne doit fuiter vers un site tiers.
        "Referrer-Policy": "no-referrer",
    }


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.FLASK_SECRET_KEY

    # Durcissement du cookie de session. SameSite=Lax empeche qu'il parte
    # lors d'une navigation declenchee par un site tiers : c'est la premiere
    # barriere CSRF, la seconde etant l'en-tete X-Requested-With exige par
    # la couche API.
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Pilote par .env : le deploiement actuel est en HTTP sur la VM, ou
    # marquer le cookie Secure couperait la connexion (cf. app/config.py).
    app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
    app.config["PERMANENT_SESSION_LIFETIME"] = DUREE_SESSION

    init_db()

    # Calcule une fois au demarrage : lire index.html a chaque reponse
    # couterait un acces disque par requete.
    entetes_securite = _entetes_securite()

    @app.after_request
    def poser_entetes_securite(reponse):
        # setdefault : une route qui aurait une raison de definir son propre
        # en-tete garde la main.
        for entete, valeur in entetes_securite.items():
            reponse.headers.setdefault(entete, valeur)
        return reponse

    from app.web.auth import login_manager
    from app.web.compliance import compliance_bp
    from app.web.reports import reports_bp

    login_manager.init_app(app)

    app.register_blueprint(reports_bp)
    app.register_blueprint(compliance_bp)

    from app.web.api import enregistrer_api
    enregistrer_api(app)

    _servir_interface_react(app)

    return app


def _servir_interface_react(app):
    """
    Sert l'application React.

    La route attrape-tout renvoie index.html pour toute URL inconnue : sans
    elle, rafraichir la page sur /expositions/<id> donnerait un 404, le
    routage etant assure cote navigateur.
    """
    if not RACINE_BUILD.exists():
        # En developpement, l'interface est servie par Vite (port 5173) qui
        # relaie /api vers Flask : l'absence de build n'est pas une erreur.
        @app.route("/")
        def build_absent():
            return jsonify({
                "message": (
                    "Interface non compilee. Lancez `npm run dev` dans "
                    "frontend/ (developpement) ou `npm run build` pour "
                    "generer frontend/dist (production)."
                ),
            }), 200

        return

    @app.route("/assets/<path:fichier>")
    def assets_react(fichier):
        return send_from_directory(RACINE_BUILD / "assets", fichier)

    @app.route("/", defaults={"chemin": ""})
    @app.route("/<path:chemin>")
    def interface_react(chemin):
        if chemin.split("/", 1)[0] in PREFIXES_SERVEUR:
            return jsonify({
                "erreur": "introuvable",
                "message": "Ressource inexistante.",
            }), 404

        # Un fichier reellement present dans le build (favicon, image...)
        # est servi tel quel ; tout le reste est une route React.
        fichier = RACINE_BUILD / chemin
        if chemin and fichier.is_file():
            return send_from_directory(RACINE_BUILD, chemin)

        # no-cache : le navigateur revalide index.html a chaque chargement, et
        # prend donc la nouvelle interface des qu'elle est deployee. Werkzeug
        # le pose deja par defaut ; l'expliciter protege index.html si un
        # SEND_FILE_MAX_AGE_DEFAULT est regle un jour pour les assets.
        reponse = send_from_directory(RACINE_BUILD, "index.html")
        reponse.headers["Cache-Control"] = "no-cache"
        return reponse
