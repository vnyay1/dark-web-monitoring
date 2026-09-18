"""
Modele de donnees SQLAlchemy - base sur le diagramme de classes valide.

Base sur FR-16 (liste la plus complete). A ajuster si l'encadrant tranche
en faveur de la liste restreinte de CN-03 (voir ambiguite 3 du rapport de suivi).

Respecte CN-04 : aucun champ ne doit jamais contenir de nom de personne,
numero CNI, telephone, email, mot de passe, hash, information financiere,
ou extrait d'un enregistrement divulgue.

SEULE EXCEPTION, par derogation validee par l'encadrant le 2026-09-18 :
SourceReference.texte_brut, le texte integral de l'annonce d'une entree qui
a produit une exposition, masque (cf. app/conservation.py).
"""

import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Integer,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, deferred, relationship

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

class StatutExposition(enum.Enum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    NOTIFIED = "notified"
    CLOSED = "closed"


class NiveauCriticite(enum.Enum):
    """
    FR-10 - Niveau de criticite d'une exposition, derive de son SCORE : les
    selecteurs distincts du catalogue trouves dans l'entree analysee,
    chacun compte pour son poids (1, sauf selecteur prioritaire).

    Remplace l'ancien score de confiance flottant : un analyste peut
    justifier "3 selecteurs camerounais distincts dans la meme annonce",
    la ou un 0.72 pondere n'etait explicable qu'en relisant le code.
    Les paliers sont regles par l'administrateur (cf. app.config_system).
    """
    FAIBLE = "faible"
    MOYENNE = "moyenne"
    ELEVEE = "elevee"
    CRITIQUE = "critique"


class TypeSource(enum.Enum):
    RANSOMWARE_SITE = "ransomware_site"
    PASTE = "paste"
    FORUM = "forum"
    TELEGRAM = "telegram"
    TEST_CLAIRNET = "test_clairnet"


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

# ---------------------------------------------------------------------
# Categorie (FR-13) - geree par l'administrateur
# ---------------------------------------------------------------------

class Categorie(Base):
    """
    Categorie d'un selecteur du catalogue (Ministere, Banque...). Une
    exposition porte les categories des selecteurs qui l'ont declenchee.

    Ces categories remplacent l'ancienne "nature de la fuite", deduite du
    texte par mots-cles et jugee trop peu fiable. Elles ne sont plus une
    enumeration figee dans le code : l'administrateur les cree, les renomme
    et les supprime depuis l'interface.

    lieu_generique : le selecteur est un nom de lieu (ville, region, pays)
    susceptible d'apparaitre dans une simple liste de pays sans viser
    d'entite camerounaise. La regle de faux positif correspondante
    (app.matching.exclusion) suit cet indicateur, et non un nom de
    categorie qu'un renommage casserait.

    prioritaire : secteur prioritaire au sens de FR-26 (administration,
    finance, telecommunications). Les alertes sur une exposition portant
    une telle categorie empruntent les canaux renforces (app.alerting.rules).
    Cet indicateur remplace le champ texte Exposition.secteur_activite, que
    rien ne renseignait.
    """
    __tablename__ = "categories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    nom = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    lieu_generique = Column(Boolean, nullable=False, default=False)
    prioritaire = Column(Boolean, nullable=False, default=False)
    date_creation = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    selecteurs = relationship("Selecteur", back_populates="categorie")

    def __repr__(self):
        return f"<Categorie {self.nom}>"


# Une exposition peut relever de plusieurs categories (une annonce citant
# un ministere et une banque), et une categorie concerne de nombreuses
# expositions.
exposition_categories = Table(
    "exposition_categories",
    Base.metadata,
    Column("exposition_id", String(36), ForeignKey("expositions.id"), primary_key=True),
    Column("categorie_id", String(36), ForeignKey("categories.id"), primary_key=True),
)


class Exposition(Base):
    __tablename__ = "expositions"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    nom_entite = Column(String(255), nullable=False)

    date_premiere_detection = Column(DateTime(timezone=True), nullable=False,
                                      default=utc_now)
    date_derniere_detection = Column(DateTime(timezone=True), nullable=False,
                                      default=utc_now)

    # FR-10 - criticite = score de l'entree : selecteurs DISTINCTS trouves,
    # chacun compte pour son poids (Selecteur.poids, 1 par defaut) ;
    # niveau_criticite en est le palier lisible. Les selecteurs eux-memes
    # sont enregistres par signalement (SourceReference.selecteurs_trouves).
    criticite = Column(Integer, nullable=False, default=0)
    niveau_criticite = Column(SAEnum(NiveauCriticite), nullable=False,
                               default=NiveauCriticite.FAIBLE)

    # Date de publication de l'annonce sur la source (pas du contenu
    # divulgue) : la plus recente connue, dupliquee depuis
    # SourceReference pour permettre tri et filtre sans jointure.
    date_publication_source = Column(DateTime(timezone=True), nullable=True)

    statut = Column(SAEnum(StatutExposition), nullable=False,
                     default=StatutExposition.NEW)

    sources = relationship(
        "SourceReference", back_populates="exposition",
        cascade="all, delete-orphan"
    )
    # Categories des selecteurs qui ont declenche l'exposition (FR-13).
    categories = relationship(
        "Categorie", secondary=exposition_categories, order_by=Categorie.nom,
    )

    alertes = relationship("Alerte", back_populates="exposition",
                            cascade="all, delete-orphan")

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

    # source_id relie le signalement a la Source surveillee, ce qui donne
    # acces a son NOM ("payload", "safepay"...). type_source seul ne
    # portait que la famille ("ransomware_site") : l'origine exacte d'une
    # exposition etait donc introuvable depuis l'interface.
    source_id = Column(String(36), ForeignKey("sources.id"), nullable=True)

    type_source = Column(SAEnum(TypeSource), nullable=False)
    reference_source = Column(String(500), nullable=False)  # URL/identifiant, jamais le contenu

    # Date de publication de l'annonce sur CETTE source. Une meme
    # exposition vue sur plusieurs sources a une date par signalement.
    date_publication = Column(DateTime(timezone=True), nullable=True)

    date_signalement = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    # DEROGATION CN-04/CN-05 (2026-09-18, validee par l'encadrant) : texte
    # integral de l'annonce, masque par
    # app.conservation.preparer_texte_conserve(), sans limite de duree.
    # Jamais le HTML de la page, jamais le texte d'une entree sans
    # exposition. deferred : charge seulement quand on le lit (endpoint
    # dedie), jamais par les listes ni les exports. date_texte_brut est posee
    # en meme temps que lui : c'est elle qu'on teste pour savoir si un texte
    # existe, sans le charger.
    texte_brut = deferred(Column(Text, nullable=True))
    date_texte_brut = Column(DateTime(timezone=True), nullable=True)

    # Selecteurs du catalogue trouves dans l'annonce, liste JSON de
    # {valeur, categorie_id, categorie, poids, occurrences, correspondances}
    # issue de l'analyse au score le plus eleve (cf.
    # app.conservation.conserver_selecteurs). Des termes du CATALOGUE, fige
    # a la detection : ce n'est pas une cle etrangere, supprimer ou renommer
    # un selecteur ne le modifie pas. NULL : signalement anterieur.
    selecteurs_trouves = Column(Text, nullable=True)

    exposition = relationship("Exposition", back_populates="sources")
    source = relationship("Source")

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

# Poids d'un selecteur dans la criticite : 1 pour un selecteur ordinaire,
# jusqu'a POIDS_MAXIMAL pour un selecteur que l'administrateur juge
# prioritaire (un nom de pays explicite, par exemple).
POIDS_NORMAL = 1
POIDS_MAXIMAL = 5


class Selecteur(Base):
    __tablename__ = "selecteurs"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    valeur = Column(String(255), nullable=False)
    categorie_id = Column(String(36), ForeignKey("categories.id"), nullable=False)
    actif = Column(Boolean, nullable=False, default=True)

    # FR-10 : ce que le selecteur apporte a la criticite de l'entree ou il
    # est trouve (cf. app.matching.criticite). Au-dela de POIDS_NORMAL, il
    # est dit "prioritaire".
    poids = Column(Integer, nullable=False, default=POIDS_NORMAL, server_default="1")

    categorie = relationship("Categorie", back_populates="selecteurs")

    def __repr__(self):
        return f"<Selecteur {self.valeur}>"


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

    exposition = relationship("Exposition", back_populates="alertes")

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

class HistoriqueRole(Base):
    __tablename__ = "historique_roles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_cible_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    modifie_par_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    ancien_role = Column(SAEnum(RoleUtilisateur), nullable=False)
    nouveau_role = Column(SAEnum(RoleUtilisateur), nullable=False)
    date_modification = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    user_cible = relationship("User", foreign_keys=[user_cible_id])
    modifie_par = relationship("User", foreign_keys=[modifie_par_id])

# ---------------------------------------------------------------------
# EntreeCollectee - file de travail du crawl incremental
# ---------------------------------------------------------------------

class StatutDetailEntree(enum.Enum):
    A_TRAITER = "a_traiter"      # vue en listing, detail pas encore recupere/analyse
    TRAITEE = "traitee"          # analysee, quel que soit le resultat du matching
    SANS_DETAIL = "sans_detail"  # source listing-only, ou pas de page de detail licite
    ECHEC = "echec"              # abandonnee apres MAX_ECHECS_DETAIL


class EntreeCollectee(Base):
    """
    File de travail TECHNIQUE du crawl incremental : elle memorise quelles
    entrees d'une source ont deja ete analysees, pour ne pas re-telecharger
    leur page de detail a chaque cycle (le cout serait non borne, et le
    martelement contraire a la collecte passive CN-09/CN-10).

    Ce n'est PAS un index de victimes. Conformite CN-03/CN-04 :

    1. identifiant_entree reference la page de PUBLICATION (l'annonce) sur
       la source surveillee - exactement la meme nature que
       SourceReference.reference_source, deja autorise par CN-03 sous
       "source". Ce n'est jamais un lien vers les donnees divulguees.
    2. La decision de considerer un lien comme visitable est centralisee
       dans BaseConnector.url_detail(). Quand le seul lien d'une entree
       pointe vers les donnees (orion_leaks) ou vers un site tiers hors
       perimetre (cmd_organization), l'identifiant est SYNTHETIQUE et non
       navigable ("h:<sha256>") : aucune URL n'est reconstructible depuis
       la base. Controle d'audit :
           SELECT identifiant_entree FROM entrees_collectees
            WHERE identifiant_entree LIKE 'http%';   -- doit etre vide
    3. Aucun nom d'entite, aucun extrait de texte, aucune empreinte du
       contenu n'est stocke : sinon la table constituerait de facto une
       base de toutes les victimes de ransomware du monde, hors de la
       finalite declaree (entites camerounaises).
    4. Retention limitee : purger_registre() supprime les lignes qui n'ont
       plus ete vues depuis 90 jours.
    """
    __tablename__ = "entrees_collectees"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_id = Column(String(36), ForeignKey("sources.id"), nullable=False)

    identifiant_entree = Column(String(500), nullable=False)

    statut_detail = Column(SAEnum(StatutDetailEntree), nullable=False,
                            default=StatutDetailEntree.A_TRAITER)

    date_premiere_vue = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    date_derniere_vue = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    date_detail_traite = Column(DateTime(timezone=True), nullable=True)

    nb_echecs_detail = Column(Integer, nullable=False, default=0)
    a_produit_exposition = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("source_id", "identifiant_entree", name="uq_entree_par_source"),
        Index("ix_entrees_source_statut", "source_id", "statut_detail"),
    )

    def __repr__(self):
        return f"<EntreeCollectee {self.identifiant_entree} [{self.statut_detail.value}]>"


