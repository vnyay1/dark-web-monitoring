"""
FR-27 - Generation du rapport mensuel d'exposition (PDF et HTML).

Contient uniquement des statistiques agregees et une repartition par
categorie - AUCUNE donnee personnelle, conformement a l'exigence explicite
du cahier des charges. Le modele de donnees ne stocke de toute facon
jamais ce type d'information (CN-03/CN-04), donc ce rapport hérite
naturellement de cette garantie.
"""

import re
import logging
from pathlib import Path
from datetime import timedelta
from collections import Counter

from flask import render_template

from app import libelles
from app.config_system import get_config_int
from app.db import get_session
from app.models import (
    Exposition, NiveauCriticite, Source, SourceReference, StatutExposition, utc_now,
)

logger = logging.getLogger(__name__)

# Chemin absolu vers app/web/, calcule relativement a ce fichier
# (app/reports/monthly_report.py -> ../web/), donc independant du
# repertoire de travail courant et portable entre le poste Windows
# et la VM Kali.
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# url_for('static', filename=...) produit un chemin ABSOLU depuis la
# racine du serveur (ex. "/static/images/logo-antic.png"). Un chemin
# commencant par "/" est toujours resolu par WeasyPrint comme une
# racine filesystem absolue, quel que soit le format de base_url
# (chemin brut ou URI file://) - base_url ne peut donc structurellement
# pas influencer la resolution d'un tel chemin. Confirme empiriquement :
# le meme src, une fois rendu relatif (sans le "/" de tete), se resout
# correctement avec base_url pointant vers app/web/.
#
# Ce pattern ne cible que les attributs src="/static/..." (les guillemets
# font partie du pattern), donc aucun risque de toucher a autre chose
# qu'une reference a une ressource static Flask.
_STATIC_SRC_PATTERN = re.compile(r'src="/static/')
# Meme probleme pour les polices embarquees, referencees en CSS par
# url('/static/fonts/...').
_STATIC_URL_PATTERN = re.compile(r"url\((['\"]?)/static/")


def _rendre_chemins_static_relatifs(html_content: str) -> str:
    """
    Convertit src="/static/..." en src="static/..." dans le HTML,
    uniquement pour la generation PDF. Le HTML servi au navigateur
    (generer_rapport_html) n'est pas concerne : un navigateur resout
    correctement un chemin absolu via l'origine de la requete HTTP,
    ce qui n'est pas le cas de WeasyPrint utilise hors contexte de
    requete (HTML(string=...)).
    """
    html_content = _STATIC_SRC_PATTERN.sub('src="static/', html_content)
    return _STATIC_URL_PATTERN.sub(r"url(\1static/", html_content)


def collecter_statistiques_mensuelles(mois: int, annee: int) -> dict:
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

    # Une exposition compte dans CHACUNE de ses categories (FR-13) : le
    # total peut depasser le nombre d'expositions, ce que le document dit.
    repartition_categorie = Counter(
        c.nom for e in expositions_du_mois for c in e.categories
    )
    repartition_statut = Counter(
        e.statut.value for e in expositions_du_mois
    )

    # La criticite est un palier, pas une grandeur continue : une
    # "criticite moyenne" de 2,4 n'aurait aucun sens pour un lecteur du
    # rapport. On publie donc la REPARTITION par niveau, plus la part des
    # expositions de niveau eleve ou critique, qui est le chiffre que
    # l'encadrement regarde reellement.
    repartition_criticite = Counter(
        e.niveau_criticite.value for e in expositions_du_mois
    )
    niveaux_hauts = (NiveauCriticite.ELEVEE, NiveauCriticite.CRITIQUE)
    nb_niveaux_hauts = sum(1 for e in expositions_du_mois if e.niveau_criticite in niveaux_hauts)

    tries = sorted(
        expositions_du_mois,
        key=lambda e: (e.criticite, e.date_premiere_detection),
        reverse=True,
    )

    # Liste des entites concernees - nom d'entite/organisation uniquement,
    # jamais de donnee personnelle associee (conforme au modele CN-03/CN-04).
    # Les identifiants bruts (categorie, statut) restent pour l'interface
    # React, qui les traduit elle-meme ; les *_libelle servent au document.
    entites = [
        {
            "nom": e.nom_entite,
            "categories": [c.nom for c in e.categories],
            "criticite": e.criticite,
            "niveau_criticite": e.niveau_criticite.value,
            "niveau_libelle": libelles.libelle(libelles.NIVEAU, e.niveau_criticite),
            "sources": sorted({sr.source.nom for sr in e.sources if sr.source is not None}),
            "date_publication": (
                e.date_publication_source.strftime("%d/%m/%Y")
                if e.date_publication_source else None
            ),
            "statut": e.statut.value,
            "statut_libelle": libelles.libelle(libelles.STATUT, e.statut),
        }
        for e in tries
    ]

    # A traiter en priorite : niveau haut, pas encore qualifiee par un analyste.
    a_qualifier = (StatutExposition.NEW, StatutExposition.UNDER_REVIEW)
    priorites = [
        entite for entite, e in zip(entites, tries)
        if e.niveau_criticite in niveaux_hauts and e.statut in a_qualifier
    ][:8]

    # Deux categories les plus representees, et le nombre d'expositions
    # qui en relevent : compte sur les EXPOSITIONS, pas en additionnant les
    # deux effectifs, qui compteraient deux fois une exposition portant
    # les deux categories.
    categories_principales = [nom for nom, _ in repartition_categorie.most_common(2)]
    part_categories_principales = sum(
        1 for e in expositions_du_mois
        if any(c.nom in categories_principales for c in e.categories)
    )

    sources = _statistiques_sources(session, [e.id for e in expositions_du_mois])

    session.close()

    return {
        "mois": mois,
        "annee": annee,
        "periode_libelle": libelles.periode(mois, annee),
        "reference": f"SEN-RM-{annee}-{mois:02d}",
        "total_periode": total_periode,
        "repartition_criticite": dict(repartition_criticite),
        "nb_niveaux_hauts": nb_niveaux_hauts,
        "nb_a_qualifier": repartition_statut.get(StatutExposition.NEW.value, 0),
        "repartition_categorie": dict(repartition_categorie),
        "repartition_statut": dict(repartition_statut),
        "criticite": _paliers(repartition_criticite),
        "categories_principales": categories_principales,
        "part_categories_principales": part_categories_principales,
        "categories": repartition_categorie.most_common(),
        "statuts": [
            (libelles.STATUT[s.value], repartition_statut[s.value])
            for s in StatutExposition if repartition_statut.get(s.value)
        ],
        "sources": sources,
        "nb_sources_actives": sum(1 for s in sources if s["active"]),
        "nb_sources_signalantes": sum(1 for s in sources if s["signalements"]),
        "priorites": priorites,
        "entites": entites,
        "date_generation": utc_now(),
    }


