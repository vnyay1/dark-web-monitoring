"""poids des selecteurs dans la criticite

Revision ID: ddb52e19e593
Revises: a7d3e9c2b6f1
Create Date: 2026-09-18 10:30:00.000000

L'administrateur peut rendre un selecteur PRIORITAIRE ("Cameroun",
"Cameroon"...) : il compte alors pour son poids, et non plus pour 1, dans
la criticite (app.matching.criticite). Poids 1 pour tous les selecteurs
existants : la criticite calculee reste exactement celle d'avant tant que
personne ne modifie un poids.

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddb52e19e593'
down_revision: Union[str, None] = 'a7d3e9c2b6f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('selecteurs') as batch_op:
        batch_op.add_column(
            sa.Column('poids', sa.Integer(), nullable=False, server_default='1')
        )


def downgrade() -> None:
    with op.batch_alter_table('selecteurs') as batch_op:
        batch_op.drop_column('poids')
