"""
Diagnostic precis : pour UNE entree donnee, affiche le texte_brut complet,
puis CHAQUE match trouve (selecteur, type, segment, position), pour
identifier precisement quel selecteur cree le faux positif systemique.
"""

import logging
from app.db import get_session
from app.models import Selecteur
from app.matching.engine import match_text_against_catalogue
from app.connectors.payload_connector import PayloadConnector

logging.basicConfig(level=logging.WARNING)  # on coupe le bruit des logs INFO

session = get_session()
selecteurs = session.query(Selecteur).filter_by(actif=True).all()

connector = PayloadConnector()
result = connector.collect()

if not result["success"]:
    print(f"Echec collecte : {result['error']}")
else:
    entries = result["extracted_text"]["entries"]

    for i, entry in enumerate(entries, start=1):
        texte = entry.get("texte_brut", "")
        matches = match_text_against_catalogue(texte, selecteurs)

        if matches:
            print(f"\n{'='*70}")
            print(f"ENTREE {i} : {entry.get('nom_entite_detecte')}")
            print(f"TEXTE BRUT COMPLET : {texte}")
            print(f"{'-'*70}")
            for m in matches:
                print(f"  MATCH -> selecteur='{m.selecteur_valeur}' "
                      f"categorie={m.selecteur_categorie} "
                      f"type={m.type_correspondance} "
                      f"segment='{m.segment_trouve}' "
                      f"position={m.position} "
                      f"similarite={m.similarite:.1f}")

session.close()