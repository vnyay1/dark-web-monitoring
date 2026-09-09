"""FR-25 - Alertes affichees dans l'interface analyste."""

from flask import jsonify
from flask_login import login_required

from app.db import get_session
from app.models import Alerte, CanalAlerte


LIMITE_ALERTES = 200


def enregistrer(api_bp):

    @api_bp.route("/alertes", methods=["GET"])
    @login_required
    def liste_alertes():
        session = get_session()
        try:
            # Seul le canal INTERFACE se liste ici : email, SMS et WhatsApp
            # sont des envois externes, pas des elements de l'interface.
            alertes = (
                session.query(Alerte)
                .filter(Alerte.canal == CanalAlerte.INTERFACE)
                .order_by(Alerte.date_creation.desc())
                .limit(LIMITE_ALERTES)
                .all()
            )

            return jsonify({
                "alertes": [
                    {
                        "id": a.id,
                        "lue": a.lue,
                        "statut_envoi": a.statut_envoi.value,
                        "date_creation": a.date_creation.isoformat(),
                        "exposition": {
                            "id": a.exposition.id,
                            "nom_entite": a.exposition.nom_entite,
                            "categorie_fuite": a.exposition.categorie_fuite.value,
                            "criticite": a.exposition.criticite,
                            "niveau_criticite": a.exposition.niveau_criticite.value,
                        } if a.exposition else None,
                    }
                    for a in alertes
                ],
                "non_lues": sum(1 for a in alertes if not a.lue),
            })
        finally:
            session.close()

    @api_bp.route("/alertes/<alerte_id>/marquer-lue", methods=["POST"])
    @login_required
    def marquer_lue(alerte_id):
        session = get_session()
        try:
            alerte = session.get(Alerte, alerte_id)
            if alerte is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Alerte inexistante.",
                }), 404

            alerte.lue = True
            session.commit()
            return jsonify({"succes": True})
        finally:
            session.close()

    @api_bp.route("/alertes/tout-marquer-lu", methods=["POST"])
    @login_required
    def tout_marquer_lu():
        session = get_session()
        try:
            nb = (
                session.query(Alerte)
                .filter(Alerte.canal == CanalAlerte.INTERFACE, Alerte.lue.is_(False))
                .update({"lue": True}, synchronize_session=False)
            )
            session.commit()
            return jsonify({"succes": True, "nb_marquees": nb})
        finally:
            session.close()
