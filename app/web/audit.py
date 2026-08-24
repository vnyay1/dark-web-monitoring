"""
Consultation du journal d'audit complet (FR-17) - reservee au super_admin.
"""

from flask import Blueprint, render_template, request
from flask_login import login_required

from app.db import get_session
from app.models import JournalAudit, Source, ResultatAudit, RoleUtilisateur
from app.web.permissions import role_requis

audit_bp = Blueprint("audit", __name__, url_prefix="/audit")


@audit_bp.route("/")
@login_required
@role_requis(RoleUtilisateur.SUPER_ADMIN)
def liste():
    session = get_session()

    query = session.query(JournalAudit).order_by(JournalAudit.horodatage.desc())

    resultat_filtre = request.args.get("resultat", "").strip()
    if resultat_filtre:
        try:
            query = query.filter(JournalAudit.resultat == ResultatAudit(resultat_filtre))
        except ValueError:
            pass

    source_filtre = request.args.get("source_id", "").strip()
    if source_filtre:
        query = query.filter(JournalAudit.source_id == source_filtre)

    entries = query.limit(500).all()  # limite raisonnable pour l'affichage

    toutes_sources = session.query(Source).order_by(Source.nom).all()

    resultat = render_template(
        "audit_liste.html",
        entries=entries,
        toutes_sources=toutes_sources,
        filtres_actifs={"resultat": resultat_filtre, "source_id": source_filtre},
    )
    session.close()
    return resultat