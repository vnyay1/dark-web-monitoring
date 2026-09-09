"""
Export de conformite (telechargement).

L'ecran de conformite et la purge sont passes en React
(frontend/src/pages/Conformite.jsx + app/web/api/compliance.py). Seul
l'export reste ici : un lien natif telecharge le fichier avec son nom et
sa progression, la ou un fetch() devrait le reconstruire en memoire.
"""

from flask import Blueprint, Response
from flask_login import login_required

from app.models import RoleUtilisateur, utc_now
from app.reports.export import exporter_json
from app.web.permissions import role_requis

compliance_bp = Blueprint("compliance", __name__, url_prefix="/compliance")


@compliance_bp.route("/export-complet")
@login_required
@role_requis(RoleUtilisateur.SUPER_ADMIN)
def export_complet():
    """Export complet a des fins d'audit externe, avant purge eventuelle."""
    horodatage = utc_now().strftime("%Y%m%d_%H%M%S")
    return Response(
        exporter_json(),
        mimetype="application/json",
        headers={
            "Content-Disposition":
                f"attachment; filename=export_conformite_{horodatage}.json"
        },
    )
