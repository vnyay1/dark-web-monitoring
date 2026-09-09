"""
Conformite : export integral et purge definitive (super_admin).

La purge est IRREVERSIBLE. Elle exige donc, en plus du role super_admin,
une confirmation explicite dans le corps de la requete : l'interface ne
peut pas la declencher par un simple clic mal place.
"""

import logging
from datetime import datetime

from flask import jsonify, request
from flask_login import current_user, login_required

from app.db import get_session
from app.models import Exposition, RoleUtilisateur
from app.web.permissions import role_requis

logger = logging.getLogger(__name__)

MOT_DE_CONFIRMATION = "CONFIRMER"


def enregistrer(api_bp):

    @api_bp.route("/conformite", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.SUPER_ADMIN)
    def etat_conformite():
        session = get_session()
        try:
            return jsonify({
                "total_expositions": session.query(Exposition).count(),
                "mot_de_confirmation": MOT_DE_CONFIRMATION,
            })
        finally:
            session.close()

    @api_bp.route("/conformite/pre-purge", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.SUPER_ADMIN)
    def pre_purge():
        """
        Compte ce qu'une purge supprimerait, sans rien supprimer.

        L'ancien formulaire faisait decouvrir l'ampleur des degats APRES
        coup, dans un message de confirmation. Pour une action irreversible,
        le chiffre doit etre connu avant.
        """
        date_limite = _lire_date(request.args.get("date_limite", ""))
        if date_limite is None:
            return jsonify({
                "succes": False,
                "message": "Date limite invalide (format attendu : AAAA-MM-JJ).",
            }), 400

        session = get_session()
        try:
            nb = (
                session.query(Exposition)
                .filter(Exposition.date_premiere_detection < date_limite)
                .count()
            )
            return jsonify({"nb_concernees": nb, "date_limite": date_limite.date().isoformat()})
        finally:
            session.close()

    @api_bp.route("/conformite/purger", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.SUPER_ADMIN)
    def purger():
        donnees = request.get_json(silent=True) or {}

        if donnees.get("confirmation") != MOT_DE_CONFIRMATION:
            return jsonify({
                "succes": False,
                "message": f"Confirmation requise : saisissez {MOT_DE_CONFIRMATION}.",
            }), 400

        date_limite = _lire_date(donnees.get("date_limite", ""))
        if date_limite is None:
            return jsonify({
                "succes": False,
                "message": "Date limite invalide (format attendu : AAAA-MM-JJ).",
            }), 400

        session = get_session()
        try:
            a_purger = (
                session.query(Exposition)
                .filter(Exposition.date_premiere_detection < date_limite)
                .all()
            )
            nb = len(a_purger)

            for exposition in a_purger:
                # Suppression en cascade vers SourceReference et Alerte.
                session.delete(exposition)

            session.commit()

            logger.warning(
                f"[conformite] PURGE par '{current_user.nom_utilisateur}' : "
                f"{nb} exposition(s) anterieure(s) a {date_limite.date()} "
                f"supprimee(s) definitivement."
            )

            return jsonify({"succes": True, "nb_purgees": nb})
        finally:
            session.close()


def _lire_date(valeur: str):
    try:
        return datetime.strptime((valeur or "").strip(), "%Y-%m-%d")
    except ValueError:
        return None
