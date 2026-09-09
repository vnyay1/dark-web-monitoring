"""FR-24 - Authentification pour l'interface React (session Flask-Login)."""

from flask import jsonify, request
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.db import get_session
from app.models import User
from app.web.api import utilisateur_courant
from app.web.auth import AuthenticatedUser


def enregistrer(api_bp):

    @api_bp.route("/auth/connexion", methods=["POST"])
    def connexion():
        donnees = request.get_json(silent=True) or {}
        nom = (donnees.get("nom_utilisateur") or "").strip()
        mot_de_passe = donnees.get("mot_de_passe") or ""

        session = get_session()
        user = session.query(User).filter_by(nom_utilisateur=nom, actif=True).first()
        session.close()

        # Message volontairement identique que le compte n'existe pas, soit
        # desactive, ou que le mot de passe soit faux : distinguer les cas
        # revient a confirmer l'existence d'un compte a un attaquant.
        if not user or not check_password_hash(user.mot_de_passe_hash, mot_de_passe):
            return jsonify({
                "succes": False,
                "message": "Identifiants incorrects.",
            }), 401

        login_user(AuthenticatedUser(user))

        return jsonify({
            "succes": True,
            "utilisateur": {
                "id": user.id,
                "nom_utilisateur": user.nom_utilisateur,
                "role": user.role.value,
            },
        })

    @api_bp.route("/auth/deconnexion", methods=["POST"])
    @login_required
    def deconnexion():
        logout_user()
        return jsonify({"succes": True})

    @api_bp.route("/auth/moi", methods=["GET"])
    @login_required
    def moi():
        """Consulte au demarrage de l'application pour restaurer la session."""
        return jsonify(utilisateur_courant())
