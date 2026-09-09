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


def upgrade() -> None:
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
    op.create_index(
        'ix_evenements_horodatage', 'evenements_collecte', ['horodatage']
    )


def downgrade() -> None:
    op.drop_index('ix_evenements_horodatage', table_name='evenements_collecte')
    op.drop_table('evenements_collecte')
    op.drop_table('etat_scheduler')
