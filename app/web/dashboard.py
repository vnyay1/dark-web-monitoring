"""
FR-19 - Blueprint du tableau de bord analyste.

Affiche :
- nombre total d'expositions
- nouvelles expositions sur 7 jours / 30 jours
- repartition par secteur d'activite
- repartition par categorie de fuite
"""

from datetime import timedelta
from collections import Counter

from flask import Blueprint, render_template

from app.db import get_session
from app.models import Exposition, utc_now

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
def index():
    session = get_session()

    toutes_expositions = session.query(Exposition).all()

    total = len(toutes_expositions)

    seuil_7j = utc_now() - timedelta(days=7)
    seuil_30j = utc_now() - timedelta(days=30)

    nouvelles_7j = sum(1 for e in toutes_expositions if e.date_premiere_detection >= seuil_7j)
    nouvelles_30j = sum(1 for e in toutes_expositions if e.date_premiere_detection >= seuil_30j)

    # Repartition par secteur (le champ peut etre vide/None pour l'instant,
    # tant qu'aucune logique de deduction automatique du secteur n'existe)
    secteurs = Counter(
        (e.secteur_activite or "Non renseigne") for e in toutes_expositions
    )

    # Repartition par categorie de fuite
    categories = Counter(
        e.categorie_fuite.value for e in toutes_expositions
    )

    session.close()

    return render_template(
        "dashboard.html",
        total=total,
        nouvelles_7j=nouvelles_7j,
        nouvelles_30j=nouvelles_30j,
        secteurs=dict(secteurs),
        categories=dict(categories),
    )