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


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.FLASK_SECRET_KEY

    # Durcissement du cookie de session. SameSite=Lax empeche qu'il parte
    # lors d'une navigation declenchee par un site tiers : c'est la premiere
    # barriere CSRF, la seconde etant l'en-tete X-Requested-With exige par
    # la couche API.
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    init_db()

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

        return send_from_directory(RACINE_BUILD, "index.html")
