"""
FR-27/FR-28 - Rapports et exports.

Seules les DONNEES du rapport transitent en JSON. Les fichiers eux-memes
(PDF, JSON, CSV) restent servis par le blueprint `reports`
(app/web/reports.py), en telechargement direct : les faire transiter par
fetch() puis les reconstruire cote navigateur n'apporterait rien et
casserait la barre de progression native du telechargement.
"""

from flask import jsonify, request
from flask_login import login_required

from app.models import RoleUtilisateur, utc_now
from app.reports.monthly_report import collecter_statistiques_mensuelles
from app.web.permissions import role_requis


def enregistrer(api_bp):

    @api_bp.route("/rapports/mensuel", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.SUPERVISOR)
    def rapport_mensuel():
        maintenant = utc_now()
        mois = request.args.get("mois", maintenant.month, type=int)
        annee = request.args.get("annee", maintenant.year, type=int)

        if not 1 <= mois <= 12:
            return jsonify({
                "succes": False,
                "message": "Mois invalide (1 a 12).",
            }), 400

        # Sans borne, datetime.replace(year=...) leve un ValueError non
        # rattrape (annee=0, annee negative, au-dela de 9999) et l'utilisateur
        # recoit une 500 la ou une saisie invalide merite une 400.
        if not 2000 <= annee <= 2100:
            return jsonify({
                "succes": False,
                "message": "Annee invalide (2000 a 2100).",
            }), 400

        donnees = collecter_statistiques_mensuelles(mois, annee)

        # date_generation est un datetime : il ne survit pas a jsonify tel quel.
        donnees["date_generation"] = donnees["date_generation"].isoformat()

        return jsonify(donnees)
