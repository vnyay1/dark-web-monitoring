"""
FR-25 - Blueprint d'affichage des alertes dans l'interface analyste.
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

from app.db import get_session
from app.models import Alerte, CanalAlerte

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alerts")


@alerts_bp.route("/")
@login_required
def liste():
    session = get_session()

    # Seules les alertes "interface" sont affichees ici (les autres
    # canaux - email/sms/whatsapp - sont des envois externes, pas des
    # elements a lister dans l'UI elle-meme)
    alertes = (
        session.query(Alerte)
        .filter(Alerte.canal == CanalAlerte.INTERFACE)
        .order_by(Alerte.date_creation.desc())
        .all()
    )

    resultat = render_template("alerts_liste.html", alertes=alertes)
    session.close()
    return resultat


@alerts_bp.route("/<alerte_id>/marquer-lue", methods=["POST"])
@login_required
def marquer_lue(alerte_id):
    session = get_session()
    alerte = session.query(Alerte).filter_by(id=alerte_id).first()

    if alerte:
        alerte.lue = True
        session.commit()

    session.close()
    return redirect(url_for("alerts.liste"))


def compter_alertes_non_lues() -> int:
    """Utilise par le template de base pour afficher le badge de compteur."""
    session = get_session()
    count = (
        session.query(Alerte)
        .filter(Alerte.canal == CanalAlerte.INTERFACE, Alerte.lue == False)
        .count()
    )
    session.close()
    return count