"""
FR-28 - Export des indicateurs d'exposition en JSON et CSV.
"""

import csv
import json
import io
import logging

from app.db import get_session
from app.models import Exposition

logger = logging.getLogger(__name__)


def _exposition_vers_dict(exposition) -> dict:
    """Convertit une Exposition en dictionnaire exportable (CN-03/CN-04 compatible)."""
    return {
        "id": exposition.id,
        "nom_entite": exposition.nom_entite,
        "secteur_activite": exposition.secteur_activite,
        "type_entite": exposition.type_entite.value if exposition.type_entite else None,
        "categorie_fuite": exposition.categorie_fuite.value,
        "date_premiere_detection": exposition.date_premiere_detection.date().isoformat(),
        "date_derniere_detection": exposition.date_derniere_detection.date().isoformat(),
        "nombre_enregistrements_revendique": exposition.nombre_enregistrements_revendique,
        "score_confiance": exposition.score_confiance,
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

    for e in expositions:
        writer.writerow(_exposition_vers_dict(e))

    session.close()
    return output.getvalue()