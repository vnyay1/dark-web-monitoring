"""retrait des champs qu'aucune etape du pipeline ne renseigne

Revision ID: a7d3e9c2b6f1
Revises: f4c8b2d6e913
Create Date: 2026-09-11 14:00:00.000000

Meme constat que pour le secteur d'activite (revision f4c8b2d6e913) : ces
colonnes existent depuis le schema initial mais la collecte ne les
remplit jamais.

  - expositions.type_entite (publique / privee) et l'enumeration
    typeentite ;
  - expositions.nombre_enregistrements_revendique, affiche "non
    communique" dans le detail de chaque exposition ;
  - sources.temps_reponse_moyen, lu nulle part ;
  - selecteurs.propose_par_ner et selecteurs.valide_par_analyste : prevus
    pour FR-14 (proposition de selecteurs par NER), non realise.

GARDE-FOU - si une exposition porte une valeur dans l'un de ces champs
(base alimentee par l'ancien script de donnees de test, par exemple), la
migration s'arrete au lieu de l'effacer sans le dire. Pour confirmer :
    SENTINEL_SUPPRIMER_CHAMPS_VIDES=1 alembic upgrade head

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3). Le
downgrade restaure les colonnes, vides (valeurs par defaut du schema
initial pour les deux booleens des selecteurs).
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3e9c2b6f1'
down_revision: Union[str, None] = 'f4c8b2d6e913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    renseignees = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM expositions "
        "WHERE type_entite IS NOT NULL OR nombre_enregistrements_revendique IS NOT NULL"
    )).scalar()
    if renseignees and os.getenv("SENTINEL_SUPPRIMER_CHAMPS_VIDES") != "1":
        raise RuntimeError(
            f"{renseignees} exposition(s) ont un type d'entite ou un nombre "
            f"d'enregistrements renseigne, qui serait efface. Pour confirmer : "
            f"SENTINEL_SUPPRIMER_CHAMPS_VIDES=1 alembic upgrade head"
        )

    with op.batch_alter_table('expositions') as batch_op:
        batch_op.drop_column('type_entite')
        batch_op.drop_column('nombre_enregistrements_revendique')

    with op.batch_alter_table('sources') as batch_op:
        batch_op.drop_column('temps_reponse_moyen')

    with op.batch_alter_table('selecteurs') as batch_op:
        batch_op.drop_column('propose_par_ner')
        batch_op.drop_column('valide_par_analyste')


def downgrade() -> None:
    with op.batch_alter_table('selecteurs') as batch_op:
        batch_op.add_column(
            sa.Column('propose_par_ner', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column('valide_par_analyste', sa.Boolean(), nullable=False, server_default=sa.true())
        )

    with op.batch_alter_table('sources') as batch_op:
        batch_op.add_column(sa.Column('temps_reponse_moyen', sa.Float(), nullable=True))

    with op.batch_alter_table('expositions') as batch_op:
        batch_op.add_column(sa.Column(
            'type_entite', sa.Enum('PUBLIQUE', 'PRIVEE', name='typeentite'), nullable=True
        ))
        batch_op.add_column(sa.Column('nombre_enregistrements_revendique', sa.Integer(), nullable=True))
