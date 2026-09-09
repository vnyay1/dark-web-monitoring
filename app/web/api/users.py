"""
FR-24 - Gestion des comptes et des roles.

Les regles de privilege sont celles des blueprints Jinja, reprises telles
quelles : un compte ne peut pas se desactiver lui-meme, et seul un
super_admin agit sur un compte admin ou super_admin.
"""

from flask import jsonify, request
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from app.db import get_session
from app.models import HistoriqueRole, RoleUtilisateur, User
from app.web.permissions import role_requis
from app.securite import valider_mot_de_passe


def _serialiser(user) -> dict:
    return {
        "id": user.id,
        "nom_utilisateur": user.nom_utilisateur,
        "role": user.role.value,
        "actif": user.actif,
        "date_creation": user.date_creation.isoformat() if user.date_creation else None,
    }


def enregistrer(api_bp):

    @api_bp.route("/utilisateurs", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def liste_utilisateurs():
        session = get_session()
        try:
            utilisateurs = session.query(User).order_by(User.date_creation.desc()).all()
            return jsonify({
                "utilisateurs": [_serialiser(u) for u in utilisateurs],
                "roles": [r.value for r in RoleUtilisateur],
                "est_super_admin": current_user.role == RoleUtilisateur.SUPER_ADMIN,
                "moi": current_user.id,
            })
        finally:
            session.close()

    @api_bp.route("/utilisateurs", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def creer_utilisateur():
        donnees = request.get_json(silent=True) or {}
        nom = (donnees.get("nom_utilisateur") or "").strip()
        mot_de_passe = donnees.get("mot_de_passe") or ""

        if not nom:
            return jsonify({"succes": False, "message": "Nom d'utilisateur requis."}), 400

        valide, message = valider_mot_de_passe(mot_de_passe)
        if not valide:
            return jsonify({"succes": False, "message": message}), 400

        try:
            role = RoleUtilisateur(donnees.get("role", RoleUtilisateur.USER.value))
        except ValueError:
            role = RoleUtilisateur.USER

        # Contrairement au formulaire Jinja, qui retrogradait silencieusement
        # vers "user", on refuse explicitement : creer un compte avec un
        # privilege autre que celui demande est une surprise dangereuse.
        if role == RoleUtilisateur.SUPER_ADMIN and current_user.role != RoleUtilisateur.SUPER_ADMIN:
            return jsonify({
                "succes": False,
                "message": "Seul un super-administrateur peut creer un compte super-admin.",
            }), 403

        session = get_session()
        try:
            if session.query(User).filter_by(nom_utilisateur=nom).first():
                return jsonify({
                    "succes": False,
                    "message": "Cet utilisateur existe deja.",
                }), 409

            user = User(
                nom_utilisateur=nom,
                mot_de_passe_hash=generate_password_hash(mot_de_passe),
                role=role,
            )
            session.add(user)
            session.commit()

            return jsonify({"succes": True, "utilisateur": _serialiser(user)})
        finally:
            session.close()

    @api_bp.route("/utilisateurs/<user_id>/role", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def changer_role(user_id):
        donnees = request.get_json(silent=True) or {}

        try:
            nouveau_role = RoleUtilisateur(donnees.get("role"))
        except ValueError:
            return jsonify({"succes": False, "message": "Role invalide."}), 400

        session = get_session()
        try:
            user = session.get(User, user_id)
            if user is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Utilisateur introuvable.",
                }), 404

            if current_user.role != RoleUtilisateur.SUPER_ADMIN:
                if RoleUtilisateur.SUPER_ADMIN in (user.role, nouveau_role):
                    return jsonify({
                        "succes": False,
                        "message": (
                            "Seul un super-administrateur peut attribuer ou "
                            "modifier le role super-admin."
                        ),
                    }), 403

            if user.role != nouveau_role:
                session.add(HistoriqueRole(
                    user_cible_id=user.id,
                    modifie_par_id=current_user.id,
                    ancien_role=user.role,
                    nouveau_role=nouveau_role,
                ))

            user.role = nouveau_role
            session.commit()

            return jsonify({"succes": True, "utilisateur": _serialiser(user)})
        finally:
            session.close()

    @api_bp.route("/utilisateurs/<user_id>/basculer-actif", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def basculer_actif(user_id):
        session = get_session()
        try:
            user = session.get(User, user_id)
            if user is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Utilisateur introuvable.",
                }), 404

            # Empeche un verrouillage accidentel du systeme.
            if user.id == current_user.id:
                return jsonify({
                    "succes": False,
                    "message": "Vous ne pouvez pas desactiver votre propre compte.",
                }), 403

            cible_protegee = user.role in (RoleUtilisateur.ADMIN, RoleUtilisateur.SUPER_ADMIN)
            if cible_protegee and current_user.role != RoleUtilisateur.SUPER_ADMIN:
                return jsonify({
                    "succes": False,
                    "message": (
                        "Seul un super-administrateur peut activer ou desactiver "
                        "un compte admin ou super-admin."
                    ),
                }), 403

            user.actif = not user.actif
            session.commit()

            return jsonify({"succes": True, "utilisateur": _serialiser(user)})
        finally:
            session.close()

    @api_bp.route("/utilisateurs/historique-roles", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.SUPER_ADMIN)
    def historique_roles():
        session = get_session()
        try:
            entrees = (
                session.query(HistoriqueRole)
                .order_by(HistoriqueRole.date_modification.desc())
                .all()
            )

            # Un seul aller-retour pour les noms, plutot qu'une requete par
            # ligne d'historique.
            noms = {u.id: u.nom_utilisateur for u in session.query(User).all()}

            return jsonify({
                "entrees": [
                    {
                        "id": e.id,
                        "date_modification": e.date_modification.isoformat(),
                        "utilisateur_cible": noms.get(e.user_cible_id, "(compte supprime)"),
                        "modifie_par": noms.get(e.modifie_par_id, "(compte supprime)"),
                        "ancien_role": e.ancien_role.value if e.ancien_role else None,
                        "nouveau_role": e.nouveau_role.value if e.nouveau_role else None,
                    }
                    for e in entrees
                ],
            })
        finally:
            session.close()
