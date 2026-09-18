"""texte conserve des signalements (derogation CN-04/CN-05)

Revision ID: 3bee298d4fcb
Revises: ddb52e19e593
Create Date: 2026-09-18 11:30:00.000000

Le texte analyse d'une entree qui a produit une exposition est conserve
sur son signalement, pour que l'analyste puisse le relire depuis le detail
de l'exposition (bouton "Details"). C'est une DEROGATION a CN-04/CN-05,
decidee le 2026-09-18 : perimetre et garde-fous dans app/conservation.py
et dans le README.

Colonnes vides pour les signalements existants : leur texte n'a jamais
ete conserve. Le downgrade supprime les textes conserves.

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3bee298d4fcb'
down_revision: Union[str, None] = 'ddb52e19e593'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('source_references') as batch_op:
        batch_op.add_column(sa.Column('texte_brut', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('date_texte_brut', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('source_references') as batch_op:
        batch_op.drop_column('date_texte_brut')
        batch_op.drop_column('texte_brut')
