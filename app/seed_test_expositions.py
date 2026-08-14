"""
Script de test UNIQUEMENT - insere des expositions fictives en base pour
valider visuellement le dashboard (FR-19) et la liste/filtres (FR-20).

A NE JAMAIS EXECUTER sur une base contenant de vraies donnees collectees -
sert uniquement au developpement de l'interface.
"""

import logging
from datetime import timedelta

from app.db import get_session, init_db
from app.models import (
    Exposition, SourceReference, TypeEntite, CategorieFuite,
    StatutExposition, TypeSource, utc_now
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TEST_DATA = [
    {
        "nom_entite": "MINFI (Ministere des Finances)",
        "secteur_activite": "Administration publique",
        "type_entite": TypeEntite.PUBLIQUE,
        "categorie_fuite": CategorieFuite.CREDENTIALS,
        "score_confiance": 0.87,
        "statut": StatutExposition.NEW,
        "jours_ecoules": 2,
        "nb_enregistrements": 15000,
        "source_type": TypeSource.RANSOMWARE_SITE,
        "source_ref": "http://payload.onion/posts/abc123",
    },
    {
        "nom_entite": "Afriland First Bank",
        "secteur_activite": "Finance",
        "type_entite": TypeEntite.PRIVEE,
        "categorie_fuite": CategorieFuite.DONNEES_FINANCIERES,
        "score_confiance": 0.72,
        "statut": StatutExposition.UNDER_REVIEW,
        "jours_ecoules": 5,
        "nb_enregistrements": 8200,
        "source_type": TypeSource.FORUM,
        "source_ref": "http://cmd-org.onion/entity/xyz",
    },
    {
        "nom_entite": "Universite de Yaounde I",
        "secteur_activite": "Education",
        "type_entite": TypeEntite.PUBLIQUE,
        "categorie_fuite": CategorieFuite.DONNEES_PERSONNELLES,
        "score_confiance": 0.45,
        "statut": StatutExposition.NEW,
        "jours_ecoules": 12,
        "nb_enregistrements": 3400,
        "source_type": TypeSource.PASTE,
        "source_ref": "http://safepay.onion/blog/post/uy1",
    },
    {
        "nom_entite": "MTN Cameroon",
        "secteur_activite": "Telecommunications",
        "type_entite": TypeEntite.PRIVEE,
        "categorie_fuite": CategorieFuite.DOCUMENTS_INTERNES,
        "score_confiance": 0.91,
        "statut": StatutExposition.CONFIRMED,
        "jours_ecoules": 1,
        "nb_enregistrements": None,
        "source_type": TypeSource.RANSOMWARE_SITE,
        "source_ref": "http://blackwater.onion/blog?uuid=mtn1",
    },
    {
        "nom_entite": "CAMTEL",
        "secteur_activite": "Telecommunications",
        "type_entite": TypeEntite.PUBLIQUE,
        "categorie_fuite": CategorieFuite.CODE_SOURCE,
        "score_confiance": 0.38,
        "statut": StatutExposition.FALSE_POSITIVE,
        "jours_ecoules": 20,
        "nb_enregistrements": None,
        "source_type": TypeSource.RANSOMWARE_SITE,
        "source_ref": "http://orionleaks.onion/news/article?id=99",
    },
    {
        "nom_entite": "SONARA",
        "secteur_activite": "Energie",
        "type_entite": TypeEntite.PUBLIQUE,
        "categorie_fuite": CategorieFuite.DOCUMENTS_INTERNES,
        "score_confiance": 0.68,
        "statut": StatutExposition.NOTIFIED,
        "jours_ecoules": 40,
        "nb_enregistrements": 500,
        "source_type": TypeSource.RANSOMWARE_SITE,
        "source_ref": "http://dataexposurelogs.onion/entity/sonara1",
    },
    {
        "nom_entite": "Ecobank Cameroun",
        "secteur_activite": "Finance",
        "type_entite": TypeEntite.PRIVEE,
        "categorie_fuite": CategorieFuite.DONNEES_FINANCIERES,
        "score_confiance": 0.79,
        "statut": StatutExposition.CLOSED,
        "jours_ecoules": 55,
        "nb_enregistrements": 12000,
        "source_type": TypeSource.RANSOMWARE_SITE,
        "source_ref": "http://safepay.onion/blog/post/ecobank1",
    },
]


def seed_test_data():
    init_db()
    session = get_session()

    for data in TEST_DATA:
        date_detection = utc_now() - timedelta(days=data["jours_ecoules"])

        exposition = Exposition(
            nom_entite=data["nom_entite"],
            secteur_activite=data["secteur_activite"],
            type_entite=data["type_entite"],
            categorie_fuite=data["categorie_fuite"],
            date_premiere_detection=date_detection,
            date_derniere_detection=date_detection,
            nombre_enregistrements_revendique=data["nb_enregistrements"],
            score_confiance=data["score_confiance"],
            statut=data["statut"],
        )
        session.add(exposition)
        session.flush()

        source_ref = SourceReference(
            exposition_id=exposition.id,
            type_source=data["source_type"],
            reference_source=data["source_ref"],
        )
        session.add(source_ref)

    session.commit()
    print(f"[OK] {len(TEST_DATA)} exposition(s) de test inseree(s).")
    session.close()


if __name__ == "__main__":
    seed_test_data()