"""secteur d'activite retire, priorite sectorielle portee par les categories

Revision ID: f4c8b2d6e913
Revises: e3a9f6c1d072
Create Date: 2026-09-11 09:00:00.000000

expositions.secteur_activite n'etait renseigne par aucune etape du
pipeline : toutes les expositions affichaient "Non renseigne". Le secteur
est desormais lu sur les CATEGORIES de l'exposition, qui viennent des
selecteurs trouves (Ministere, Banque, Telecommunications...).

  - categories.prioritaire : secteur prioritaire au sens de FR-26 (canaux
    d'alerte renforces). Il remplace la liste de mots-cles que
    app.alerting.rules cherchait dans le champ secteur. Active pour les
    categories correspondantes : Ministere, Agence gouvernementale, Banque,
    Microfinance, Telecommunications.
  - expositions.secteur_activite : supprimee.

GARDE-FOU - si des expositions ont un secteur renseigne (base alimentee par
app.seed_test_expositions, par exemple), la migration s'arrete au lieu de
les effacer sans le dire. Pour confirmer :
    SENTINEL_SUPPRIMER_SECTEURS=1 alembic upgrade head

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3). Le
downgrade restaure la colonne, vide.
"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4c8b2d6e913'
down_revision: Union[str, None] = 'e3a9f6c1d072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Libelles poses par la revision e3a9f6c1d072. Une categorie renommee
# depuis n'est pas retrouvee : l'administrateur coche alors l'indicateur
# lui-meme dans Configuration.
CATEGORIES_PRIORITAIRES = (
    "Ministère", "Agence gouvernementale", "Banque", "Microfinance", "Télécommunications",
)


def upgrade() -> None:
    connexion = op.get_bind()
    renseignes = connexion.execute(sa.text(
        "SELECT COUNT(*) FROM expositions "
        "WHERE secteur_activite IS NOT NULL AND TRIM(secteur_activite) != ''"
    )).scalar()
    if renseignes and os.getenv("SENTINEL_SUPPRIMER_SECTEURS") != "1":
        raise RuntimeError(
            f"{renseignes} exposition(s) ont un secteur d'activite renseigne, qui "
            f"serait efface. Pour confirmer : "
            f"SENTINEL_SUPPRIMER_SECTEURS=1 alembic upgrade head"
        )

    with op.batch_alter_table('categories') as batch_op:
        batch_op.add_column(
            sa.Column('prioritaire', sa.Boolean(), nullable=False, server_default=sa.false())
        )

    categories = sa.table('categories', sa.column('nom', sa.String), sa.column('prioritaire', sa.Boolean))
    op.execute(
        categories.update()
        .where(categories.c.nom.in_(CATEGORIES_PRIORITAIRES))
        .values(prioritaire=True)
    )

    with op.batch_alter_table('expositions') as batch_op:
        batch_op.drop_column('secteur_activite')


def downgrade() -> None:
    with op.batch_alter_table('expositions') as batch_op:
        batch_op.add_column(sa.Column('secteur_activite', sa.String(length=255), nullable=True))

    with op.batch_alter_table('categories') as batch_op:
        batch_op.drop_column('prioritaire')
