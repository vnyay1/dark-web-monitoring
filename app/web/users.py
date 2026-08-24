"""
Gestion des comptes utilisateurs - reserve aux roles admin et super_admin.
La modification du ROLE d'un utilisateur est reservee au super_admin uniquement.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app.db import get_session
from app.models import User, RoleUtilisateur
from app.web.permissions import role_requis

users_bp = Blueprint("users", __name__, url_prefix="/users")


@users_bp.route("/")
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def liste():
    session = get_session()
    utilisateurs = session.query(User).order_by(User.date_creation.desc()).all()
    resultat = render_template(
        "users_liste.html",
        utilisateurs=utilisateurs,
        tous_roles=list(RoleUtilisateur),
        peut_modifier_role=True,  # admin et super_admin arrivent tous deux ici (route protegee ADMIN+)
        est_super_admin=(current_user.role == RoleUtilisateur.SUPER_ADMIN),
    )
    session.close()
    return resultat


@users_bp.route("/creer", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def creer():
    session = get_session()

    nom_utilisateur = request.form.get("nom_utilisateur", "").strip()
    mot_de_passe = request.form.get("mot_de_passe", "")
    role_demande = request.form.get("role", RoleUtilisateur.USER.value)

    if not nom_utilisateur or len(mot_de_passe) < 8:
        flash("Nom d'utilisateur requis et mot de passe d'au moins 8 caracteres.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    existing = session.query(User).filter_by(nom_utilisateur=nom_utilisateur).first()
    if existing:
        flash("Cet utilisateur existe deja.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    # Seul un super_admin peut creer un compte super_admin ou admin
    try:
        role_enum = RoleUtilisateur(role_demande)
    except ValueError:
        role_enum = RoleUtilisateur.USER

    if role_enum in (RoleUtilisateur.ADMIN, RoleUtilisateur.SUPER_ADMIN) and current_user.role != RoleUtilisateur.SUPER_ADMIN:
        flash("Seul un super-administrateur peut attribuer ce role.", "error")
        role_enum = RoleUtilisateur.USER

    user = User(
        nom_utilisateur=nom_utilisateur,
        mot_de_passe_hash=generate_password_hash(mot_de_passe),
        role=role_enum,
    )
    session.add(user)
    session.commit()

    flash(f"Utilisateur '{nom_utilisateur}' cree avec le role {role_enum.value}.", "success")
    session.close()
    return redirect(url_for("users.liste"))


@users_bp.route("/<user_id>/role", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def changer_role(user_id):
    """
    Modification du role :
    - admin peut modifier le role de tout utilisateur SAUF un super_admin
      (ni le promouvoir vers super_admin, ni modifier un compte deja super_admin)
    - super_admin peut modifier n'importe quel role, y compris vers/depuis super_admin
    """
    session = get_session()
    user = session.query(User).filter_by(id=user_id).first()

    if user is None:
        flash("Utilisateur introuvable.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    nouveau_role_str = request.form.get("role")

    try:
        nouveau_role = RoleUtilisateur(nouveau_role_str)
    except ValueError:
        flash("Role invalide.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    if current_user.role != RoleUtilisateur.SUPER_ADMIN:
        # Un admin ne peut ni toucher a un compte deja super_admin,
        # ni promouvoir quelqu'un vers super_admin
        if user.role == RoleUtilisateur.SUPER_ADMIN or nouveau_role == RoleUtilisateur.SUPER_ADMIN:
            flash("Seul un super-administrateur peut attribuer ou modifier le role super-admin.", "error")
            session.close()
            return redirect(url_for("users.liste"))

    user.role = nouveau_role
    session.commit()
    flash(f"Role de '{user.nom_utilisateur}' mis a jour : {nouveau_role.value}.", "success")

    session.close()
    return redirect(url_for("users.liste"))


@users_bp.route("/<user_id>/toggle-actif", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def toggle_actif(user_id):
    """
    Active/desactive un compte. Regles de protection :
    - Un utilisateur ne peut pas se desactiver lui-meme (evite un
      verrouillage accidentel du systeme).
    - Seul un super_admin peut desactiver un compte admin ou super_admin
      (un admin ne peut agir que sur des comptes user/supervisor).
    """
    session = get_session()
    user = session.query(User).filter_by(id=user_id).first()

    if user is None:
        flash("Utilisateur introuvable.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    if user.id == current_user.id:
        flash("Vous ne pouvez pas desactiver votre propre compte.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    cible_est_protegee = user.role in (RoleUtilisateur.ADMIN, RoleUtilisateur.SUPER_ADMIN)
    if cible_est_protegee and current_user.role != RoleUtilisateur.SUPER_ADMIN:
        flash("Seul un super-administrateur peut activer/desactiver un compte admin ou super-admin.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    user.actif = not user.actif
    session.commit()
    flash(f"Compte '{user.nom_utilisateur}' {'active' if user.actif else 'desactive'}.", "success")

    session.close()
    return redirect(url_for("users.liste"))