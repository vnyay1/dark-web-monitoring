"""selecteurs trouves, enregistres par signalement

Revision ID: c87e007c6549
Revises: 731285b2af56
Create Date: 2026-09-18 16:00:00.000000

Le detail d'une exposition affiche desormais les selecteurs du catalogue
trouves dans l'annonce, avec leur poids : ils justifient sa criticite. Ils
sont enregistres sur le signalement (liste JSON de termes du catalogue).
Colonne vide pour les signalements existants : la collecte les complete a
la prochaine relecture de l'annonce (cf. app.conservation).

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c87e007c6549'
down_revision: Union[str, None] = '731285b2af56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('source_references') as batch_op:
        batch_op.add_column(sa.Column('selecteurs_trouves', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('source_references') as batch_op:
        batch_op.drop_column('selecteurs_trouves')
