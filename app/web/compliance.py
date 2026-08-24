"""
Export et purge de conformite - reserves au super_admin.
La purge est IRREVERSIBLE : suppression definitive en base.
"""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user

from app.db import get_session
from app.models import Exposition, RoleUtilisateur, utc_now
from app.reports.export import exporter_json
from app.web.permissions import role_requis

logger = logging.getLogger(__name__)

compliance_bp = Blueprint("compliance", __name__, url_prefix="/compliance")


@compliance_bp.route("/")
@login_required
@role_requis(RoleUtilisateur.SUPER_ADMIN)
def index():
    session = get_session()
    total_expositions = session.query(Exposition).count()
    session.close()
    return render_template("compliance_index.html", total_expositions=total_expositions)


@compliance_bp.route("/export-complet")
@login_required
@role_requis(RoleUtilisateur.SUPER_ADMIN)
def export_complet():
    """Export complet a des fins d'audit externe, avant purge eventuelle."""
    data = exporter_json()
    horodatage = utc_now().strftime("%Y%m%d_%H%M%S")
    return Response(
        data,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=export_conformite_{horodatage}.json"},
    )


@compliance_bp.route("/purger", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.SUPER_ADMIN)
def purger():
    """
    Purge DEFINITIVE des expositions anterieures a une date donnee.
    Action irreversible - necessite une confirmation explicite du
    formulaire (checkbox) avant execution.
    """
    confirmation = request.form.get("confirmation")
    date_limite_str = request.form.get("date_limite", "").strip()

    if confirmation != "CONFIRMER":
        flash("Confirmation requise : tapez CONFIRMER pour valider la purge.", "error")
        return redirect(url_for("compliance.index"))

    if not date_limite_str:
        flash("Date limite requise.", "error")
        return redirect(url_for("compliance.index"))

    from datetime import datetime
    try:
        date_limite = datetime.strptime(date_limite_str, "%Y-%m-%d")
    except ValueError:
        flash("Format de date invalide.", "error")
        return redirect(url_for("compliance.index"))

    session = get_session()

    a_purger = session.query(Exposition).filter(Exposition.date_premiere_detection < date_limite).all()
    nb_purges = len(a_purger)

    for exposition in a_purger:
        session.delete(exposition)  # cascade vers SourceReference et Alerte (relations definies)

    session.commit()
    session.close()

    logger.warning(
        f"[compliance] PURGE effectuee par '{current_user.nom_utilisateur}' : "
        f"{nb_purges} exposition(s) anterieure(s) a {date_limite_str} supprimee(s) definitivement."
    )

    flash(f"{nb_purges} exposition(s) purgee(s) definitivement.", "success")
    return redirect(url_for("compliance.index"))