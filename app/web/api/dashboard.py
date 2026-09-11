"""FR-19 - Tableau de bord analyste."""

from collections import Counter
from datetime import timedelta

from flask import jsonify
from flask_login import login_required

from app.db import get_session
from app.models import Exposition, NiveauCriticite, Source, StatutExposition, utc_now


def enregistrer(api_bp):

    @api_bp.route("/dashboard", methods=["GET"])
    @login_required
    def dashboard():
        session = get_session()
        try:
            expositions = session.query(Exposition).all()

            seuil_7j = utc_now() - timedelta(days=7)
            seuil_30j = utc_now() - timedelta(days=30)

            # Une exposition compte dans CHACUNE de ses categories : le
            # total de cette repartition peut depasser le nombre
            # d'expositions (precise a l'ecran).
            categories = Counter(c.nom for e in expositions for c in e.categories)
            criticites = Counter(e.niveau_criticite.value for e in expositions)
            statuts = Counter(e.statut.value for e in expositions)

            # Les paliers sont toujours presents, meme a zero : sans cela un
            # graphique verrait ses categories apparaitre et disparaitre au
            # fil des donnees, et changerait de couleurs d'un jour a l'autre.
            repartition_criticite = {
                niveau.value: criticites.get(niveau.value, 0)
                for niveau in NiveauCriticite
            }

            # Une source retiree reste en base (son journal d'audit en
            # depend) mais n'est plus surveillee : elle ne doit pas
            # apparaitre comme "injoignable".
            sources = session.query(Source).filter(Source.actif.is_(True)).all()

            return jsonify({
                "total": len(expositions),
                "nouvelles_7j": sum(
                    1 for e in expositions if e.date_premiere_detection >= seuil_7j
                ),
                "nouvelles_30j": sum(
                    1 for e in expositions if e.date_premiere_detection >= seuil_30j
                ),
                "a_traiter": sum(
                    1 for e in expositions
                    if e.statut in (StatutExposition.NEW, StatutExposition.UNDER_REVIEW)
                ),
                "niveaux_hauts": sum(
                    1 for e in expositions
                    if e.niveau_criticite in (NiveauCriticite.ELEVEE, NiveauCriticite.CRITIQUE)
                ),
                "repartition_categorie": dict(categories.most_common()),
                "repartition_criticite": repartition_criticite,
                "repartition_statut": dict(statuts.most_common()),
                "sources": [
                    {
                        "nom": s.nom,
                        "type_source": s.type_source.value,
                        "actif": s.actif,
                        "nombre_erreurs": s.nombre_erreurs,
                        "indisponible": s.est_indisponible(),
                        "derniere_collecte_reussie": (
                            s.derniere_collecte_reussie.isoformat()
                            if s.derniere_collecte_reussie else None
                        ),
                    }
                    for s in sorted(sources, key=lambda x: x.nom)
                ],
                "dernieres_expositions": [
                    {
                        "id": e.id,
                        "nom_entite": e.nom_entite,
                        "niveau_criticite": e.niveau_criticite.value,
                        "criticite": e.criticite,
                        "categories": [c.nom for c in e.categories],
                        "statut": e.statut.value,
                        "date_premiere_detection": e.date_premiere_detection.isoformat(),
                        "sources": sorted({
                            sr.source.nom for sr in e.sources if sr.source is not None
                        }),
                    }
                    for e in sorted(
                        expositions,
                        key=lambda x: x.date_premiere_detection,
                        reverse=True,
                    )[:8]
                ],
            })
        finally:
            session.close()
