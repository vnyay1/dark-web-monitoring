"""criticite remplace le score de confiance, source et date sur les signalements

Revision ID: a1c7e3f42b90
Revises: d6fb8279afd3
Create Date: 2026-09-09 18:40:00.000000

FR-10 - Le score de confiance (flottant 0-1 issu de trois facteurs
ponderes) est remplace par la CRITICITE : le nombre de selecteurs
distincts du catalogue trouves dans l'entree, et son palier nomme.

FR-03 - Ajout des dates de publication, necessaires pour ne parcourir que
les entrees publiees sur la periode reglee par l'administrateur.

FR-12 - source_references.source_id relie enfin un signalement a la Source
surveillee : jusqu'ici la table ne portait que la FAMILLE de source
("ransomware_site"), donc le nom exact de l'origine d'une exposition
("payload", "safepay") etait introuvable depuis l'interface.

Ecrite A LA MAIN, sans --autogenerate, pour les raisons detaillees dans la
revision d6fb8279afd3.

Note SQLAlchemy : SAEnum stocke le NOM du membre ('FAIBLE'), pas sa valeur
('faible') - d'ou les majuscules dans sa.Enum(...).

IRREVERSIBILITE PARTIELLE - le downgrade restaure la colonne
score_confiance mais ne peut pas en recalculer les valeurs : les facteurs
d'origine (precision par categorie de selecteur, position des
correspondances) n'ont jamais ete persistes. Les expositions retrouvent
donc un score a 0.0.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7e3f42b90'
down_revision: Union[str, None] = 'd6fb8279afd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NIVEAU_CRITICITE = sa.Enum(
    'FAIBLE', 'MOYENNE', 'ELEVEE', 'CRITIQUE', name='niveaucriticite'
)

# Cles de configuration devenues sans objet : elles reglaient des seuils
# exprimes sur l'echelle de score, qui n'existe plus.
CLES_OBSOLETES = (
    'seuil_alerte_minimum',
    'seuil_alerte_critique',
    'seuil_alerte_eleve',
    'seuil_hausse_confirmation',
    'seuil_enregistrement_minimum',
)


def upgrade() -> None:
    # SQLite ne sait pas supprimer ni contraindre une colonne en place :
    # batch_alter_table recree la table et recopie les donnees.
    with op.batch_alter_table('expositions') as batch:
        batch.add_column(sa.Column(
            'criticite', sa.Integer(), nullable=False, server_default='0'
        ))
        batch.add_column(sa.Column(
            'niveau_criticite', NIVEAU_CRITICITE,
            nullable=False, server_default='FAIBLE',
        ))
        batch.add_column(sa.Column(
            'date_publication_source', sa.DateTime(timezone=True), nullable=True
        ))
        batch.drop_column('score_confiance')

    with op.batch_alter_table('source_references') as batch:
        batch.add_column(sa.Column('source_id', sa.String(length=36), nullable=True))
        batch.add_column(sa.Column(
            'date_publication', sa.DateTime(timezone=True), nullable=True
        ))
        batch.add_column(sa.Column(
            'date_signalement', sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.current_timestamp(),
        ))
        batch.create_foreign_key(
            'fk_source_references_source_id', 'sources', ['source_id'], ['id']
        )

    op.execute(
        sa.text('DELETE FROM configuration_systeme WHERE cle IN :cles')
        .bindparams(sa.bindparam('cles', value=CLES_OBSOLETES, expanding=True))
    )


def downgrade() -> None:
    with op.batch_alter_table('source_references') as batch:
        batch.drop_constraint('fk_source_references_source_id', type_='foreignkey')
        batch.drop_column('date_signalement')
        batch.drop_column('date_publication')
        batch.drop_column('source_id')

    with op.batch_alter_table('expositions') as batch:
        # Valeurs perdues : voir la note d'irreversibilite en tete de fichier.
        batch.add_column(sa.Column(
            'score_confiance', sa.Float(), nullable=False, server_default='0.0'
        ))
        batch.drop_column('date_publication_source')
        batch.drop_column('niveau_criticite')
        batch.drop_column('criticite')
