"""signature de listing des entrees collectees

Revision ID: a3f10b7c94d2
Revises: e9dc3c85a1c6
Create Date: 2026-09-21 10:00:00.000000

Le registre du crawl incremental savait seulement si un identifiant avait
deja ete traite. Une annonce dont le contenu s'enrichissait (un post ajoute
a une categorie everest deja TRAITEE) n'etait donc plus jamais relue.

signature_listing memorise, par entree, une empreinte du VOLUME annonce par
le listing au dernier passage (nombre de posts, date). Quand elle change,
la page de detail est reprise dans le budget du cycle.

CN-03/CN-04 : l'empreinte est un sha256 de metadonnees de volume et de date
uniquement - jamais un nom d'entite, jamais un extrait de texte, jamais une
empreinte du contenu divulgue. Colonne vide pour les lignes existantes :
sans point de comparaison, elles ne sont pas relues, et la signature sera
posee a leur prochaine lecture de page de detail.

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f10b7c94d2'
down_revision: Union[str, None] = 'e9dc3c85a1c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('entrees_collectees') as batch_op:
        batch_op.add_column(sa.Column('signature_listing', sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('entrees_collectees') as batch_op:
        batch_op.drop_column('signature_listing')
