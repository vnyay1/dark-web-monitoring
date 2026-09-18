"""FR-24 - Authentification pour l'interface React (session Flask-Login)."""

import logging

from flask import jsonify, request, session as session_flask
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.db import get_session
from app.models import JournalAudit, ResultatAudit, User
from app.web import limitation
from app.web.api import utilisateur_courant
from app.web.auth import AuthenticatedUser

logger = logging.getLogger(__name__)


def _journaliser_connexion(reussie: bool, nom: str) -> None:
    """
    FR-17 - Trace durable des acces. Seul le nom de COMPTE est ecrit : il
    figure deja dans la table users et n'est pas une donnee personnelle au
    sens de CN-04. Le mot de passe saisi, lui, n'est jamais journalise, meme
    tronque, meme en cas d'echec.
    """
    session = get_session()
    try:
        session.add(JournalAudit(
            source_id=None,  # nullable : evenement d'authentification, pas de collecte
            resultat=ResultatAudit.SUCCES if reussie else ResultatAudit.ECHEC,
            details=(
                f"Connexion reussie : {nom}" if reussie
                else f"Echec de connexion pour : {nom or '(nom vide)'}"
            ),
        ))
        session.commit()
    except Exception:
        # Un journal indisponible ne doit pas empecher de se connecter, mais
        # ne doit pas non plus passer inapercu cote serveur.
        session.rollback()
        logger.exception("[auth] Impossible de journaliser la tentative de connexion.")
    finally:
        session.close()


def enregistrer(api_bp):

    @api_bp.route("/auth/connexion", methods=["POST"])
    def connexion():
        donnees = request.get_json(silent=True) or {}
        nom = (donnees.get("nom_utilisateur") or "").strip()
        mot_de_passe = donnees.get("mot_de_passe") or ""
        ip = request.remote_addr

        # Frein anti-force brute AVANT toute verification : sans lui, le seul
        # cout d'un essai etait celui du hachage PBKDF2.
        secondes_restantes = limitation.est_bloque(nom, ip)
        if secondes_restantes:
            return jsonify({
                "succes": False,
                "message": (
                    f"Trop de tentatives echouees. Reessayez dans "
                    f"{secondes_restantes // 60 + 1} minute(s)."
                ),
            }), 429

        session = get_session()
        try:
            user = session.query(User).filter_by(nom_utilisateur=nom, actif=True).first()

            # Message volontairement identique que le compte n'existe pas, soit
            # desactive, ou que le mot de passe soit faux : distinguer les cas
            # revient a confirmer l'existence d'un compte a un attaquant.
            if not user or not check_password_hash(user.mot_de_passe_hash, mot_de_passe):
                limitation.enregistrer_echec(nom, ip)
                _journaliser_connexion(False, nom)
                return jsonify({
                    "succes": False,
                    "message": "Identifiants incorrects.",
                }), 401

            utilisateur = AuthenticatedUser(user)
            charge_utile = {
                "id": user.id,
                "nom_utilisateur": user.nom_utilisateur,
                "role": user.role.value,
            }
        finally:
            session.close()

        limitation.reinitialiser(nom, ip)
        login_user(utilisateur)

        # Sans session permanente, PERMANENT_SESSION_LIFETIME ne s'applique
        # pas : le cookie vivrait jusqu'a la fermeture du navigateur.
        session_flask.permanent = True

        _journaliser_connexion(True, charge_utile["nom_utilisateur"])

        return jsonify({
            "succes": True,
            "utilisateur": charge_utile,
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
