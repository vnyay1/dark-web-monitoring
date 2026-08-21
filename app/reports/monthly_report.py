"""
FR-27 - Generation du rapport mensuel d'exposition (PDF et HTML).

Contient uniquement des statistiques agregees et une repartition par
secteur - AUCUNE donnee personnelle, conformement a l'exigence explicite
du cahier des charges. Le modele de donnees ne stocke de toute facon
jamais ce type d'information (CN-03/CN-04), donc ce rapport hérite
naturellement de cette garantie.
"""

import logging
from pathlib import Path
from datetime import timedelta
from collections import Counter

from weasyprint import HTML
from flask import render_template

from app.db import get_session
from app.models import Exposition, utc_now

logger = logging.getLogger(__name__)

# Chemin absolu vers app/web/, calcule relativement a ce fichier
# (app/reports/monthly_report.py -> ../web/), donc independant du
# repertoire de travail courant et portable entre le poste Windows
# et la VM Kali.
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _collecter_statistiques_mensuelles(mois: int, annee: int) -> dict:
    """
    Rassemble les statistiques agregees du mois donne, sans jamais
    exposer le detail nominatif au-dela du nom de l'entite elle-meme
    (qui n'est pas une donnee personnelle mais une entite organisationnelle).
    """
    session = get_session()

    debut_mois = utc_now().replace(year=annee, month=mois, day=1, hour=0, minute=0, second=0, microsecond=0)
    if mois == 12:
        fin_mois = debut_mois.replace(year=annee + 1, month=1)
    else:
        fin_mois = debut_mois.replace(month=mois + 1)

    expositions_du_mois = (
        session.query(Exposition)
        .filter(Exposition.date_premiere_detection >= debut_mois)
        .filter(Exposition.date_premiere_detection < fin_mois)
        .all()
    )

    total_periode = len(expositions_du_mois)

    repartition_secteur = Counter(
        (e.secteur_activite or "Non renseigne") for e in expositions_du_mois
    )
    repartition_categorie = Counter(
        e.categorie_fuite.value for e in expositions_du_mois
    )
    repartition_statut = Counter(
        e.statut.value for e in expositions_du_mois
    )

    score_moyen = (
        sum(e.score_confiance for e in expositions_du_mois) / total_periode
        if total_periode > 0 else 0.0
    )

    # Liste des entites concernees - nom d'entite/organisation uniquement,
    # jamais de donnee personnelle associee (conforme au modele CN-03/CN-04)
    entites = [
        {
            "nom": e.nom_entite,
            "secteur": e.secteur_activite or "Non renseigne",
            "categorie": e.categorie_fuite.value,
            "score": round(e.score_confiance, 2),
            "statut": e.statut.value,
        }
        for e in sorted(expositions_du_mois, key=lambda x: x.score_confiance, reverse=True)
    ]

    session.close()

    return {
        "mois": mois,
        "annee": annee,
        "total_periode": total_periode,
        "score_moyen": round(score_moyen, 2),
        "repartition_secteur": dict(repartition_secteur),
        "repartition_categorie": dict(repartition_categorie),
        "repartition_statut": dict(repartition_statut),
        "entites": entites,
        "date_generation": utc_now(),
    }


def generer_rapport_html(mois: int, annee: int) -> str:
    """Genere le rapport au format HTML (chaine de caracteres)."""
    stats = _collecter_statistiques_mensuelles(mois, annee)
    return render_template("rapport_mensuel.html", **stats)


def generer_rapport_pdf(mois: int, annee: int, chemin_sortie: str) -> str:
    """
    Genere le rapport au format PDF a partir du meme template HTML,
    via WeasyPrint. Retourne le chemin du fichier genere.

    Le parametre base_url est indispensable : le template utilise
    url_for('static', ...) qui produit une URL relative (ex.
    /static/images/logo-antic.png). Sans base_url, WeasyPrint n'a
    aucun moyen de resoudre ce chemin vers un fichier reel sur le
    disque et l'image (logo) est silencieusement ignoree.
    """
    html_content = generer_rapport_html(mois, annee)
    HTML(string=html_content, base_url=str(_WEB_DIR)).write_pdf(chemin_sortie)
    logger.info(f"[reports] Rapport PDF genere : {chemin_sortie}")
    return chemin_sortie