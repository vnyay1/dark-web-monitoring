"""FR-08/FR-10 - Configuration systeme et catalogue de selecteurs."""

from flask import jsonify, request
from flask_login import current_user, login_required

from app.config_system import (
    VALEURS_PAR_DEFAUT, init_config_defaults, set_config, valider_valeur,
)
from app.db import get_session
from app.models import (
    CategorieSelecteur, ConfigurationSysteme, RoleUtilisateur, Selecteur,
)
from app.web.permissions import role_requis


def enregistrer(api_bp):

    @api_bp.route("/configuration", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def lire_configuration():
        init_config_defaults()
        session = get_session()
        try:
            lignes = (
                session.query(ConfigurationSysteme)
                .order_by(ConfigurationSysteme.cle)
                .all()
            )

            return jsonify({
                "configurations": [
                    {
                        "cle": c.cle,
                        "valeur": c.valeur,
                        "description": c.description,
                        # Le type pilote le champ de saisie cote interface :
                        # un menu deroulant pour un palier, un champ
                        # numerique sinon.
                        "type": VALEURS_PAR_DEFAUT.get(c.cle, (None, None, "int"))[2],
                    }
                    for c in lignes
                ],
                "modifiable": current_user.role == RoleUtilisateur.SUPER_ADMIN,
            })
        finally:
            session.close()

    @api_bp.route("/configuration/<cle>", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.SUPER_ADMIN)
    def modifier_configuration(cle):
        donnees = request.get_json(silent=True) or {}

        try:
            valeur = valider_valeur(cle, str(donnees.get("valeur", "")))
        except KeyError:
            return jsonify({
                "succes": False,
                "message": f"Cle de configuration inconnue : {cle}",
            }), 404
        except ValueError as erreur:
            return jsonify({"succes": False, "message": str(erreur)}), 400

        set_config(cle, valeur)
        return jsonify({"succes": True, "cle": cle, "valeur": valeur})

    @api_bp.route("/selecteurs", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def lire_selecteurs():
        session = get_session()
        try:
            lignes = (
                session.query(Selecteur)
                .order_by(Selecteur.categorie, Selecteur.valeur)
                .all()
            )
            return jsonify({
                "selecteurs": [
                    {
                        "id": s.id,
                        "valeur": s.valeur,
                        "categorie": s.categorie.value,
                        "actif": s.actif,
                        "propose_par_ner": s.propose_par_ner,
                        "valide_par_analyste": s.valide_par_analyste,
                    }
                    for s in lignes
                ],
                "categories": [c.value for c in CategorieSelecteur],
            })
        finally:
            session.close()

    @api_bp.route("/selecteurs", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def ajouter_selecteur():
        donnees = request.get_json(silent=True) or {}
        valeur = (donnees.get("valeur") or "").strip()

        if not valeur:
            return jsonify({"succes": False, "message": "Valeur requise."}), 400

        try:
            categorie = CategorieSelecteur(donnees.get("categorie"))
        except ValueError:
            return jsonify({"succes": False, "message": "Categorie inconnue."}), 400

        session = get_session()
        try:
            existant = (
                session.query(Selecteur)
                .filter_by(valeur=valeur, categorie=categorie)
                .first()
            )
            if existant:
                return jsonify({
                    "succes": False,
                    "message": f"Le selecteur '{valeur}' existe deja dans cette categorie.",
                }), 409

            selecteur = Selecteur(valeur=valeur, categorie=categorie, actif=True)
            session.add(selecteur)
            session.commit()

            return jsonify({
                "succes": True,
                "selecteur": {
                    "id": selecteur.id,
                    "valeur": selecteur.valeur,
                    "categorie": selecteur.categorie.value,
                    "actif": selecteur.actif,
                    "propose_par_ner": selecteur.propose_par_ner,
                    "valide_par_analyste": selecteur.valide_par_analyste,
                },
            })
        finally:
            session.close()

    @api_bp.route("/selecteurs/<selecteur_id>/basculer", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def basculer_selecteur(selecteur_id):
        session = get_session()
        try:
            selecteur = session.get(Selecteur, selecteur_id)
            if selecteur is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Selecteur inexistant.",
                }), 404

            selecteur.actif = not selecteur.actif
            session.commit()
            return jsonify({"succes": True, "actif": selecteur.actif})
        finally:
            session.close()
