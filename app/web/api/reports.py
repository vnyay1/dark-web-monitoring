"""
FR-27/FR-28 - Rapports et exports.

Seules les DONNEES du rapport transitent en JSON. Les fichiers eux-memes
(PDF, JSON, CSV) restent servis par le blueprint Jinja `reports`, en
telechargement direct : les faire transiter par fetch() puis les
reconstruire cote navigateur n'apporterait rien et casserait la barre de
progression native du telechargement.
"""

from datetime import datetime

from flask import jsonify, request
from flask_login import login_required

from app.models import RoleUtilisateur
from app.reports.monthly_report import _collecter_statistiques_mensuelles
from app.web.permissions import role_requis


def enregistrer(api_bp):

    @api_bp.route("/rapports/mensuel", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.SUPERVISOR)
    def rapport_mensuel():
        maintenant = datetime.now()
        mois = request.args.get("mois", maintenant.month, type=int)
        annee = request.args.get("annee", maintenant.year, type=int)

        if not 1 <= mois <= 12:
            return jsonify({
                "succes": False,
                "message": "Mois invalide (1 a 12).",
            }), 400

        donnees = _collecter_statistiques_mensuelles(mois, annee)

        # date_generation est un datetime : il ne survit pas a jsonify tel quel.
        donnees["date_generation"] = donnees["date_generation"].isoformat()

        # Liens de telechargement, servis par le blueprint Jinja.
        donnees["telechargements"] = {
            "pdf": f"/reports/monthly/pdf?mois={mois}&annee={annee}",
            "html": f"/reports/monthly/html?mois={mois}&annee={annee}",
            "json": "/reports/export/json",
            "csv": "/reports/export/csv",
        }

        return jsonify(donnees)
