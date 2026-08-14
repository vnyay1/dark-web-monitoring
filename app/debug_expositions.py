"""
Script de diagnostic - affiche le detail des expositions creees par le
pipeline, pour verifier si les detections sont pertinentes ou si le
Matching Engine remonte des faux positifs en masse (notamment sur Payload
qui a genere 18 expositions, ce qui semble suspect).
"""

from app.db import get_session
from app.models import Exposition, SourceReference

session = get_session()

expositions = session.query(Exposition).order_by(Exposition.date_premiere_detection.desc()).all()

print(f"Total expositions en base : {len(expositions)}\n")

for exp in expositions:
    sources = [sr.reference_source for sr in exp.sources]
    print(f"--- {exp.nom_entite} ---")
    print(f"  Categorie : {exp.categorie_fuite.value}")
    print(f"  Score confiance : {exp.score_confiance}")
    print(f"  Sources ({len(sources)}) : {sources[:2]}")
    print()

session.close()