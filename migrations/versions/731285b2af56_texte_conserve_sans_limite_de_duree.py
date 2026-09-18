"""texte conserve des annonces sans limite de duree

Revision ID: 731285b2af56
Revises: 3bee298d4fcb
Create Date: 2026-09-18 14:00:00.000000

L'encadrant a valide la conservation du texte integral des annonces, sans
limite de duree : le reglage retention_texte_brut_jours disparait du code.
Sa ligne, creee a la premiere ouverture de l'ecran de configuration, est
retiree de configuration_systeme ; sinon elle resterait affichee dans
"Autres reglages" sans plus rien piloter.

Le downgrade ne la recree pas : le code de la revision precedente la
reinsere de lui-meme avec sa valeur par defaut (init_config_defaults).

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '731285b2af56'
down_revision: Union[str, None] = '3bee298d4fcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "DELETE FROM configuration_systeme WHERE cle = 'retention_texte_brut_jours'"
    ))


def downgrade() -> None:
    pass
