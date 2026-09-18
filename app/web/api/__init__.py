"""
Couche API JSON consommee par l'interface React.

POURQUOI DU JSON PARTOUT - une application monopage a besoin de codes de
statut et de JSON : une redirection 302 vers une page de connexion est
suivie en silence par fetch(), qui recoit alors du HTML la ou il attendait
des donnees, sans jamais voir qu'il n'etait pas authentifie. Seuls les
telechargements (app/web/reports.py, app/web/compliance.py) restent hors
de /api.

SECURITE - deux protections ajoutees au passage :

  1. Toute requete mutante doit porter l'en-tete X-Requested-With. Un
     formulaire CSRF classique ne peut pas le poser (seul XHR/fetch en est
     capable, et une requete inter-origine le declenche prealablement en
     preflight CORS). L'application n'avait aucune protection CSRF alors
     que tout passe par un cookie de session : la purge de conformite, le
     changement de role et le pilotage du scheduler etaient exposes.
  2. Les erreurs 401/403 sortent en JSON sous /api, jamais en HTML.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Methodes qui modifient l'etat du systeme et exigent donc l'en-tete.
METHODES_MUTANTES = ("POST", "PUT", "PATCH", "DELETE")


@api_bp.before_request
def exiger_entete_xhr():
    """
    Defense CSRF : un <form> malveillant sur un site tiers peut declencher
    un POST avec le cookie de session de la victime, mais ne peut pas y
    joindre un en-tete personnalise.
    """
    if request.method not in METHODES_MUTANTES:
        return None

    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify({
            "erreur": "requete_refusee",
            "message": "En-tete X-Requested-With manquant.",
        }), 403

    return None


def utilisateur_courant() -> dict:
    """Representation JSON de l'utilisateur connecte."""
    return {
        "id": current_user.id,
        "nom_utilisateur": current_user.nom_utilisateur,
        "role": current_user.role.value,
    }


def enregistrer_api(app):
    """Monte la couche API sur l'application Flask."""
    from app.web.api import (
        alerts,
        audit,
        auth,
        compliance,
        dashboard,
        expositions,
        reports,
        scheduler,
        settings,
        systeme,
        users,
    )

    for module in (auth, dashboard, expositions, alerts, scheduler,
                   settings, systeme, users, audit, compliance, reports):
        module.enregistrer(api_bp)

    app.register_blueprint(api_bp)

    _installer_gestionnaires_erreurs(app)


def _installer_gestionnaires_erreurs(app):
    """
    Fait repondre l'API en JSON la ou Flask-Login et abort() renvoient du
    HTML ou une redirection.
    """
    from app.web.auth import login_manager

    @login_manager.unauthorized_handler
    def non_authentifie():
        # Flask-Login redirige par defaut vers la page de connexion. Pour
        # l'API il faut un 401 franc, que le client React traduit en
        # retour a l'ecran de connexion.
        if request.path.startswith("/api/"):
            return jsonify({
                "erreur": "non_authentifie",
                "message": "Authentification requise.",
            }), 401

        # Hors API (telechargements /reports, /compliance) : retour a
        # l'ecran de connexion de l'interface React. Il n'existe plus de
        # page de connexion cote serveur vers laquelle rediriger.
        from flask import redirect
        return redirect("/connexion")

    @app.errorhandler(403)
    def interdit(erreur):
        if request.path.startswith("/api/"):
            return jsonify({
                "erreur": "acces_refuse",
                "message": "Privileges insuffisants pour cette action.",
            }), 403
        return erreur

    @app.errorhandler(404)
    def introuvable(erreur):
        if request.path.startswith("/api/"):
            return jsonify({
                "erreur": "introuvable",
                "message": "Ressource inexistante.",
            }), 404
        return erreur

    @app.errorhandler(500)
    def erreur_interne(erreur):
        if request.path.startswith("/api/"):
            logger.exception("[api] Erreur interne non rattrapee.")
            return jsonify({
                "erreur": "erreur_interne",
                "message": "Une erreur interne est survenue.",
            }), 500
        return erreur
