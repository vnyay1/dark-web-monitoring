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
from app.reports.monthly_report import collecter_statistiques_mensuelles, erreur_de_periode
from app.web.permissions import role_requis


def enregistrer(api_bp):

    @api_bp.route("/rapports/mensuel", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.SUPERVISOR)
    def rapport_mensuel():
        maintenant = utc_now()
        mois = request.args.get("mois", maintenant.month, type=int)
        annee = request.args.get("annee", maintenant.year, type=int)

        erreur = erreur_de_periode(mois, annee)
        if erreur:
            return jsonify({"succes": False, "message": erreur}), 400

        donnees = collecter_statistiques_mensuelles(mois, annee)

        # date_generation est un datetime : il ne survit pas a jsonify tel quel.
        donnees["date_generation"] = donnees["date_generation"].isoformat()

        return jsonify(donnees)
