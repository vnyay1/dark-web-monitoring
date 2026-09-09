"""
FR-20 - Blueprint de la liste des expositions avec recherche et filtres.
FR-21 - Modification du statut d'une exposition (inclus ici car couple a la liste).
"""

from datetime import timedelta
from flask_login import login_required
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.web.permissions import role_requis
from app.models import RoleUtilisateur

from app.db import get_session
from app.models import (
    Exposition, CategorieFuite, NiveauCriticite, StatutExposition, utc_now
)

expositions_bp = Blueprint("expositions", __name__, url_prefix="/expositions")


def _seuil_du_niveau(niveau: str) -> int:
    """
    Nombre minimum de selecteurs correspondant a un palier de criticite.
    Leve ValueError si le palier est inconnu (filtre alors ignore).
    """
    from app.config_system import get_config_int

    niveau = NiveauCriticite(niveau)

    if niveau == NiveauCriticite.CRITIQUE:
        return get_config_int("seuil_criticite_critique")
    if niveau == NiveauCriticite.ELEVEE:
        return get_config_int("seuil_criticite_elevee")
    if niveau == NiveauCriticite.MOYENNE:
        return get_config_int("seuil_criticite_moyenne")
    return 0

@expositions_bp.route("/")
@login_required
def liste():
    session = get_session()

    query = session.query(Exposition)

    # --- Filtre : secteur ---
    secteur = request.args.get("secteur", "").strip()
    if secteur:
        query = query.filter(Exposition.secteur_activite == secteur)

    # --- Filtre : categorie ---
    categorie = request.args.get("categorie", "").strip()
    if categorie:
        try:
            query = query.filter(Exposition.categorie_fuite == CategorieFuite(categorie))
        except ValueError:
            pass  # valeur invalide, filtre ignore silencieusement

    # --- Filtre : statut ---
    statut = request.args.get("statut", "").strip()
    if statut:
        try:
            query = query.filter(Exposition.statut == StatutExposition(statut))
        except ValueError:
            pass

    # --- Filtre : periode (nombre de jours) ---
    periode = request.args.get("periode", "").strip()
    if periode and periode.isdigit():
        seuil = utc_now() - timedelta(days=int(periode))
        query = query.filter(Exposition.date_premiere_detection >= seuil)

    # --- Filtre : niveau de criticite minimum ---
    #
    # NiveauCriticite est une enumeration de chaines : comparer en SQL
    # donnerait un ordre alphabetique ("critique" < "elevee" < "faible"),
    # sans rapport avec la gravite. On filtre donc sur criticite, l'entier
    # sous-jacent, en traduisant le palier demande par son seuil.
    niveau_min = request.args.get("niveau_min", "").strip()
    if niveau_min:
        try:
            query = query.filter(Exposition.criticite >= _seuil_du_niveau(niveau_min))
        except ValueError:
            pass

    # --- Recherche texte libre (nom de l'entite) ---
    recherche = request.args.get("q", "").strip()
    if recherche:
        query = query.filter(Exposition.nom_entite.ilike(f"%{recherche}%"))

    expositions = query.order_by(Exposition.date_premiere_detection.desc()).all()

    # Listes pour peupler les menus deroulants de filtre
    tous_secteurs = sorted(set(
        e.secteur_activite for e in session.query(Exposition).all()
        if e.secteur_activite
    ))

    resultat = render_template(
        "expositions_liste.html",
        expositions=expositions,
        tous_secteurs=tous_secteurs,
        toutes_categories=list(CategorieFuite),
        tous_niveaux=list(NiveauCriticite),
        tous_statuts=list(StatutExposition),
        filtres_actifs={
            "secteur": secteur,
            "categorie": categorie,
            "statut": statut,
            "periode": periode,
            "niveau_min": niveau_min,
            "q": recherche,
        },
    )

    session.close()
    return resultat


@expositions_bp.route("/<exposition_id>/statut", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def changer_statut(exposition_id):
    """FR-21 - Modification du statut d'une exposition par l'analyste."""
    session = get_session()

    exposition = session.query(Exposition).filter_by(id=exposition_id).first()

    if exposition is None:
        session.close()
        flash("Exposition introuvable.", "error")
        return redirect(url_for("expositions.liste"))

    nouveau_statut = request.form.get("statut")
    try:
        exposition.changer_statut(StatutExposition(nouveau_statut))
        session.commit()
        flash(f"Statut mis a jour : {nouveau_statut}", "success")
    except ValueError:
        flash("Statut invalide.", "error")

    session.close()
    return redirect(url_for("expositions.liste"))