"""duree de cycle et ip de sortie tor sur etat_scheduler

Revision ID: c7d2a8e51f06
Revises: b4e91d07c355
Create Date: 2026-09-10 10:30:00.000000

FR-07 - Supervision :

  - debut_collecte / fin_collecte : le "temps ecoule" de la console mesure
    desormais la duree du CYCLE en cours (fige en veille, remis a zero au
    cycle suivant) et non plus l'age du processus scheduler.
  - ip_sortie, ip_sortie_precedente, ip_verifiee_le, ip_changee_le,
    verification_ip_demandee : IP du noeud de sortie Tor, publiee par le
    processus scheduler, pour verifier que le renouvellement de circuit
    fonctionne.

Le nouveau type d'evenement CIRCUIT_RENOUVELE ne demande aucun changement
de schema : SQLite ne pose pas de contrainte CHECK sur les colonnes
sa.Enum, et la colonne VARCHAR(19) accueille ce nom de 17 caracteres.

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
Colonnes ajoutees une a une avec controle d'existence, par coherence avec
b4e91d07c355 : une colonne deja presente n'est pas recreee.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2a8e51f06'
down_revision: Union[str, None] = 'b4e91d07c355'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NOUVELLES_COLONNES = (
    sa.Column('debut_collecte', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fin_collecte', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip_sortie', sa.String(length=64), nullable=True),
    sa.Column('ip_sortie_precedente', sa.String(length=64), nullable=True),
    sa.Column('ip_verifiee_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip_changee_le', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verification_ip_demandee', sa.Boolean(), nullable=False,
              server_default=sa.false()),
)


def upgrade() -> None:
    presentes = {
        colonne['name']
        for colonne in sa.inspect(op.get_bind()).get_columns('etat_scheduler')
    }

    with op.batch_alter_table('etat_scheduler') as batch:
        for colonne in NOUVELLES_COLONNES:
            if colonne.name not in presentes:
                batch.add_column(colonne.copy())


def downgrade() -> None:
    with op.batch_alter_table('etat_scheduler') as batch:
        for colonne in reversed(NOUVELLES_COLONNES):
            batch.drop_column(colonne.name)
