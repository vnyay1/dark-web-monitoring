"""version du code executee par le scheduler

Revision ID: e9dc3c85a1c6
Revises: c87e007c6549
Create Date: 2026-09-18 18:00:00.000000

Le scheduler, processus de longue duree, garde en memoire le code charge a
son demarrage. Il enregistre desormais cette version (le commit, cf.
app.version) en prenant le verrou d'instance : l'interface previent
l'administrateur quand elle differe du code installe, c'est-a-dire quand un
redemarrage manque apres un git pull.

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9dc3c85a1c6'
down_revision: Union[str, None] = 'c87e007c6549'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('etat_scheduler') as batch_op:
        batch_op.add_column(sa.Column('version_code', sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('etat_scheduler') as batch_op:
        batch_op.drop_column('version_code')
