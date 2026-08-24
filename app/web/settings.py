"""
Interface de configuration systeme.
- Catalogue de selecteurs (FR-08) : admin et super_admin
- Seuils d'alerte critiques (FR-25/FR-26) : super_admin uniquement
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.db import get_session
from app.models import ConfigurationSysteme, Selecteur, CategorieSelecteur, RoleUtilisateur
from app.config_system import init_config_defaults
from app.web.permissions import role_requis

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/")
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def index():
    init_config_defaults()
    session = get_session()

    configurations = session.query(ConfigurationSysteme).order_by(ConfigurationSysteme.cle).all()
    selecteurs = session.query(Selecteur).order_by(Selecteur.categorie, Selecteur.valeur).all()

    resultat = render_template(
        "settings_index.html",
        configurations=configurations,
        selecteurs=selecteurs,
        toutes_categories=list(CategorieSelecteur),
        peut_modifier_seuils=(current_user.role == RoleUtilisateur.SUPER_ADMIN),
    )
    session.close()
    return resultat


@settings_bp.route("/config/<cle>", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.SUPER_ADMIN)
def update_config(cle):
    from app.config_system import set_config

    valeur = request.form.get("valeur", "").strip()

    try:
        float(valeur)
    except ValueError:
        flash(f"Valeur invalide pour {cle} : doit etre un nombre.", "error")
        return redirect(url_for("settings.index"))

    set_config(cle, valeur)
    flash(f"Configuration '{cle}' mise a jour : {valeur}", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/selecteurs/ajouter", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def ajouter_selecteur():
    session = get_session()

    valeur = request.form.get("valeur", "").strip()
    categorie = request.form.get("categorie", "").strip()

    if not valeur or not categorie:
        flash("Valeur et categorie requises.", "error")
        session.close()
        return redirect(url_for("settings.index"))

    try:
        categorie_enum = CategorieSelecteur(categorie)
    except ValueError:
        flash("Categorie invalide.", "error")
        session.close()
        return redirect(url_for("settings.index"))

    existing = session.query(Selecteur).filter_by(valeur=valeur, categorie=categorie_enum).first()
    if existing:
        flash("Ce selecteur existe deja.", "error")
        session.close()
        return redirect(url_for("settings.index"))

    selecteur = Selecteur(valeur=valeur, categorie=categorie_enum, actif=True, valide_par_analyste=True)
    session.add(selecteur)
    session.commit()

    flash(f"Selecteur '{valeur}' ajoute.", "success")
    session.close()
    return redirect(url_for("settings.index"))


@settings_bp.route("/selecteurs/<selecteur_id>/toggle", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def toggle_selecteur(selecteur_id):
    session = get_session()
    selecteur = session.query(Selecteur).filter_by(id=selecteur_id).first()

    if selecteur:
        selecteur.actif = not selecteur.actif
        session.commit()
        flash(f"Selecteur '{selecteur.valeur}' {'active' if selecteur.actif else 'desactive'}.", "success")

    session.close()
    return redirect(url_for("settings.index"))