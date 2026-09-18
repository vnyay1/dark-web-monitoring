"""
Point d'entree pour la connexion a la base de donnees.

LE SCHEMA APPARTIENT A ALEMBIC. init_db() creait autrefois les tables
manquantes par Base.metadata.create_all(). C'etait incompatible avec les
migrations : lance apres un git pull et AVANT "alembic upgrade head",
n'importe quel point d'entree (serveur web, scheduler, scripts) creait les
nouvelles tables a partir des modeles, et la migration echouait ensuite sur
"table ... already exists". C'est exactement ce qui s'est produit sur la VM
avec etat_scheduler.

init_db() se contente donc de VERIFIER que la base est a la revision head,
et refuse de continuer sinon, avec la commande a lancer. Mieux vaut un arret
net au demarrage qu'un plantage plus tard sur une colonne absente.
"""

import threading
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Config

# SQLite n'admet qu'un ecrivain a la fois ; les autres attendent. 30 s au
# lieu des 5 s par defaut : avec la collecte parallele, une ecriture annexe
# (heartbeat du scheduler, evenement de supervision) peut devoir patienter
# le temps qu'une source finisse d'enregistrer une entree. Mieux vaut
# attendre que d'echouer en "database is locked".
_OPTIONS_CONNEXION = (
    {"timeout": 30} if Config.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(Config.DATABASE_URL, echo=False, connect_args=_OPTIONS_CONNEXION)
SessionLocal = sessionmaker(bind=engine)

# COLLECTE PARALLELE (cf. app.pipeline.executer_tous_les_connecteurs) - les
# sources font leurs requetes reseau en meme temps, mais passent UNE PAR UNE
# dans tout ce qui lit puis ecrit la base de la collecte : preparation,
# analyse et enregistrement, journal d'audit. Deux raisons :
#   - deduplication : chercher une exposition existante puis l'inserer n'est
#     pas atomique ; deux sources publiant la meme victime en meme temps
#     creeraient deux expositions ;
#   - SQLite : un seul ecrivain a la fois.
# RLock : un fil qui le detient deja peut le reprendre sans se bloquer.
verrou_base = threading.RLock()

RACINE_PROJET = Path(__file__).resolve().parents[1]


class BaseNonAJour(RuntimeError):
    """La base n'est pas a la derniere revision Alembic."""


def _revisions_attendues() -> set:
    from alembic.config import Config as ConfigAlembic
    from alembic.script import ScriptDirectory

    configuration = ConfigAlembic(str(RACINE_PROJET / "alembic.ini"))
    # Chemin absolu : le processus peut etre lance depuis un autre dossier
    # (le scheduler, par exemple, quand il est demarre depuis l'interface).
    configuration.set_main_option("script_location", str(RACINE_PROJET / "migrations"))
    return set(ScriptDirectory.from_config(configuration).get_heads())


def _revisions_en_base() -> set:
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as connexion:
        return set(MigrationContext.configure(connexion).get_current_heads())


def init_db():
    """
    Verifie que le schema de la base est a jour. Ne cree ni ne modifie rien.

    Leve BaseNonAJour si la base est vide ou en retard sur les migrations.
    """
    attendues = _revisions_attendues()
    en_base = _revisions_en_base()

    if en_base == attendues:
        return

    etat = ", ".join(sorted(en_base)) or "aucune (base vide ou non geree par Alembic)"
    raise BaseNonAJour(
        f"La base de donnees n'est pas a jour : revision {etat}, "
        f"attendue {', '.join(sorted(attendues))}.\n"
        f"Lancez depuis la racine du projet :  alembic upgrade head"
    )


def get_session():
    """Retourne une nouvelle session SQLAlchemy."""
    return SessionLocal()
