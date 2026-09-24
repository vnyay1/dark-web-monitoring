"""
Attribue des categories aux expositions qui n'en ont pas.

POURQUOI - les categories d'une exposition sont celles des selecteurs qui
l'ont declenchee (FR-13). Les expositions detectees avant ce changement
n'en portent aucune : les selecteurs trouves a l'epoque n'etaient pas
enregistres (CN-03), il est donc impossible de les retrouver exactement.

APPROXIMATION ASSUMEE - le seul texte encore disponible est le NOM de
l'entite. Il passe dans le meme moteur de correspondance et le meme filtre
de faux positifs que la collecte. "Afriland First Bank" retrouve ainsi la
categorie Banque ; un nom qui ne cite aucun selecteur reste sans categorie.
Les collectes suivantes completent par union (cf. deduplication), sans
jamais retirer ce qui a ete attribue ici.

Simulation par defaut ; --confirmer ecrit en base.

Usage :
    python3 -m app.maintenance.recategoriser
    python3 -m app.maintenance.recategoriser --confirmer
"""

import argparse
import logging
import sys

from sqlalchemy.orm import joinedload

from app.db import get_session, init_db
from app.matching.engine import match_text_against_catalogue
from app.matching.exclusion import filtrer_faux_positifs
from app.models import Categorie, Exposition, Selecteur

logger = logging.getLogger(__name__)


def recategoriser(confirmer: bool) -> int:
    init_db()
    session = get_session()
    try:
        selecteurs = (
            session.query(Selecteur)
            .options(joinedload(Selecteur.categorie))
            .filter_by(actif=True)
            .all()
        )
        categories = {c.id: c for c in session.query(Categorie).all()}

        sans_categorie = [e for e in session.query(Exposition).all() if not e.categories]
        print(f"\n{len(sans_categorie)} exposition(s) sans categorie, "
              f"{len(selecteurs)} selecteur(s) actif(s).\n")

        attribuees = 0
        for exposition in sans_categorie:
            texte = exposition.nom_entite or ""
            # Sans source_id : une exposition peut porter plusieurs
            # signalements, il n'y a pas UNE source a laquelle rattacher la
            # regle - seules les regles generales s'appliquent. Les regles
            # de type ENTITE ne sont pas consultees non plus : elles
            # ecartent des annonces a l'analyse, elles ne retirent pas leurs
            # categories a des expositions deja enregistrees.
            correspondances = filtrer_faux_positifs(
                texte, match_text_against_catalogue(texte, selecteurs), session=session,
            )
            trouvees = [
                categories[i] for i in dict.fromkeys(m.selecteur_categorie for m in correspondances)
                if i in categories
            ]

            libelle = ", ".join(c.nom for c in trouvees) or "aucune (reste sans categorie)"
            print(f"  {exposition.nom_entite[:48]:50} -> {libelle}")

            if trouvees:
                attribuees += 1
                if confirmer:
                    exposition.categories.extend(trouvees)

        print(f"\n{attribuees} exposition(s) recoivent au moins une categorie ; "
              f"{len(sans_categorie) - attribuees} restent sans categorie.")

        if not confirmer:
            print("SIMULATION : rien n'a ete modifie. Relancez avec --confirmer pour ecrire.")
            session.rollback()
            return 0

        session.commit()
        logger.info(f"[maintenance] Categories attribuees a {attribuees} exposition(s).")
        print("Categories enregistrees.")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
    parseur = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parseur.add_argument("--confirmer", action="store_true", help="Ecrit en base (sinon : simulation)")
    sys.exit(recategoriser(parseur.parse_args().confirmer))