def _paliers(repartition_criticite: Counter) -> list:
    """
    Les quatre paliers, du plus grave au plus faible, avec le nombre
    d'expositions et le seuil EN VIGUEUR - regle par l'administrateur, donc
    lu dans la configuration plutot qu'ecrit en dur dans le document.
    """
    moyenne = get_config_int("seuil_criticite_moyenne")
    elevee = get_config_int("seuil_criticite_elevee")
    critique = get_config_int("seuil_criticite_critique")

    def plage(bas, haut):
        pluriel = lambda n: "sélecteur" if n <= 1 else "sélecteurs"
        if haut is None:
            return f"{bas} {pluriel(bas)} et plus"
        if bas >= haut:
            return f"{bas} {pluriel(bas)}"
        return f"{bas} à {haut} sélecteurs"

    bornes = (
        (NiveauCriticite.CRITIQUE, critique, None),
        (NiveauCriticite.ELEVEE, elevee, critique - 1),
        (NiveauCriticite.MOYENNE, moyenne, elevee - 1),
        (NiveauCriticite.FAIBLE, 1, moyenne - 1),
    )
    return [
        {
            "niveau": niveau.value,
            "libelle": libelles.NIVEAU[niveau.value],
            "nombre": repartition_criticite.get(niveau.value, 0),
            "seuil": plage(bas, haut),
        }
        for niveau, bas, haut in bornes
    ]


def _statistiques_sources(session, ids_expositions: list) -> list:
    """
    Signalements de la periode par source, et combien la source a dates.
    Toutes les sources actives figurent, meme sans signalement : une source
    muette est une information pour le lecteur.
    """
    compte = Counter()
    dates = Counter()
    if ids_expositions:
        for sr in (
            session.query(SourceReference)
            .filter(SourceReference.exposition_id.in_(ids_expositions))
            .all()
        ):
            if sr.source_id:
                compte[sr.source_id] += 1
                dates[sr.source_id] += sr.date_publication is not None

    lignes = [
        {
            "nom": source.nom,
            "type": libelles.libelle(libelles.TYPE_SOURCE, source.type_source),
            "active": bool(source.actif),
            "signalements": compte.get(source.id, 0),
            "dates": dates.get(source.id, 0),
        }
        for source in session.query(Source).all()
        if source.actif or compte.get(source.id)
    ]
    return sorted(lignes, key=lambda l: (-l["signalements"], l["nom"]))


def generer_rapport_html(mois: int, annee: int) -> str:
    """Genere le rapport au format HTML (chaine de caracteres)."""
    stats = collecter_statistiques_mensuelles(mois, annee)
    return render_template("rapport_mensuel.html", **stats)


def generer_rapport_pdf(mois: int, annee: int) -> bytes:
    """
    Genere le rapport au format PDF, en memoire : les octets sont servis
    tels quels, sans fichier temporaire a nettoyer.
    """
    from weasyprint import HTML
    html_content = generer_rapport_html(mois, annee)
    html_content_pdf = _rendre_chemins_static_relatifs(html_content)
    pdf = HTML(string=html_content_pdf, base_url=str(_WEB_DIR)).write_pdf()
    logger.info(f"[reports] Rapport PDF genere ({mois:02d}/{annee}, {len(pdf)} octets).")
    return pdf