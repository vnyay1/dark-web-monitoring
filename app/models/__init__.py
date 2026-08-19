"""
Modele de donnees SQLAlchemy - base sur le diagramme de classes valide.

Base sur FR-16 (liste la plus complete). A ajuster si l'encadrant tranche
en faveur de la liste restreinte de CN-03 (voir ambiguite 3 du rapport de suivi).

Respecte CN-04 : aucun champ ne doit jamais contenir de nom de personne,
numero CNI, telephone, email, mot de passe, hash, information financiere,
ou extrait d'un enregistrement divulgue.
"""

import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Integer,
    Float,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


def utc_now():
    """
    Retourne l'heure UTC actuelle en tant que datetime NAIVE (sans
    tzinfo). SQLite ne conserve pas l'information de timezone au stockage
    (contrairement a PostgreSQL) : une date consciente inseree en aware
    revient naive apres relecture, ce qui casse toute comparaison
    ulterieure avec une nouvelle date aware (TypeError). Comme le systeme
    est mono-fuseau (tout en UTC implicite), on reste volontairement en
    naive partout pour eviter ce probleme a la racine.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------

class TypeEntite(enum.Enum):
    PUBLIQUE = "publique"
    PRIVEE = "privee"


class CategorieFuite(enum.Enum):
    CREDENTIALS = "credentials"
    DONNEES_PERSONNELLES = "donnees_personnelles"
    DONNEES_FINANCIERES = "donnees_financieres"
    DONNEES_SANTE = "donnees_sante"
    DOCUMENTS_INTERNES = "documents_internes"
    CODE_SOURCE = "code_source"
    NON_PRECISEE = "non_precisee"


class StatutExposition(enum.Enum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    NOTIFIED = "notified"
    CLOSED = "closed"


class TypeSource(enum.Enum):
    RANSOMWARE_SITE = "ransomware_site"
    PASTE = "paste"
    FORUM = "forum"
    TELEGRAM = "telegram"
    TEST_CLAIRNET = "test_clairnet"


class CategorieSelecteur(enum.Enum):
    DOMAINE = "domaine"
    TELEPHONE = "telephone"
    MINISTERE = "ministere"
    AGENCE_GOUVERNEMENTALE = "agence_gouvernementale"
    BANQUE = "banque"
    MICROFINANCE = "microfinance"
    TELECOM = "telecom"
    UNIVERSITE = "universite"
    ENTREPRISE = "entreprise"
    VILLE_REGION = "ville_region"


class ResultatAudit(enum.Enum):
    SUCCES = "succes"
    ECHEC = "echec"

class RoleUtilisateur(enum.Enum):
    USER = "user"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# ---------------------------------------------------------------------
# Exposition (indicateur d'exposition - FR-16)
# ---------------------------------------------------------------------

class Exposition(Base):
    __tablename__ = "expositions"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    nom_entite = Column(String(255), nullable=False)
    secteur_activite = Column(String(255), nullable=True)
    type_entite = Column(SAEnum(TypeEntite), nullable=True)

    categorie_fuite = Column(SAEnum(CategorieFuite), nullable=False,
                              default=CategorieFuite.NON_PRECISEE)

    date_premiere_detection = Column(DateTime(timezone=True), nullable=False,
                                      default=utc_now)
    date_derniere_detection = Column(DateTime(timezone=True), nullable=False,
                                      default=utc_now)

    nombre_enregistrements_revendique = Column(Integer, nullable=True)
    score_confiance = Column(Float, nullable=False, default=0.0)

    statut = Column(SAEnum(StatutExposition), nullable=False,
                     default=StatutExposition.NEW)

    sources = relationship(
        "SourceReference", back_populates="exposition",
        cascade="all, delete-orphan"
    )

    def changer_statut(self, nouveau_statut: StatutExposition):
        self.statut = nouveau_statut

    def __repr__(self):
        return f"<Exposition {self.nom_entite} [{self.statut.value}]>"


# ---------------------------------------------------------------------
# SourceReference (lien entre une Exposition et une Source physique)
# ---------------------------------------------------------------------

class SourceReference(Base):
    __tablename__ = "source_references"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    exposition_id = Column(String(36), ForeignKey("expositions.id"), nullable=False)

    type_source = Column(SAEnum(TypeSource), nullable=False)
    reference_source = Column(String(500), nullable=False)  # URL/identifiant, jamais le contenu

    exposition = relationship("Exposition", back_populates="sources")

    def __repr__(self):
        return f"<SourceReference {self.type_source.value} - {self.reference_source[:50]}>"


# ---------------------------------------------------------------------
# Source (source surveillee - FR-04)
# ---------------------------------------------------------------------

class Source(Base):
    __tablename__ = "sources"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    nom = Column(String(255), nullable=False)
    type_source = Column(SAEnum(TypeSource), nullable=False)
    url_ou_identifiant = Column(String(500), nullable=False)

    derniere_collecte_reussie = Column(DateTime(timezone=True), nullable=True)
    nombre_erreurs = Column(Integer, nullable=False, default=0)
    temps_reponse_moyen = Column(Float, nullable=True)

    actif = Column(Boolean, nullable=False, default=True)

    audits = relationship(
        "JournalAudit", back_populates="source",
        cascade="all, delete-orphan"
    )

    def est_indisponible(self, seuil_heures: int = 48) -> bool:
        """FR-04 : signale une source inaccessible depuis plus de 48h."""
        if self.derniere_collecte_reussie is None:
            return True
        delta = utc_now() - self.derniere_collecte_reussie
        return delta.total_seconds() > seuil_heures * 3600

    def __repr__(self):
        return f"<Source {self.nom} ({self.type_source.value})>"


# ---------------------------------------------------------------------
# Selecteur (catalogue de selecteurs - FR-08)
# ---------------------------------------------------------------------

class Selecteur(Base):
    __tablename__ = "selecteurs"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    valeur = Column(String(255), nullable=False)
    categorie = Column(SAEnum(CategorieSelecteur), nullable=False)
    actif = Column(Boolean, nullable=False, default=True)

    # FR-14 : sélecteurs proposés par NER, en attente de validation par un analyste
    propose_par_ner = Column(Boolean, nullable=False, default=False)
    valide_par_analyste = Column(Boolean, nullable=False, default=True)

    def __repr__(self):
        return f"<Selecteur {self.valeur} ({self.categorie.value})>"


# ---------------------------------------------------------------------
# ExclusionFauxPositif (FR-11)
# ---------------------------------------------------------------------

class ExclusionFauxPositif(Base):
    __tablename__ = "exclusions_faux_positifs"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    motif = Column(Text, nullable=False)
    ajoute_par = Column(String(255), nullable=False)  # identifiant analyste, pas de nom personnel
    date_ajout = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    def __repr__(self):
        return f"<ExclusionFauxPositif {self.motif[:50]}>"


# ---------------------------------------------------------------------
# JournalAudit (FR-17 - append-only)
# ---------------------------------------------------------------------

class JournalAudit(Base):
    __tablename__ = "journal_audit"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    horodatage = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    source_id = Column(String(36), ForeignKey("sources.id"), nullable=True)
    resultat = Column(SAEnum(ResultatAudit), nullable=False)
    details = Column(Text, nullable=True)  # message d'erreur eventuel, jamais de contenu de page

    source = relationship("Source", back_populates="audits")

    def __repr__(self):
        return f"<JournalAudit {self.horodatage} - {self.resultat.value}>"

# ---------------------------------------------------------------------
# User (FR-24 - authentification des analystes)
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# User (FR-24 - authentification + gestion des privileges)
# ---------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    nom_utilisateur = Column(String(100), nullable=False, unique=True)
    mot_de_passe_hash = Column(String(255), nullable=False)
    role = Column(SAEnum(RoleUtilisateur), nullable=False, default=RoleUtilisateur.USER)
    actif = Column(Boolean, nullable=False, default=True)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    def __repr__(self):
        return f"<User {self.nom_utilisateur} ({self.role.value})>"

# ---------------------------------------------------------------------
# Alerte (FR-25/FR-26 - alertes multi-canal)
# ---------------------------------------------------------------------

class CanalAlerte(enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    INTERFACE = "interface"


class StatutEnvoiAlerte(enum.Enum):
    EN_ATTENTE = "en_attente"
    ENVOYEE = "envoyee"
    ECHEC = "echec"


class Alerte(Base):
    __tablename__ = "alertes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    exposition_id = Column(String(36), ForeignKey("expositions.id"), nullable=False)

    canal = Column(SAEnum(CanalAlerte), nullable=False)
    statut_envoi = Column(SAEnum(StatutEnvoiAlerte), nullable=False, default=StatutEnvoiAlerte.EN_ATTENTE)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    date_envoi = Column(DateTime(timezone=True), nullable=True)
    lue = Column(Boolean, nullable=False, default=False)  # pour affichage interface (FR-25)
    details_echec = Column(Text, nullable=True)  # message d'erreur si echec d'envoi

    exposition = relationship("Exposition")

    def __repr__(self):
        return f"<Alerte {self.canal.value} - {self.statut_envoi.value}>"

# ---------------------------------------------------------------------
# ConfigurationSysteme (parametres modifiables par admin/super_admin)
# ---------------------------------------------------------------------

class ConfigurationSysteme(Base):
    __tablename__ = "configuration_systeme"

    cle = Column(String(100), primary_key=True)
    valeur = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    def __repr__(self):
        return f"<ConfigurationSysteme {self.cle}={self.valeur}>"