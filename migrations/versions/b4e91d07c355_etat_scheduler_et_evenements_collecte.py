"""etat_scheduler et evenements_collecte pour la supervision temps reel

Revision ID: b4e91d07c355
Revises: a1c7e3f42b90
Create Date: 2026-09-09 19:05:00.000000

FR-07 - Le scheduler tourne dans un processus separe du serveur Flask.
Sans etat partage, l'interface de supervision ne pouvait rien savoir de
lui, et rien n'empechait de lancer deux collectes concurrentes.

  - etat_scheduler : ligne unique (id=1) portant le verrou d'instance
    unique (pid + heartbeat) et le tableau de bord (source en cours,
    prochaine echeance).
  - evenements_collecte : fil d'activite lu par la console. Cle primaire
    ENTIERE, contrairement au reste du modele en UUID, parce que la
    console demande "les evenements posterieurs a l'id X" et a donc besoin
    d'un ordre total bon marche.

Ecrite A LA MAIN, sans --autogenerate, pour les raisons detaillees dans la
revision d6fb8279afd3.

Note SQLAlchemy : SAEnum stocke le NOM du membre ('EN_ATTENTE'), pas sa
valeur ('en_attente') - d'ou les majuscules dans sa.Enum(...).

IDEMPOTENTE - sur la VM, un point d'entree de l'application a tourne apres
le git pull et avant "alembic upgrade head" : app/db.py::init_db()
executait alors Base.metadata.create_all(), qui a cree ces deux tables a
partir des modeles. La migration echouait ensuite sur "table etat_scheduler
already exists", avec alembic_version bloquee sur a1c7e3f42b90.

Elle cree donc chaque table et l'index SEULEMENT s'ils manquent. Une table
deja presente n'est pas acceptee les yeux fermes : ses colonnes sont
controlees, et s'il manque une colonne attendue, la migration s'arrete avec
un message explicite plutot que d'enregistrer comme appliquee une table
incomplete. Aucune donnee n'est supprimee.

La cause elle-meme est corrigee dans init_db(), qui ne cree plus de tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e91d07c355'
down_revision: Union[str, None] = 'a1c7e3f42b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUT_SCHEDULER = sa.Enum(
    'ARRETE', 'EN_ATTENTE', 'COLLECTE_EN_COURS', name='statutscheduler'
)

TYPE_EVENEMENT = sa.Enum(
    'DEBUT_CYCLE', 'DEBUT_SOURCE', 'FIN_SOURCE', 'NOUVELLE_EXPOSITION',
    'FIN_CYCLE', name='typeevenementcollecte',
)


# Colonnes que chaque table doit porter pour que la revision soit
# consideree comme appliquee.
COLONNES_ATTENDUES = {
    'etat_scheduler': {
        'id', 'actif', 'statut', 'pid', 'hostname', 'demarre_le', 'heartbeat',
        'source_en_cours', 'derniere_execution', 'prochaine_execution',
        'derniere_stats', 'collecte_immediate_demandee',
    },
    'evenements_collecte': {
        'id', 'horodatage', 'type_evenement', 'source', 'message', 'exposition_id',
    },
}


def _controler_table_existante(inspecteur, table: str):
    """Refuse de valider une table creee hors Alembic si elle est incomplete."""
    presentes = {colonne['name'] for colonne in inspecteur.get_columns(table)}
    manquantes = COLONNES_ATTENDUES[table] - presentes
    if manquantes:
        raise RuntimeError(
            f"La table {table} existe deja mais il lui manque les colonnes "
            f"{sorted(manquantes)}. Elle a ete creee hors Alembic par une "
            f"version anterieure du modele : a examiner avant toute action "
            f"(voir le docstring de cette revision)."
        )


def upgrade() -> None:
    inspecteur = sa.inspect(op.get_bind())

    if inspecteur.has_table('etat_scheduler'):
        _controler_table_existante(inspecteur, 'etat_scheduler')
    else:
        op.create_table(
            'etat_scheduler',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('actif', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('statut', STATUT_SCHEDULER, nullable=False, server_default='ARRETE'),
            sa.Column('pid', sa.Integer(), nullable=True),
            sa.Column('hostname', sa.String(length=255), nullable=True),
            sa.Column('demarre_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('heartbeat', sa.DateTime(timezone=True), nullable=True),
            sa.Column('source_en_cours', sa.String(length=255), nullable=True),
            sa.Column('derniere_execution', sa.DateTime(timezone=True), nullable=True),
            sa.Column('prochaine_execution', sa.DateTime(timezone=True), nullable=True),
            sa.Column('derniere_stats', sa.Text(), nullable=True),
            sa.Column('collecte_immediate_demandee', sa.Boolean(), nullable=False,
                      server_default=sa.false()),
            sa.PrimaryKeyConstraint('id'),
        )

    if inspecteur.has_table('evenements_collecte'):
        _controler_table_existante(inspecteur, 'evenements_collecte')
    else:
        op.create_table(
            'evenements_collecte',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('horodatage', sa.DateTime(timezone=True), nullable=False),
            sa.Column('type_evenement', TYPE_EVENEMENT, nullable=False),
            sa.Column('source', sa.String(length=255), nullable=True),
            sa.Column('message', sa.String(length=500), nullable=False),
            sa.Column('exposition_id', sa.String(length=36), nullable=True),
            sa.ForeignKeyConstraint(['exposition_id'], ['expositions.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    # Relecture : l'inspecteur met en cache l'etat initial de la base.
    index_presents = {
        index['name'] for index in sa.inspect(op.get_bind()).get_indexes('evenements_collecte')
    }
    if 'ix_evenements_horodatage' not in index_presents:
        op.create_index(
            'ix_evenements_horodatage', 'evenements_collecte', ['horodatage']
        )


def downgrade() -> None:
    op.drop_index('ix_evenements_horodatage', table_name='evenements_collecte')
    op.drop_table('evenements_collecte')
    op.drop_table('etat_scheduler')
