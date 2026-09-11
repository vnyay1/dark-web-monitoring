"""
FR-28 - Export des indicateurs d'exposition en JSON et CSV.
"""

import csv
import json
import io
import logging

from app import libelles
from app.db import get_session
from app.models import Exposition

logger = logging.getLogger(__name__)


def _exposition_vers_dict(exposition) -> dict:
    """Convertit une Exposition en dictionnaire exportable (CN-03/CN-04 compatible)."""
    return {
        "id": exposition.id,
        "nom_entite": exposition.nom_entite,
        # Plusieurs categories possibles (FR-13) : jointes par " ; " pour
        # rester une seule colonne lisible dans un tableur.
        "categories": " ; ".join(c.nom for c in exposition.categories),
        "date_premiere_detection": exposition.date_premiere_detection.date().isoformat(),
        "date_derniere_detection": exposition.date_derniere_detection.date().isoformat(),
        "criticite": exposition.criticite,
        "niveau_criticite": exposition.niveau_criticite.value,
        "date_publication_source": (
            exposition.date_publication_source.date().isoformat()
            if exposition.date_publication_source else None
        ),
        "sources": ", ".join(sorted({
            sr.source.nom for sr in exposition.sources if sr.source is not None
        })),
        "statut": exposition.statut.value,
        "nb_sources": len(exposition.sources),
    }


def exporter_json() -> str:
    """FR-28 - Exporte toutes les expositions au format JSON (chaine)."""
    session = get_session()
    expositions = session.query(Exposition).all()

    data = [_exposition_vers_dict(e) for e in expositions]

    session.close()
    return json.dumps(data, indent=2, ensure_ascii=False)


def exporter_csv() -> str:
    """FR-28 - Exporte toutes les expositions au format CSV (chaine)."""
    session = get_session()
    expositions = session.query(Exposition).all()

    output = io.StringIO()

    if not expositions:
        session.close()
        return ""

    fieldnames = list(_exposition_vers_dict(expositions[0]).keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    # Le CSV s'ouvre dans un tableur, devant un lecteur humain : libelles
    # francais. Le JSON, format d'echange entre outils, garde les
    # identifiants techniques, stables et sans ambiguite.
    for e in expositions:
        ligne = _exposition_vers_dict(e)
        ligne["statut"] = libelles.libelle(libelles.STATUT, ligne["statut"])
        ligne["niveau_criticite"] = libelles.libelle(libelles.NIVEAU, ligne["niveau_criticite"])
        writer.writerow(ligne)

    session.close()
    return output.getvalue()