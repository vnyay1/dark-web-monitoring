"""FR-08/FR-10 - Configuration systeme et catalogue de selecteurs."""

import logging

from flask import jsonify, request
from flask_login import current_user, login_required

from app.config_system import (
    VALEURS_PAR_DEFAUT, init_config_defaults, set_config, valider_valeur,
)
from app.db import get_session
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.models import (
    POIDS_MAXIMAL, POIDS_NORMAL, Categorie, ConfigurationSysteme, RoleUtilisateur,
    Selecteur, exposition_categories,
)
from app.web.permissions import role_requis

logger = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # Categories (FR-13) - gerees par l'administrateur. La liste, avec ses
    # compteurs, est servie avec le catalogue par GET /selecteurs.
    # ------------------------------------------------------------------

    @api_bp.route("/categories", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def creer_categorie():
        donnees = request.get_json(silent=True) or {}
        session = get_session()
        try:
            erreur = _valider_categorie(session, donnees)
            if erreur:
                return erreur

            categorie = Categorie(
                nom=donnees["nom"].strip(),
                description=(donnees.get("description") or "").strip() or None,
                lieu_generique=bool(donnees.get("lieu_generique")),
                prioritaire=bool(donnees.get("prioritaire")),
            )
            session.add(categorie)
            session.commit()
            logger.info(f"[catalogue] Categorie creee par '{current_user.nom_utilisateur}' : {categorie.nom!r}")
            return jsonify({"succes": True, "categorie": _serialiser_categorie(categorie)})
        finally:
            session.close()

    @api_bp.route("/categories/<categorie_id>", methods=["PUT"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def modifier_categorie(categorie_id):
        donnees = request.get_json(silent=True) or {}
        session = get_session()
        try:
            categorie = session.get(Categorie, categorie_id)
            if categorie is None:
                return _introuvable("Categorie inexistante.")

            erreur = _valider_categorie(session, donnees, exclure_id=categorie.id)
            if erreur:
                return erreur

            ancien_nom = categorie.nom
            categorie.nom = donnees["nom"].strip()
            categorie.description = (donnees.get("description") or "").strip() or None
            categorie.lieu_generique = bool(donnees.get("lieu_generique"))
            categorie.prioritaire = bool(donnees.get("prioritaire"))
            session.commit()

            logger.info(
                f"[catalogue] Categorie modifiee par '{current_user.nom_utilisateur}' : "
                f"{ancien_nom!r} -> {categorie.nom!r}"
            )
            return jsonify({"succes": True, "categorie": _serialiser_categorie(categorie)})
        finally:
            session.close()

    @api_bp.route("/categories/<categorie_id>", methods=["DELETE"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def supprimer_categorie(categorie_id):
        """
        Suppression d'une categorie. Si elle est utilisee, une categorie de
        REMPLACEMENT est obligatoire : ses selecteurs et les expositions qui
        la portaient y sont transferes. Rien n'est perdu - ni un selecteur
        du catalogue, ni la categorisation d'une exposition deja detectee.
        """
        donnees = request.get_json(silent=True) or {}
        session = get_session()
        try:
            categorie = session.get(Categorie, categorie_id)
            if categorie is None:
                return _introuvable("Categorie inexistante.")

            nb_selecteurs = session.query(Selecteur).filter_by(categorie_id=categorie.id).count()
            ids_expositions = [
                ligne[0] for ligne in session.execute(
                    exposition_categories.select()
                    .with_only_columns(exposition_categories.c.exposition_id)
                    .where(exposition_categories.c.categorie_id == categorie.id)
                )
            ]

            remplacement = None
            if nb_selecteurs or ids_expositions:
                remplacement_id = donnees.get("remplacement_id")
                if not remplacement_id:
                    return jsonify({
                        "succes": False,
                        "message": (
                            f"Cette categorie est utilisee par {nb_selecteurs} selecteur(s) "
                            f"et {len(ids_expositions)} exposition(s) : choisissez une "
                            f"categorie vers laquelle les transferer."
                        ),
                    }), 409
                remplacement = session.get(Categorie, remplacement_id)
                if remplacement is None or remplacement.id == categorie.id:
                    return jsonify({
                        "succes": False,
                        "message": "Categorie de remplacement invalide.",
                    }), 400

                # Selecteurs : simple changement de rattachement.
                (session.query(Selecteur)
                 .filter_by(categorie_id=categorie.id)
                 .update({"categorie_id": remplacement.id}, synchronize_session=False))

                # Expositions : transfert sans doublon - une exposition qui
                # portait deja la categorie de remplacement la garde une fois.
                deja = {
                    ligne[0] for ligne in session.execute(
                        exposition_categories.select()
                        .with_only_columns(exposition_categories.c.exposition_id)
                        .where(exposition_categories.c.categorie_id == remplacement.id)
                    )
                }
                a_ajouter = [i for i in ids_expositions if i not in deja]
                if a_ajouter:
                    session.execute(exposition_categories.insert(), [
                        {"exposition_id": i, "categorie_id": remplacement.id} for i in a_ajouter
                    ])

            session.execute(
                exposition_categories.delete()
                .where(exposition_categories.c.categorie_id == categorie.id)
            )
            nom = categorie.nom
            session.delete(categorie)
            session.commit()

            logger.warning(
                f"[catalogue] Categorie supprimee par '{current_user.nom_utilisateur}' : {nom!r}"
                + (f" ({nb_selecteurs} selecteur(s) et {len(ids_expositions)} exposition(s) "
                   f"transferes vers {remplacement.nom!r})" if remplacement else "")
            )
            return jsonify({
                "succes": True,
                "selecteurs_transferes": nb_selecteurs,
                "expositions_transferees": len(ids_expositions),
            })
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Selecteurs (FR-08)
    # ------------------------------------------------------------------

    @api_bp.route("/selecteurs", methods=["GET"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def lire_selecteurs():
        session = get_session()
        try:
            lignes = (
                session.query(Selecteur)
                .options(joinedload(Selecteur.categorie))
                .join(Categorie)
                .order_by(Categorie.nom, Selecteur.valeur)
                .all()
            )
            return jsonify({
                "selecteurs": [_serialiser_selecteur(s) for s in lignes],
                "categories": _categories_avec_compteurs(session),
            })
        finally:
            session.close()

    @api_bp.route("/selecteurs", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def ajouter_selecteur():
        donnees = request.get_json(silent=True) or {}
        session = get_session()
        try:
            valeur, categorie, erreur = _valider_selecteur(session, donnees)
            if erreur:
                return erreur
            poids, erreur = _valider_poids(donnees, defaut=POIDS_NORMAL)
            if erreur:
                return erreur

            selecteur = Selecteur(valeur=valeur, categorie=categorie, actif=True, poids=poids)
            session.add(selecteur)
            session.commit()

            return jsonify({"succes": True, "selecteur": _serialiser_selecteur(selecteur)})
        finally:
            session.close()

    @api_bp.route("/selecteurs/<selecteur_id>", methods=["PUT"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def modifier_selecteur(selecteur_id):
        """
        Modification de la valeur, de la categorie et/ou du poids d'un
        selecteur. Les expositions deja detectees gardent leurs categories
        et leur criticite : la modification vaut pour les collectes a venir.
        """
        donnees = request.get_json(silent=True) or {}
        session = get_session()
        try:
            selecteur = session.get(Selecteur, selecteur_id)
            if selecteur is None:
                return _introuvable("Selecteur inexistant.")

            valeur, categorie, erreur = _valider_selecteur(session, donnees, exclure_id=selecteur.id)
            if erreur:
                return erreur
            # Poids absent de la requete : il est conserve.
            poids, erreur = _valider_poids(donnees, defaut=selecteur.poids)
            if erreur:
                return erreur

            ancien, ancien_poids = selecteur.valeur, selecteur.poids
            selecteur.valeur = valeur
            selecteur.categorie = categorie
            selecteur.poids = poids
            session.commit()

            logger.info(
                f"[catalogue] Selecteur modifie par '{current_user.nom_utilisateur}' : "
                f"{ancien!r} -> {valeur!r} ({categorie.nom}), poids {ancien_poids} -> {poids}"
            )
            return jsonify({"succes": True, "selecteur": _serialiser_selecteur(selecteur)})
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
                return _introuvable("Selecteur inexistant.")

            selecteur.actif = not selecteur.actif
            session.commit()
            return jsonify({"succes": True, "actif": selecteur.actif})
        finally:
            session.close()

    @api_bp.route("/selecteurs/<selecteur_id>", methods=["DELETE"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def supprimer_selecteur(selecteur_id):
        """
        Suppression DEFINITIVE d'un selecteur du catalogue.

        Aucune table ne reference les selecteurs : les selecteurs trouves
        sont enregistres sur les signalements comme des VALEURS figees a la
        detection, et les categories d'une exposition lui sont attachees
        directement. Les expositions deja detectees ne sont donc pas
        affectees ; seules les collectes futures ne rechercheront plus ce
        terme. La desactivation reste l'alternative reversible.
        """
        session = get_session()
        try:
            selecteur = session.get(Selecteur, selecteur_id)
            if selecteur is None:
                return _introuvable("Selecteur inexistant.")

            valeur, categorie = selecteur.valeur, selecteur.categorie.nom
            session.delete(selecteur)
            session.commit()

            logger.warning(
                f"[catalogue] Selecteur supprime par '{current_user.nom_utilisateur}' : "
                f"{valeur!r} ({categorie})"
            )
            return jsonify({"succes": True, "valeur": valeur})
        finally:
            session.close()


# ----------------------------------------------------------------------
# Aides
# ----------------------------------------------------------------------

def _introuvable(message):
    return jsonify({"erreur": "introuvable", "message": message}), 404


def _serialiser_categorie(categorie, nb_selecteurs=None, nb_expositions=None) -> dict:
    donnees = {
        "id": categorie.id,
        "nom": categorie.nom,
        "description": categorie.description,
        "lieu_generique": categorie.lieu_generique,
        "prioritaire": categorie.prioritaire,
    }
    if nb_selecteurs is not None:
        donnees["nb_selecteurs"] = nb_selecteurs
        donnees["nb_expositions"] = nb_expositions
    return donnees


def _serialiser_selecteur(selecteur) -> dict:
    return {
        "id": selecteur.id,
        "valeur": selecteur.valeur,
        "categorie": {"id": selecteur.categorie.id, "nom": selecteur.categorie.nom},
        "actif": selecteur.actif,
        "poids": selecteur.poids,
    }


def _categories_avec_compteurs(session) -> list:
    """
    Categories, avec leur nombre de selecteurs et d'expositions : l'interface
    annonce ainsi l'effet d'une suppression AVANT de la demander.
    """
    selecteurs = dict(
        session.query(Selecteur.categorie_id, func.count()).group_by(Selecteur.categorie_id).all()
    )
    expositions = dict(session.execute(
        exposition_categories.select()
        .with_only_columns(exposition_categories.c.categorie_id, func.count())
        .group_by(exposition_categories.c.categorie_id)
    ).all())
    return [
        _serialiser_categorie(c, selecteurs.get(c.id, 0), expositions.get(c.id, 0))
        for c in session.query(Categorie).order_by(Categorie.nom).all()
    ]


def _valider_categorie(session, donnees, exclure_id=None):
    """Retourne une reponse d'erreur, ou None si les donnees sont valides."""
    nom = (donnees.get("nom") or "").strip()
    if not nom:
        return jsonify({"succes": False, "message": "Nom de categorie requis."}), 400
    if len(nom) > 100:
        return jsonify({"succes": False, "message": "Nom limite a 100 caracteres."}), 400

    # Unicite insensible a la casse : "banque" et "Banque" seraient deux
    # categories distinctes en base mais indiscernables a l'ecran.
    query = session.query(Categorie).filter(func.lower(Categorie.nom) == nom.lower())
    if exclure_id:
        query = query.filter(Categorie.id != exclure_id)
    if query.first():
        return jsonify({"succes": False, "message": f"La categorie {nom!r} existe deja."}), 409
    return None


def _valider_selecteur(session, donnees, exclure_id=None):
    """Retourne (valeur, categorie, erreur) ; erreur est None si tout va bien."""
    valeur = (donnees.get("valeur") or "").strip()
    if not valeur:
        return None, None, (jsonify({"succes": False, "message": "Valeur requise."}), 400)

    categorie = session.get(Categorie, donnees.get("categorie_id") or "")
    if categorie is None:
        return None, None, (jsonify({"succes": False, "message": "Categorie inconnue."}), 400)

    query = session.query(Selecteur).filter_by(valeur=valeur, categorie_id=categorie.id)
    if exclure_id:
        query = query.filter(Selecteur.id != exclure_id)
    if query.first():
        return None, None, (jsonify({
            "succes": False,
            "message": f"Le selecteur {valeur!r} existe deja dans la categorie {categorie.nom!r}.",
        }), 409)

    return valeur, categorie, None


def _valider_poids(donnees, defaut):
    """Retourne (poids, erreur) ; erreur est None si tout va bien."""
    brut = donnees.get("poids")
    if brut is None or brut == "":
        return defaut, None
    # bool est un int en Python : true ne doit pas passer pour un poids 1.
    if isinstance(brut, bool):
        brut = None
    try:
        poids = int(brut)
    except (TypeError, ValueError):
        poids = None
    if poids is None or not POIDS_NORMAL <= poids <= POIDS_MAXIMAL:
        return None, (jsonify({
            "succes": False,
            "message": f"Le poids est un entier de {POIDS_NORMAL} a {POIDS_MAXIMAL}.",
        }), 400)
    return poids, None