# ---------------------------------------------------------------------
# Supervision du scheduler (FR-07)
# ---------------------------------------------------------------------

class StatutScheduler(enum.Enum):
    ARRETE = "arrete"
    EN_ATTENTE = "en_attente"           # planifie, en veille jusqu'a la prochaine echeance
    COLLECTE_EN_COURS = "collecte_en_cours"


class TypeEvenementCollecte(enum.Enum):
    DEBUT_CYCLE = "debut_cycle"
    DEBUT_SOURCE = "debut_source"
    FIN_SOURCE = "fin_source"
    NOUVELLE_EXPOSITION = "nouvelle_exposition"
    FIN_CYCLE = "fin_cycle"
    CIRCUIT_RENOUVELE = "circuit_renouvele"   # nouvelle IP de sortie Tor constatee
    # Echeance de collecte passee sans declenchement (cf. app.scheduler).
    # Aucune migration : colonne VARCHAR(19) sans contrainte, nom de 16
    # caracteres - meme cas que CIRCUIT_RENOUVELE (revision c7d2a8e51f06).
    ECHEANCE_MANQUEE = "echeance_manquee"


class EtatScheduler(Base):
    """
    Ligne UNIQUE (id=1) portant l'etat du processus de collecte.

    Elle remplit deux roles :

    1. VERROU D'INSTANCE UNIQUE. Le scheduler tourne dans un processus
       separe du serveur web ; sans etat partage, rien n'empechait de
       lancer une seconde collecte par-dessus la premiere (depuis
       l'interface, ou par un `python -m app.scheduler` en ligne de
       commande). Le verrou vivant en BASE et non en memoire, il vaut
       pour les deux chemins.

       La peremption par heartbeat est indispensable : un processus tue
       (kill -9, coupure de la VM) ne libere pas son verrou, et sans
       expiration le scheduler serait definitivement bloque.

    2. TABLEAU DE BORD. L'interface de supervision lit ici la source en
       cours d'analyse, l'heure de lancement et la prochaine echeance.

    CN-03/CN-04 : uniquement des metadonnees d'exploitation (etat, dates,
    nom de source, PID). Aucune donnee collectee.
    """
    __tablename__ = "etat_scheduler"

    id = Column(Integer, primary_key=True, default=1)

    actif = Column(Boolean, nullable=False, default=False)
    statut = Column(SAEnum(StatutScheduler), nullable=False,
                     default=StatutScheduler.ARRETE)

    pid = Column(Integer, nullable=True)
    hostname = Column(String(255), nullable=True)

    demarre_le = Column(DateTime(timezone=True), nullable=True)
    heartbeat = Column(DateTime(timezone=True), nullable=True)

    source_en_cours = Column(String(255), nullable=True)

    derniere_execution = Column(DateTime(timezone=True), nullable=True)
    prochaine_execution = Column(DateTime(timezone=True), nullable=True)
    derniere_stats = Column(Text, nullable=True)  # resume JSON du dernier cycle

    collecte_immediate_demandee = Column(Boolean, nullable=False, default=False)

    # Bornes du cycle de collecte en cours ou du dernier cycle : le "temps
    # ecoule" affiche est la duree du CYCLE, figee en veille, et non l'age
    # du processus, qui continuait d'avancer pendant la veille.
    debut_collecte = Column(DateTime(timezone=True), nullable=True)
    fin_collecte = Column(DateTime(timezone=True), nullable=True)

    # Noeud de sortie Tor, publie par le processus scheduler (le serveur web
    # ne parle jamais a Tor). Une IP de relais Tor est une donnee
    # d'infrastructure publique, pas une donnee personnelle (CN-04).
    ip_sortie = Column(String(64), nullable=True)
    ip_sortie_precedente = Column(String(64), nullable=True)
    ip_verifiee_le = Column(DateTime(timezone=True), nullable=True)
    ip_changee_le = Column(DateTime(timezone=True), nullable=True)
    verification_ip_demandee = Column(Boolean, nullable=False, default=False)

    # Version du code (commit) que le processus a chargee a son demarrage,
    # cf. app.version : l'interface previent quand elle differe du code
    # installe, c'est-a-dire quand un redemarrage manque apres un git pull.
    version_code = Column(String(40), nullable=True)

    def __repr__(self):
        return f"<EtatScheduler {self.statut.value} pid={self.pid}>"


