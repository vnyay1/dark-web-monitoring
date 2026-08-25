"""
Gestion des comptes utilisateurs - reserve aux roles admin et super_admin.
La modification du ROLE d'un utilisateur est reservee au super_admin uniquement,
sauf pour l'attribution/retrait du role super_admin qui reste strictement
reserve au super_admin (un admin peut modifier tout role SAUF super_admin).
"""

import re

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app.db import get_session
from app.models import User, RoleUtilisateur
from app.web.permissions import role_requis

users_bp = Blueprint("users", __name__, url_prefix="/users")


# ---------------------------------------------------------------------
# Politique de robustesse des mots de passe
# ---------------------------------------------------------------------

CARACTERES_SPECIAUX = r"!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`"
LONGUEUR_MINIMALE = 8


def valider_mot_de_passe(mot_de_passe: str) -> tuple:
    """
    Verifie qu'un mot de passe respecte la politique de robustesse :
    - au moins 8 caracteres
    - au moins une majuscule
    - au moins une minuscule
    - au moins un caractere special

    Retourne un tuple (valide: bool, message: str). Le message est vide
    si le mot de passe est valide, sinon il decrit la premiere regle
    non respectee.
    """
    if len(mot_de_passe) < LONGUEUR_MINIMALE:
        return False, f"Le mot de passe doit contenir au moins {LONGUEUR_MINIMALE} caracteres."

    if not re.search(r"[A-Z]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins une majuscule."

    if not re.search(r"[a-z]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins une minuscule."

    if not re.search(f"[{re.escape(CARACTERES_SPECIAUX)}]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins un caractere special."

    return True, ""


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------

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

    if not nom_utilisateur:
        flash("Nom d'utilisateur requis.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    mot_de_passe_valide, message_erreur = valider_mot_de_passe(mot_de_passe)
    if not mot_de_passe_valide:
        flash(message_erreur, "error")
        session.close()
        return redirect(url_for("users.liste"))

    existing = session.query(User).filter_by(nom_utilisateur=nom_utilisateur).first()
    if existing:
        flash("Cet utilisateur existe deja.", "error")
        session.close()
        return redirect(url_for("users.liste"))

    try:
        role_enum = RoleUtilisateur(role_demande)
    except ValueError:
        role_enum = RoleUtilisateur.USER

    # Seul un super_admin peut creer un compte super_admin
    if role_enum == RoleUtilisateur.SUPER_ADMIN and current_user.role != RoleUtilisateur.SUPER_ADMIN:
        flash("Seul un super-administrateur peut creer un compte super-admin.", "error")
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
        if user.role == RoleUtilisateur.SUPER_ADMIN or nouveau_role == RoleUtilisateur.SUPER_ADMIN:
            flash("Seul un super-administrateur peut attribuer ou modifier le role super-admin.", "error")
            session.close()
            return redirect(url_for("users.liste"))

    if user.role != nouveau_role:
        from app.models import HistoriqueRole
        historique = HistoriqueRole(
            user_cible_id=user.id,
            modifie_par_id=current_user.id,
            ancien_role=user.role,
            nouveau_role=nouveau_role,
        )
        session.add(historique)

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


@users_bp.route("/historique-roles")
@login_required
@role_requis(RoleUtilisateur.SUPER_ADMIN)
def historique_roles():
    from app.models import HistoriqueRole

    session = get_session()
    entries = session.query(HistoriqueRole).order_by(HistoriqueRole.date_modification.desc()).all()
    resultat = render_template("historique_roles.html", entries=entries)
    session.close()
    return resultat