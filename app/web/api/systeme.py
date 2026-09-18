"""
Version du code executee par le serveur web et le scheduler, comparee au code
installe (cf. app.version).

Sert au bandeau de l'interface qui previent l'administrateur quand un
processus n'a pas ete redemarre apres un git pull : il executerait sinon
l'ancienne version sans que rien ne le signale.
"""

from flask import jsonify
from flask_login import login_required

from app import supervision
from app.models import RoleUtilisateur
from app.version import VERSION_AU_DEMARRAGE, version_du_code
from app.web.permissions import role_requis


def enregistrer(api_bp):

    @api_bp.route("/systeme/version", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def version_systeme():
        etat = supervision.etat_courant()
        return jsonify({
            # None hors depot git : aucune comparaison possible.
            "installee": version_du_code(),
            "web": VERSION_AU_DEMARRAGE,
            "scheduler_actif": etat["actif"],
            # None pour un scheduler EN MARCHE : il a ete demarre avant que
            # les versions soient enregistrees, il est donc forcement ancien.
            "scheduler": etat.get("version_code"),
        })
