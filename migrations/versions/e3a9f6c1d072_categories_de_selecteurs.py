"""categories de selecteurs gerees en base, remplacent la nature de la fuite

Revision ID: e3a9f6c1d072
Revises: c7d2a8e51f06
Create Date: 2026-09-10 14:30:00.000000

FR-13 - La categorisation par mots-cles ("nature de la fuite" :
identifiants, donnees personnelles...) ne donnait pas satisfaction. Une
exposition prend desormais la ou les categories des SELECTEURS qui l'ont
declenchee, et ces categories deviennent une table geree par
l'administrateur au lieu d'une enumeration figee dans le code.

  - categories : les 10 categories existantes, sous leur libelle francais.
    "Ville / region" porte lieu_generique : la regle de faux positif
    "nom de lieu dans une liste de pays" suit cet indicateur, pas un nom.
  - selecteurs.categorie (enum) -> selecteurs.categorie_id (FK), chaque
    selecteur rattache a la categorie correspondant a son ancienne valeur.
  - exposition_categories : association plusieurs a plusieurs.
  - expositions.categorie_fuite : supprimee.

Ecrite A LA MAIN, sans --autogenerate (cf. revision d6fb8279afd3).
SAEnum stockait le NOM du membre ('MINISTERE') : c'est lui qui sert de cle
de correspondance.

IRREVERSIBILITE PARTIELLE - le downgrade restaure les colonnes, mais la
nature de fuite supprimee n'est pas recalculable : les expositions
reviennent en "non precisee". Une categorie creee par l'administrateur,
sans equivalent dans l'ancienne enumeration, redevient "entreprise".
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3a9f6c1d072'
down_revision: Union[str, None] = 'c7d2a8e51f06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Ancienne valeur d'enumeration -> (libelle, description, lieu_generique)
CATEGORIES_INITIALES = {
    'DOMAINE': ("Domaine internet", "Noms de domaine et suffixes camerounais (.cm, .gov.cm)", False),
    'TELEPHONE': ("Téléphone", "Indicatifs et formats de numéros camerounais", False),
    'MINISTERE': ("Ministère", "Ministères et leurs sigles", False),
    'AGENCE_GOUVERNEMENTALE': ("Agence gouvernementale", "Agences, offices et établissements publics", False),
    'BANQUE': ("Banque", "Établissements bancaires", False),
    'MICROFINANCE': ("Microfinance", "Établissements de microfinance", False),
    'TELECOM': ("Télécommunications", "Opérateurs et fournisseurs de télécommunications", False),
    'UNIVERSITE': ("Université", "Universités et grandes écoles", False),
    'ENTREPRISE': ("Entreprise", "Entreprises publiques et privées", False),
    'VILLE_REGION': ("Ville / région", "Villes et régions, susceptibles de figurer dans une simple liste de pays", True),
}

ANCIENNE_ENUM_SELECTEUR = sa.Enum(*CATEGORIES_INITIALES, name='categorieselecteur')
ANCIENNE_ENUM_FUITE = sa.Enum(
    'CREDENTIALS', 'DONNEES_PERSONNELLES', 'DONNEES_FINANCIERES', 'DONNEES_SANTE',
    'DOCUMENTS_INTERNES', 'CODE_SOURCE', 'NON_PRECISEE', name='categoriefuite',
)


def upgrade() -> None:
    op.create_table(
        'categories',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('nom', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('lieu_generique', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('date_creation', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nom', name='uq_categories_nom'),
    )

    table_categories = sa.table(
        'categories',
        sa.column('id', sa.String), sa.column('nom', sa.String),
        sa.column('description', sa.Text), sa.column('lieu_generique', sa.Boolean),
    )
    identifiants = {code: str(uuid.uuid4()) for code in CATEGORIES_INITIALES}
    op.bulk_insert(table_categories, [
        {'id': identifiants[code], 'nom': nom, 'description': description,
         'lieu_generique': lieu}
        for code, (nom, description, lieu) in CATEGORIES_INITIALES.items()
    ])

    # Rattachement des selecteurs existants, d'apres leur ancienne valeur.
    with op.batch_alter_table('selecteurs') as batch:
        batch.add_column(sa.Column('categorie_id', sa.String(length=36), nullable=True))

    connexion = op.get_bind()
    for code, identifiant in identifiants.items():
        connexion.execute(
            sa.text("UPDATE selecteurs SET categorie_id = :id WHERE categorie = :code"),
            {'id': identifiant, 'code': code},
        )

    orphelins = connexion.execute(
        sa.text("SELECT COUNT(*) FROM selecteurs WHERE categorie_id IS NULL")
    ).scalar()
    if orphelins:
        raise RuntimeError(
            f"{orphelins} selecteur(s) portent une categorie inconnue : migration "
            f"interrompue plutot que de les rattacher au hasard."
        )

    with op.batch_alter_table('selecteurs') as batch:
        batch.alter_column('categorie_id', existing_type=sa.String(length=36), nullable=False)
        batch.create_foreign_key(
            'fk_selecteurs_categorie_id', 'categories', ['categorie_id'], ['id']
        )
        batch.drop_column('categorie')

    op.create_table(
        'exposition_categories',
        sa.Column('exposition_id', sa.String(length=36), nullable=False),
        sa.Column('categorie_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['exposition_id'], ['expositions.id']),
        sa.ForeignKeyConstraint(['categorie_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('exposition_id', 'categorie_id'),
    )

    with op.batch_alter_table('expositions') as batch:
        batch.drop_column('categorie_fuite')


def downgrade() -> None:
    with op.batch_alter_table('expositions') as batch:
        # Valeurs perdues : voir la note d'irreversibilite en tete de fichier.
        batch.add_column(sa.Column(
            'categorie_fuite', ANCIENNE_ENUM_FUITE,
            nullable=False, server_default='NON_PRECISEE',
        ))

    op.drop_table('exposition_categories')

    with op.batch_alter_table('selecteurs') as batch:
        batch.add_column(sa.Column('categorie', ANCIENNE_ENUM_SELECTEUR, nullable=True))

    connexion = op.get_bind()
    for code, (nom, _description, _lieu) in CATEGORIES_INITIALES.items():
        connexion.execute(
            sa.text(
                "UPDATE selecteurs SET categorie = :code WHERE categorie_id IN "
                "(SELECT id FROM categories WHERE nom = :nom)"
            ),
            {'code': code, 'nom': nom},
        )
    connexion.execute(sa.text(
        "UPDATE selecteurs SET categorie = 'ENTREPRISE' WHERE categorie IS NULL"
    ))

    with op.batch_alter_table('selecteurs') as batch:
        batch.alter_column('categorie', existing_type=ANCIENNE_ENUM_SELECTEUR, nullable=False)
        batch.drop_constraint('fk_selecteurs_categorie_id', type_='foreignkey')
        batch.drop_column('categorie_id')

    op.drop_table('categories')
