"""add entrees_collectees for incremental crawl

Revision ID: d6fb8279afd3
Revises: 00ff39938e95
Create Date: 2026-09-09 13:05:57.333652

Table de travail du crawl incremental : elle memorise quelles entrees
d'une source ont deja ete analysees, pour ne pas re-telecharger leur page
de detail a chaque cycle.

Ecrite A LA MAIN volontairement, sans --autogenerate : l'historique de ce
depot contient deja des revisions dupliquees (8b36f4127467 / e876c6c31d5d
creent toutes deux configuration_systeme) et app/db.py::init_db() appelle
Base.metadata.create_all() en parallele d'Alembic. Un autogenerate sur la
base courante produirait des drop/alter parasites sur les colonnes Enum.

Note SQLAlchemy : SAEnum stocke le NOM du membre ('A_TRAITER'), pas sa
valeur - d'ou les majuscules dans sa.Enum(...).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6fb8279afd3'
down_revision: Union[str, None] = '00ff39938e95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'entrees_collectees',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_id', sa.String(length=36), nullable=False),
        sa.Column('identifiant_entree', sa.String(length=500), nullable=False),
        sa.Column(
            'statut_detail',
            sa.Enum('A_TRAITER', 'TRAITEE', 'SANS_DETAIL', 'ECHEC',
                    name='statutdetailentree'),
            nullable=False,
            server_default='A_TRAITER',
        ),
        sa.Column('date_premiere_vue', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_derniere_vue', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_detail_traite', sa.DateTime(timezone=True), nullable=True),
        sa.Column('nb_echecs_detail', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('a_produit_exposition', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'identifiant_entree',
                            name='uq_entree_par_source'),
    )
    op.create_index(
        'ix_entrees_source_statut', 'entrees_collectees',
        ['source_id', 'statut_detail'],
    )


def downgrade() -> None:
    op.drop_index('ix_entrees_source_statut', table_name='entrees_collectees')
    op.drop_table('entrees_collectees')
