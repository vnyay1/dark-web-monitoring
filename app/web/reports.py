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

from flask import Blueprint, Response, abort, request
from flask_login import login_required

from app.reports.monthly_report import erreur_de_periode, generer_rapport_html, generer_rapport_pdf
from app.reports.export import exporter_json, exporter_csv
from app.models import utc_now, RoleUtilisateur
from app.web.permissions import role_requis

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _mois_annee() -> tuple:
    """
    Mois et annee demandes, le mois courant par defaut (y compris pour une
    valeur non numerique, cf. type=int). Une periode invalide est refusee
    en 400, avec les memes bornes que l'API (erreur_de_periode).
    """
    maintenant = utc_now()
    mois = request.args.get("mois", maintenant.month, type=int)
    annee = request.args.get("annee", maintenant.year, type=int)
    erreur = erreur_de_periode(mois, annee)
    if erreur:
        abort(400, erreur)
    return mois, annee


@reports_bp.route("/monthly/html")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def monthly_html():
    mois, annee = _mois_annee()
    return Response(generer_rapport_html(mois, annee), mimetype="text/html")


@reports_bp.route("/monthly/pdf")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def monthly_pdf():
    mois, annee = _mois_annee()
    return Response(
        generer_rapport_pdf(mois, annee),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                f"attachment; filename=rapport_sentinel_{mois:02d}-{annee}.pdf"
        },
    )


@reports_bp.route("/export/json")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def export_json():
    return Response(
        exporter_json(),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=expositions_export.json"},
    )


@reports_bp.route("/export/csv")
@login_required
@role_requis(RoleUtilisateur.SUPERVISOR)
def export_csv():
    return Response(
        exporter_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=expositions_export.csv"},
    )
