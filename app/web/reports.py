"""
FR-27/FR-28 - Generation de rapports et export de donnees.

Ne subsistent ici que les TELECHARGEMENTS. L'ecran de selection est passe
en React (frontend/src/pages/Rapports.jsx) ; ces routes restent servies par
Flask parce qu'un lien natif conserve le nom de fichier et la progression
du navigateur, ce que ne ferait pas un fetch() suivi d'une reconstruction
cote client.

Le rapport mensuel reste rendu par un gabarit Jinja
(app/web/templates/rapport_mensuel.html) : c'est un document d'impression
mis en page pour WeasyPrint, pas une page d'interface.
"""

from flask import Blueprint, send_file, Response, request
from flask_login import login_required

from app.reports.monthly_report import generer_rapport_html, generer_rapport_pdf
from app.reports.export import exporter_json, exporter_csv
from app.models import utc_now, RoleUtilisateur
from app.web.permissions import role_requis

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/monthly/html")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def monthly_html():
    mois = int(request.args.get("mois", utc_now().month))
    annee = int(request.args.get("annee", utc_now().year))
    html_content = generer_rapport_html(mois, annee)
    return Response(html_content, mimetype="text/html")


@reports_bp.route("/monthly/pdf")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def monthly_pdf():
    mois = int(request.args.get("mois", utc_now().month))
    annee = int(request.args.get("annee", utc_now().year))

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        chemin = generer_rapport_pdf(mois, annee, tmp.name)

    return send_file(
        chemin,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"rapport_sentinel_{mois:02d}-{annee}.pdf",
    )


@reports_bp.route("/export/json")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def export_json():
    data = exporter_json()
    return Response(
        data,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=expositions_export.json"},
    )


@reports_bp.route("/export/csv")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def export_csv():
    data = exporter_csv()
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=expositions_export.csv"},
    )