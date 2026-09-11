"""FR-20/FR-21 - Expositions : liste filtrable, detail, changement de statut."""

from datetime import timedelta

from flask import jsonify, request
from flask_login import login_required

from app.config_system import get_config_int
from app.db import get_session
from app.models import (
    Categorie, Exposition, NiveauCriticite, RoleUtilisateur,
    StatutExposition, utc_now,
)
from app.web.permissions import role_requis


# Nombre maximum d'expositions renvoyees en une fois.
LIMITE_PAR_PAGE = 200


def seuil_du_niveau(niveau: NiveauCriticite) -> int:
    """
    Nombre minimum de selecteurs correspondant a un palier.

    On filtre sur `criticite` (l'entier) et non sur `niveau_criticite` :
    NiveauCriticite est une enumeration de chaines, dont l'ordre SQL serait
    alphabetique ("critique" < "elevee" < "faible") et sans rapport avec la
    gravite reelle.
    """
    if niveau == NiveauCriticite.CRITIQUE:
        return get_config_int("seuil_criticite_critique")
    if niveau == NiveauCriticite.ELEVEE:
        return get_config_int("seuil_criticite_elevee")
    if niveau == NiveauCriticite.MOYENNE:
        return get_config_int("seuil_criticite_moyenne")
    return 0


def _sources_de(exposition) -> list:
    """Signalements de l'exposition, un par source ou elle a ete vue."""
    return [
        {
            "id": sr.id,
            "nom_source": sr.source.nom if sr.source else None,
            "type_source": sr.type_source.value,
            "reference_source": sr.reference_source,
            "date_publication": (
                sr.date_publication.isoformat() if sr.date_publication else None
            ),
            "date_signalement": (
                sr.date_signalement.isoformat() if sr.date_signalement else None
            ),
        }
        for sr in exposition.sources
    ]


def serialiser(exposition, detaille: bool = False) -> dict:
    donnees = {
        "id": exposition.id,
        "nom_entite": exposition.nom_entite,
        # FR-13 : categories des selecteurs qui ont declenche l'exposition.
        "categories": [{"id": c.id, "nom": c.nom} for c in exposition.categories],
        "criticite": exposition.criticite,
        "niveau_criticite": exposition.niveau_criticite.value,
        "statut": exposition.statut.value,
        "date_premiere_detection": exposition.date_premiere_detection.isoformat(),
        "date_derniere_detection": exposition.date_derniere_detection.isoformat(),
        "date_publication_source": (
            exposition.date_publication_source.isoformat()
            if exposition.date_publication_source else None
        ),
        "nb_sources": len(exposition.sources),
        "sources": sorted({
            sr.source.nom for sr in exposition.sources if sr.source is not None
        }),
    }

    if detaille:
        donnees["signalements"] = _sources_de(exposition)

    return donnees


def enregistrer(api_bp):

    @api_bp.route("/expositions", methods=["GET"])
    @login_required
    def liste_expositions():
        session = get_session()
        try:
            query = session.query(Exposition)

            # Un filtre dont la valeur est invalide est ignore plutot que
            # rejete : l'interface ne doit pas casser sur un parametre
            # d'URL bricole a la main.
            categorie = request.args.get("categorie", "").strip()
            if categorie:
                query = query.filter(Exposition.categories.any(Categorie.id == categorie))

            statut = request.args.get("statut", "").strip()
            if statut:
                try:
                    query = query.filter(Exposition.statut == StatutExposition(statut))
                except ValueError:
                    pass

            niveau_min = request.args.get("niveau_min", "").strip()
            if niveau_min:
                try:
                    query = query.filter(
                        Exposition.criticite >= seuil_du_niveau(NiveauCriticite(niveau_min))
                    )
                except ValueError:
                    pass

            periode = request.args.get("periode", "").strip()
            if periode.isdigit():
                query = query.filter(
                    Exposition.date_premiere_detection >= utc_now() - timedelta(days=int(periode))
                )

            recherche = request.args.get("q", "").strip()
            if recherche:
                query = query.filter(Exposition.nom_entite.ilike(f"%{recherche}%"))

            total = query.count()
            lignes = (
                query.order_by(Exposition.date_premiere_detection.desc())
                .limit(LIMITE_PAR_PAGE)
                .all()
            )

            return jsonify({
                "expositions": [serialiser(e) for e in lignes],
                "total": total,
                "tronque": total > len(lignes),
                "referentiels": {
                    "categories": [
                        {"id": c.id, "nom": c.nom}
                        for c in session.query(Categorie).order_by(Categorie.nom)
                    ],
                    "statuts": [s.value for s in StatutExposition],
                    "niveaux": [n.value for n in NiveauCriticite],
                },
            })
        finally:
            session.close()

    @api_bp.route("/expositions/<exposition_id>", methods=["GET"])
    @login_required
    def detail_exposition(exposition_id):
        session = get_session()
        try:
            exposition = session.get(Exposition, exposition_id)
            if exposition is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Exposition inexistante.",
                }), 404
            return jsonify(serialiser(exposition, detaille=True))
        finally:
            session.close()

    @api_bp.route("/expositions/<exposition_id>/statut", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.SUPERVISOR)
    def changer_statut(exposition_id):
        donnees = request.get_json(silent=True) or {}

        try:
            nouveau_statut = StatutExposition(donnees.get("statut"))
        except ValueError:
            return jsonify({
                "succes": False,
                "message": "Statut inconnu.",
            }), 400

        session = get_session()
        try:
            exposition = session.get(Exposition, exposition_id)
            if exposition is None:
                return jsonify({
                    "erreur": "introuvable",
                    "message": "Exposition inexistante.",
                }), 404

            exposition.changer_statut(nouveau_statut)
            session.commit()

            return jsonify({"succes": True, "exposition": serialiser(exposition)})
        finally:
            session.close()
