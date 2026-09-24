"""portee et etat des exclusions de faux positifs

Revision ID: f2b71c9a4d83
Revises: a3f10b7c94d2
Create Date: 2026-09-24 09:00:00.000000

FR-11 - la table exclusions_faux_positifs existait depuis le schema initial
mais aucun chemin ne permettait de l'alimenter : ni route, ni interface, ni
commande. Elle etait donc structurellement vide et son moteur ne s'executait
jamais. Cette revision lui donne de quoi porter une liste reellement tenue
par les analystes :

  - type_exclusion : ce que le motif confronte, le NOM D'ENTITE retenu pour
    l'entree ("Cameroon Holdings Ltd", societe etrangere homonyme) ou le
    TEXTE de l'annonce (comportement historique).
  - source_id      : portee. NULL = toutes les sources. Un en-tete recurrent
    propre a une source n'a aucune raison d'aveugler les six autres.
  - actif          : une regle trop large se desactive au lieu de se
    supprimer, la trace de ce qui a ete essaye reste lisible.
  - commentaire    : pourquoi cette regle existe, pour l'analyste suivant.

Les lignes existantes (il ne peut y en avoir aucune, faute de chemin
d'ecriture) prendraient le type TEXTE et la portee "toutes les sources",
c'est-a-dire exactement le comportement du code precedent.

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b71c9a4d83'
down_revision: Union[str, None] = 'a3f10b7c94d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# SQLAlchemy stocke un SAEnum par le NOM du membre, pas par sa valeur :
# la colonne contient 'TEXTE' / 'ENTITE' (cf. le schema initial, qui liste
# 'CREDENTIALS', 'DONNEES_PERSONNELLES'... pour categoriefuite).
TYPE_EXCLUSION = sa.Enum('ENTITE', 'TEXTE', name='typeexclusion')


def upgrade() -> None:
    # batch_alter_table : SQLite ne sait pas ajouter une colonne portant une
    # contrainte CHECK, Alembic recree donc la table.
    with op.batch_alter_table('exclusions_faux_positifs') as batch_op:
        batch_op.add_column(
            sa.Column('type_exclusion', TYPE_EXCLUSION,
                      nullable=False, server_default='TEXTE')
        )
        batch_op.add_column(sa.Column('source_id', sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column('actif', sa.Boolean(), nullable=False, server_default='1')
        )
        batch_op.add_column(sa.Column('commentaire', sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            'fk_exclusions_source', 'sources', ['source_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('exclusions_faux_positifs') as batch_op:
        batch_op.drop_constraint('fk_exclusions_source', type_='foreignkey')
        batch_op.drop_column('commentaire')
        batch_op.drop_column('actif')
        batch_op.drop_column('source_id')
        batch_op.drop_column('type_exclusion')