class EvenementCollecte(Base):
    """
    Journal des evenements d'un cycle de collecte, consomme par la console
    de supervision en temps reel.

    Cle primaire ENTIERE (et non UUID comme le reste du modele) : la
    console demande "les evenements posterieurs a l'id X", ce qui exige un
    ordre total bon marche. Un UUID obligerait a trier par horodatage, non
    unique a la milliseconde pres.

    LES ERREURS N'ONT PAS LEUR PLACE ICI : elles sont deja journalisees
    dans JournalAudit par BaseConnector, avec le detail necessaire a
    l'audit (FR-17), et consultables dans la page dediee. Les dupliquer
    ici noierait le fil de supervision, dont l'objet est de montrer
    l'avancement et les detections.

    Retention courte (purger_evenements) : c'est un fil d'activite, pas
    une archive.
    """
    __tablename__ = "evenements_collecte"

    id = Column(Integer, primary_key=True, autoincrement=True)

    horodatage = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    type_evenement = Column(SAEnum(TypeEvenementCollecte), nullable=False)

    source = Column(String(255), nullable=True)
    message = Column(String(500), nullable=False)

    exposition_id = Column(String(36), ForeignKey("expositions.id"), nullable=True)

    __table_args__ = (
        Index("ix_evenements_horodatage", "horodatage"),
    )

    def __repr__(self):
        return f"<EvenementCollecte {self.type_evenement.value} {self.message[:40]}>"
