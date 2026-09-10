"""
FR-08 - Seed enrichi du catalogue de sélecteurs camerounais.

Objectifs :
- enrichir le catalogue existant avec des institutions, administrations,
  banques, opérateurs, universités, entreprises stratégiques et géographie ;
- conserver le mécanisme d'insertion idempotent du projet ;
- ne pas insérer de noms de personnes physiques ;
- limiter les sélecteurs extrêmement génériques aux catégories contextuelles.

Compatibilité :
- s'appuie sur app.db et app.models comme le seed d'origine ;
- utilise les catégories déjà présentes dans le projet :
  DOMAINE, TELEPHONE, MINISTERE, AGENCE_GOUVERNEMENTALE,
  BANQUE, MICROFINANCE, TELECOM, UNIVERSITE,
  ENTREPRISE, VILLE_REGION.

Important :
- Les sélecteurs courts/génériques (ex. ART, CBC, CCA, INS) peuvent produire
  des faux positifs. Ils restent présents pour la couverture, mais il est
  recommandé de leur attribuer un poids faible dans le moteur de scoring.
"""

import logging

from app.db import get_session, init_db
from app.models import Categorie, Selecteur


class CategorieSelecteur:
    """
    Noms des categories par defaut. Les categories vivent desormais en base
    et sont gerees par l'administrateur ; ces constantes gardent le
    catalogue ci-dessous lisible et inchange, et sont resolues en
    categories reelles (creees si absentes) au moment du seed.

    Les libelles doivent rester identiques a ceux de la migration
    e3a9f6c1d072, qui a cree ces categories sur les bases existantes.
    """
    DOMAINE = "Domaine internet"
    TELEPHONE = "Téléphone"
    MINISTERE = "Ministère"
    AGENCE_GOUVERNEMENTALE = "Agence gouvernementale"
    BANQUE = "Banque"
    MICROFINANCE = "Microfinance"
    TELECOM = "Télécommunications"
    UNIVERSITE = "Université"
    ENTREPRISE = "Entreprise"
    VILLE_REGION = "Ville / région"

    # Noms de lieux generiques : la regle "liste de pays" s'y applique.
    LIEUX_GENERIQUES = {VILLE_REGION}


def _categorie(session, cache, nom):
    """Categorie par son nom, creee au besoin (base neuve)."""
    if nom not in cache:
        categorie = session.query(Categorie).filter_by(nom=nom).first()
        if categorie is None:
            categorie = Categorie(
                nom=nom, lieu_generique=nom in CategorieSelecteur.LIEUX_GENERIQUES,
            )
            session.add(categorie)
            session.flush()
        cache[nom] = categorie
    return cache[nom]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _pairs(values, category):
    return [(value, category) for value in values]


# ============================================================================
# Catalogue enrichi
# ============================================================================

SEED_SELECTEURS_ENRICHIS = [

    # ------------------------------------------------------------------------
    # DOMAINES
    # ------------------------------------------------------------------------
    (".cm", CategorieSelecteur.DOMAINE),
    (".gov.cm", CategorieSelecteur.DOMAINE),
    (".edu.cm", CategorieSelecteur.DOMAINE),
    (".net.cm", CategorieSelecteur.DOMAINE),
    (".org.cm", CategorieSelecteur.DOMAINE),
    (".com.cm", CategorieSelecteur.DOMAINE),

    # ------------------------------------------------------------------------
    # TELEPHONE
    # ------------------------------------------------------------------------
    ("+237", CategorieSelecteur.TELEPHONE),
    ("00237", CategorieSelecteur.TELEPHONE),

    # ------------------------------------------------------------------------
    # MINISTERES
    # ------------------------------------------------------------------------
    ("Ministere des Finances", CategorieSelecteur.MINISTERE),
    ("MINFI", CategorieSelecteur.MINISTERE),

    ("Ministere de la Sante Publique", CategorieSelecteur.MINISTERE),
    ("MINSANTE", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Administration Territoriale", CategorieSelecteur.MINISTERE),
    ("MINAT", CategorieSelecteur.MINISTERE),

    ("Ministere des Postes et Telecommunications", CategorieSelecteur.MINISTERE),
    ("MINPOSTEL", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Enseignement Superieur", CategorieSelecteur.MINISTERE),
    ("MINESUP", CategorieSelecteur.MINISTERE),

    ("Ministere de la Justice", CategorieSelecteur.MINISTERE),
    ("MINJUSTICE", CategorieSelecteur.MINISTERE),

    ("Ministere des Relations Exterieures", CategorieSelecteur.MINISTERE),
    ("MINREX", CategorieSelecteur.MINISTERE),

    ("Ministere de la Defense", CategorieSelecteur.MINISTERE),
    ("MINDEF", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Education de Base", CategorieSelecteur.MINISTERE),
    ("MINEDUB", CategorieSelecteur.MINISTERE),

    ("Ministere des Enseignements Secondaires", CategorieSelecteur.MINISTERE),
    ("MINESEC", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Agriculture et du Developpement Rural", CategorieSelecteur.MINISTERE),
    ("MINADER", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Elevage, des Peches et des Industries Animales", CategorieSelecteur.MINISTERE),
    ("MINEPIA", CategorieSelecteur.MINISTERE),

    ("Ministere des Domaines, du Cadastre et des Affaires Foncieres", CategorieSelecteur.MINISTERE),
    ("MINDCAF", CategorieSelecteur.MINISTERE),

    ("Ministere du Commerce", CategorieSelecteur.MINISTERE),
    ("MINCOMMERCE", CategorieSelecteur.MINISTERE),

    ("Ministere des Mines, de l'Industrie et du Developpement Technologique", CategorieSelecteur.MINISTERE),
    ("MINMIDT", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Eau et de l'Energie", CategorieSelecteur.MINISTERE),
    ("MINEE", CategorieSelecteur.MINISTERE),

    ("Ministere des Travaux Publics", CategorieSelecteur.MINISTERE),
    ("MINTP", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Habitat et du Developpement Urbain", CategorieSelecteur.MINISTERE),
    ("MINHDU", CategorieSelecteur.MINISTERE),

    ("Ministere du Tourisme et des Loisirs", CategorieSelecteur.MINISTERE),
    ("MINTOUL", CategorieSelecteur.MINISTERE),

    ("Ministere des Petites et Moyennes Entreprises, de l'Economie Sociale et de l'Artisanat",
     CategorieSelecteur.MINISTERE),
    ("MINPMEESA", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Emploi et de la Formation Professionnelle", CategorieSelecteur.MINISTERE),
    ("MINEFOP", CategorieSelecteur.MINISTERE),

    ("Ministere du Travail et de la Securite Sociale", CategorieSelecteur.MINISTERE),
    ("MINTSS", CategorieSelecteur.MINISTERE),

    ("Ministere de la Communication", CategorieSelecteur.MINISTERE),
    ("MINCOM", CategorieSelecteur.MINISTERE),

    ("Ministere des Sports et de l'Education Physique", CategorieSelecteur.MINISTERE),
    ("MINSEP", CategorieSelecteur.MINISTERE),

    ("Ministere de la Jeunesse et de l'Education Civique", CategorieSelecteur.MINISTERE),
    ("MINJEC", CategorieSelecteur.MINISTERE),

    ("Ministere des Affaires Sociales", CategorieSelecteur.MINISTERE),
    ("MINAS", CategorieSelecteur.MINISTERE),

    ("Ministere de la Promotion de la Femme et de la Famille", CategorieSelecteur.MINISTERE),
    ("MINPROFF", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Environnement, de la Protection de la Nature et du Developpement Durable",
     CategorieSelecteur.MINISTERE),
    ("MINEPDED", CategorieSelecteur.MINISTERE),

    ("Ministere des Forets et de la Faune", CategorieSelecteur.MINISTERE),
    ("MINFOF", CategorieSelecteur.MINISTERE),

    ("Ministere de la Decentralisation et du Developpement Local", CategorieSelecteur.MINISTERE),
    ("MINDDEVEL", CategorieSelecteur.MINISTERE),

    ("Ministere de l'Economie, de la Planification et de l'Amenagement du Territoire",
     CategorieSelecteur.MINISTERE),
    ("MINEPAT", CategorieSelecteur.MINISTERE),

    ("Ministere de la Recherche Scientifique et de l'Innovation",
     CategorieSelecteur.MINISTERE),
    ("MINRESI", CategorieSelecteur.MINISTERE),

    ("Ministere de la Fonction Publique et de la Reforme Administrative",
     CategorieSelecteur.MINISTERE),
    ("MINFOPRA", CategorieSelecteur.MINISTERE),

    ("Ministere des Marches Publics", CategorieSelecteur.MINISTERE),
    ("MINMAP", CategorieSelecteur.MINISTERE),

    ("Ministere des Arts et de la Culture", CategorieSelecteur.MINISTERE),
    ("MINAC", CategorieSelecteur.MINISTERE),

    ("Ministere des Transports", CategorieSelecteur.MINISTERE),
    ("MINT", CategorieSelecteur.MINISTERE),

    # ------------------------------------------------------------------------
    # PRESIDENCE / PARLEMENT / AUTORITES PUBLIQUES
    # ------------------------------------------------------------------------
    ("Presidence de la Republique du Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Presidence de la Republique", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("PRC", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Services du Premier Ministre", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Services du PM", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Premier Ministre", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("SPM", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Assemblee Nationale", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("National Assembly Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Senat", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Senate Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Conseil Constitutionnel", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Constitutional Council Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Cour Supreme", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Supreme Court Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Chambre des Comptes", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Conseil Economique et Social", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Controle Superieur de l'Etat", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CONSUPE", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Commission Nationale Anti-Corruption", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CONAC", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Elections Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ELECAM", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Commission des Droits de l'Homme du Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CDHC", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Conseil National de la Communication", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CNC", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Autorite Aeronautique", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CCAA", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Cameroon Civil Aviation Authority", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    # ------------------------------------------------------------------------
    # ADMINISTRATIONS / AGENCES
    # ------------------------------------------------------------------------
    ("Direction Generale des Impots", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("DGI", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Cameroon Tax Administration", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Direction Generale des Douanes", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("DGD", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Cameroon Customs", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Tresor Public", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Tresor Public Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Direction Generale du Tresor", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("DGTCFM", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence Nationale des Technologies de l'Information et de la Communication",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ANTIC", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence de Regulation des Telecommunications",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ART", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Centre National de Developpement de l'Informatique",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CENADI", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Delegation Generale a la Surete Nationale",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("DGSN", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Surete Nationale", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("National Security Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Direction Generale de la Recherche Exterieure",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("DGRE", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Institut National de la Statistique",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("INS", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence Nationale d'Investigation Financiere",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ANIF", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence de Regulation des Marches Publics",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ARMP", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence Nationale des Affaires Maritimes",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ANAM", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence d'Electrification Rurale",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("AER", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence de Promotion des Investissements",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("API", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence de Promotion des Exportations",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("APEX", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence de Promotion des Petites et Moyennes Entreprises",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("APME", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence de Promotion des Normes", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ANOR", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Agence des Normes et de la Qualite", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Ecole Nationale d'Administration et de Magistrature",
     CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ENAM", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    # ------------------------------------------------------------------------
    # BANQUES - noms et alias
    # ------------------------------------------------------------------------
    ("Afriland First Bank", CategorieSelecteur.BANQUE),
    ("Afriland First Bank Cameroon", CategorieSelecteur.BANQUE),
    ("AFB", CategorieSelecteur.BANQUE),

    ("BICEC", CategorieSelecteur.BANQUE),
    ("Banque Internationale du Cameroun pour l'Epargne et le Credit",
     CategorieSelecteur.BANQUE),

    ("Societe Generale Cameroun", CategorieSelecteur.BANQUE),
    ("SGC Cameroun", CategorieSelecteur.BANQUE),
    ("SGBC", CategorieSelecteur.BANQUE),

    ("SCB Cameroun", CategorieSelecteur.BANQUE),
    ("SCB", CategorieSelecteur.BANQUE),
    ("Societe Commerciale de Banque Cameroun", CategorieSelecteur.BANQUE),

    ("Banque Atlantique Cameroun", CategorieSelecteur.BANQUE),
    ("Banque Atlantique du Cameroun", CategorieSelecteur.BANQUE),
    ("BACM", CategorieSelecteur.BANQUE),

    ("BGFI Bank Cameroun", CategorieSelecteur.BANQUE),
    ("BGFI Bank", CategorieSelecteur.BANQUE),

    ("NFC Bank", CategorieSelecteur.BANQUE),
    ("NFC Bank Cameroon", CategorieSelecteur.BANQUE),

    ("Commercial Bank of Cameroon", CategorieSelecteur.BANQUE),
    ("CBC", CategorieSelecteur.BANQUE),

    ("La Regionale Bank", CategorieSelecteur.BANQUE),
    ("La Regionale", CategorieSelecteur.BANQUE),

    ("Union Bank of Cameroon", CategorieSelecteur.BANQUE),
    ("UBC", CategorieSelecteur.BANQUE),

    ("United Bank for Africa", CategorieSelecteur.BANQUE),
    ("UBA Cameroon", CategorieSelecteur.BANQUE),
    ("UBA Cameroun", CategorieSelecteur.BANQUE),

    ("Ecobank Cameroon", CategorieSelecteur.BANQUE),
    ("Ecobank Cameroun", CategorieSelecteur.BANQUE),

    ("Standard Chartered Bank Cameroon", CategorieSelecteur.BANQUE),
    ("Standard Chartered Cameroun", CategorieSelecteur.BANQUE),

    ("Citibank Cameroon", CategorieSelecteur.BANQUE),
    ("Citibank Cameroun", CategorieSelecteur.BANQUE),
    ("Citi Cameroon", CategorieSelecteur.BANQUE),

    ("CCA Bank", CategorieSelecteur.BANQUE),
    ("CCA Bank Cameroun", CategorieSelecteur.BANQUE),
    ("Credit Communautaire d'Afrique", CategorieSelecteur.BANQUE),
    ("CCA", CategorieSelecteur.BANQUE),

    ("Credit Foncier du Cameroun", CategorieSelecteur.BANQUE),
    ("CFC", CategorieSelecteur.BANQUE),

    ("Access Bank Cameroon", CategorieSelecteur.BANQUE),
    ("Access Bank Cameroun", CategorieSelecteur.BANQUE),

    ("BANGE Bank Cameroon", CategorieSelecteur.BANQUE),
    ("BANGE Bank Cameroun", CategorieSelecteur.BANQUE),
    ("BANGE", CategorieSelecteur.BANQUE),

    ("Banque Centrale des Etats de l'Afrique Centrale", CategorieSelecteur.BANQUE),
    ("BEAC", CategorieSelecteur.BANQUE),

    # ------------------------------------------------------------------------
    # MICROFINANCE / ETABLISSEMENTS FINANCIERS
    # ------------------------------------------------------------------------
    ("Express Union", CategorieSelecteur.MICROFINANCE),
    ("Express Union Finance", CategorieSelecteur.MICROFINANCE),
    ("CamCCUL", CategorieSelecteur.MICROFINANCE),
    ("Cameroon Cooperative Credit Union League", CategorieSelecteur.MICROFINANCE),
    ("Advans Cameroun", CategorieSelecteur.MICROFINANCE),
    ("Advans Cameroon", CategorieSelecteur.MICROFINANCE),
    ("ACEP Cameroun", CategorieSelecteur.MICROFINANCE),
    ("ACEP Cameroon", CategorieSelecteur.MICROFINANCE),

    # ------------------------------------------------------------------------
    # TELECOMS / COMMUNICATIONS
    # ------------------------------------------------------------------------
    ("MTN Cameroon", CategorieSelecteur.TELECOM),
    ("MTN Cameroun", CategorieSelecteur.TELECOM),
    ("MTN", CategorieSelecteur.TELECOM),

    ("Orange Cameroun", CategorieSelecteur.TELECOM),
    ("Orange Cameroon", CategorieSelecteur.TELECOM),
    ("Orange", CategorieSelecteur.TELECOM),

    ("Camtel", CategorieSelecteur.TELECOM),
    ("CAMTEL", CategorieSelecteur.TELECOM),
    ("Cameroon Telecommunications", CategorieSelecteur.TELECOM),

    ("Nexttel", CategorieSelecteur.TELECOM),
    ("Nexttel Cameroon", CategorieSelecteur.TELECOM),

    ("Viettel Cameroun", CategorieSelecteur.TELECOM),
    ("Viettel Cameroon", CategorieSelecteur.TELECOM),

    ("Blue SA", CategorieSelecteur.TELECOM),
    ("Blue Cameroon", CategorieSelecteur.TELECOM),

    ("CAMPOST", CategorieSelecteur.TELECOM),
    ("Cameroon Postal Services", CategorieSelecteur.TELECOM),

    # ------------------------------------------------------------------------
    # UNIVERSITES D'ETAT / GRANDES ECOLES
    # ------------------------------------------------------------------------
    ("Universite de Bamenda", CategorieSelecteur.UNIVERSITE),
    ("University of Bamenda", CategorieSelecteur.UNIVERSITE),
    ("UBa", CategorieSelecteur.UNIVERSITE),

    ("Universite de Bertoua", CategorieSelecteur.UNIVERSITE),
    ("University of Bertoua", CategorieSelecteur.UNIVERSITE),

    ("Universite de Buea", CategorieSelecteur.UNIVERSITE),
    ("University of Buea", CategorieSelecteur.UNIVERSITE),
    ("UB", CategorieSelecteur.UNIVERSITE),

    ("Universite de Douala", CategorieSelecteur.UNIVERSITE),
    ("University of Douala", CategorieSelecteur.UNIVERSITE),

    ("Universite de Dschang", CategorieSelecteur.UNIVERSITE),
    ("University of Dschang", CategorieSelecteur.UNIVERSITE),

    ("Universite d'Ebolowa", CategorieSelecteur.UNIVERSITE),
    ("University of Ebolowa", CategorieSelecteur.UNIVERSITE),

    ("Universite de Garoua", CategorieSelecteur.UNIVERSITE),
    ("University of Garoua", CategorieSelecteur.UNIVERSITE),

    ("Universite de Maroua", CategorieSelecteur.UNIVERSITE),
    ("University of Maroua", CategorieSelecteur.UNIVERSITE),

    ("Universite de Ngaoundere", CategorieSelecteur.UNIVERSITE),
    ("University of Ngaoundere", CategorieSelecteur.UNIVERSITE),

    ("Universite de Yaounde I", CategorieSelecteur.UNIVERSITE),
    ("Universite de Yaounde 1", CategorieSelecteur.UNIVERSITE),
    ("University of Yaounde I", CategorieSelecteur.UNIVERSITE),
    ("UY1", CategorieSelecteur.UNIVERSITE),

    ("Universite de Yaounde II", CategorieSelecteur.UNIVERSITE),
    ("Universite de Yaounde 2", CategorieSelecteur.UNIVERSITE),
    ("University of Yaounde II", CategorieSelecteur.UNIVERSITE),
    ("UY2", CategorieSelecteur.UNIVERSITE),

    ("Universite Catholique d'Afrique Centrale", CategorieSelecteur.UNIVERSITE),
    ("UCAC", CategorieSelecteur.UNIVERSITE),

    ("Institut des Relations Internationales du Cameroun", CategorieSelecteur.UNIVERSITE),
    ("IRIC", CategorieSelecteur.UNIVERSITE),

    ("Ecole Nationale d'Administration et de Magistrature", CategorieSelecteur.UNIVERSITE),
    ("ENAM", CategorieSelecteur.UNIVERSITE),

    ("Ecole Polytechnique de Yaounde", CategorieSelecteur.UNIVERSITE),
    ("Ecole Nationale Superieure Polytechnique de Yaounde", CategorieSelecteur.UNIVERSITE),
    ("ENSP Yaounde", CategorieSelecteur.UNIVERSITE),
    ("Ecole Nationale Superieure des Postes et Telecommunications",
     CategorieSelecteur.UNIVERSITE),
    ("SUP'PTIC", CategorieSelecteur.UNIVERSITE),

    ("Institut Universitaire de la Cote", CategorieSelecteur.UNIVERSITE),
    ("IUC", CategorieSelecteur.UNIVERSITE),

    # ------------------------------------------------------------------------
    # ENTREPRISES / INFRASTRUCTURES STRATEGIQUES
    # ------------------------------------------------------------------------
    ("Societe Nationale des Hydrocarbures", CategorieSelecteur.ENTREPRISE),
    ("SNH", CategorieSelecteur.ENTREPRISE),
    ("National Hydrocarbons Corporation", CategorieSelecteur.ENTREPRISE),

    ("Societe Nationale de Raffinage", CategorieSelecteur.ENTREPRISE),
    ("SONARA", CategorieSelecteur.ENTREPRISE),

    ("Societe Nationale de Transport d'Electricite", CategorieSelecteur.ENTREPRISE),
    ("SONATREL", CategorieSelecteur.ENTREPRISE),

    ("Electricity Development Corporation", CategorieSelecteur.ENTREPRISE),
    ("EDC", CategorieSelecteur.ENTREPRISE),

    ("ENEO Cameroon", CategorieSelecteur.ENTREPRISE),
    ("ENEO Cameroun", CategorieSelecteur.ENTREPRISE),
    ("AES Sonel", CategorieSelecteur.ENTREPRISE),

    ("Camwater", CategorieSelecteur.ENTREPRISE),
    ("Cameroon Water Utilities", CategorieSelecteur.ENTREPRISE),
    ("Camerounaise des Eaux", CategorieSelecteur.ENTREPRISE),
    ("CDE", CategorieSelecteur.ENTREPRISE),

    ("Camair-Co", CategorieSelecteur.ENTREPRISE),
    ("Cameroon Airlines Corporation", CategorieSelecteur.ENTREPRISE),
    ("CAMAIR-CO", CategorieSelecteur.ENTREPRISE),

    ("Camrail", CategorieSelecteur.ENTREPRISE),
    ("Cameroon Railways", CategorieSelecteur.ENTREPRISE),

    ("Port Autonome de Douala", CategorieSelecteur.ENTREPRISE),
    ("Douala Port", CategorieSelecteur.ENTREPRISE),
    ("PAD", CategorieSelecteur.ENTREPRISE),

    ("Port Autonome de Kribi", CategorieSelecteur.ENTREPRISE),
    ("Kribi Port", CategorieSelecteur.ENTREPRISE),
    ("PAK", CategorieSelecteur.ENTREPRISE),

    ("Douala International Terminal", CategorieSelecteur.ENTREPRISE),
    ("DIT", CategorieSelecteur.ENTREPRISE),

    ("Hydro Mekin", CategorieSelecteur.ENTREPRISE),
    ("Kribi Power Development Company", CategorieSelecteur.ENTREPRISE),
    ("KPDC", CategorieSelecteur.ENTREPRISE),

    ("Caisse Nationale de Prevoyance Sociale", CategorieSelecteur.ENTREPRISE),
    ("CNPS", CategorieSelecteur.ENTREPRISE),

    ("SODECOTON", CategorieSelecteur.ENTREPRISE),
    ("Societe de Developpement du Coton", CategorieSelecteur.ENTREPRISE),

    ("SODECAO", CategorieSelecteur.ENTREPRISE),
    ("Cameroon Development Corporation", CategorieSelecteur.ENTREPRISE),
    ("CDC Cameroon", CategorieSelecteur.ENTREPRISE),

    ("HYSACAM", CategorieSelecteur.ENTREPRISE),
    ("Societe Camerounaise de Raffinage", CategorieSelecteur.ENTREPRISE),

    ("Chantier Naval et Industriel du Cameroun", CategorieSelecteur.ENTREPRISE),
    ("CNIC", CategorieSelecteur.ENTREPRISE),

    ("Cameroon Postal Services", CategorieSelecteur.ENTREPRISE),
    ("CAMPOST", CategorieSelecteur.ENTREPRISE),

    # ------------------------------------------------------------------------
    # VILLES / REGIONS
    # ------------------------------------------------------------------------
    ("Yaounde", CategorieSelecteur.VILLE_REGION),
    ("Yaoundé", CategorieSelecteur.VILLE_REGION),

    ("Douala", CategorieSelecteur.VILLE_REGION),

    ("Bafoussam", CategorieSelecteur.VILLE_REGION),
    ("Garoua", CategorieSelecteur.VILLE_REGION),

    ("Bamenda", CategorieSelecteur.VILLE_REGION),
    ("Buea", CategorieSelecteur.VILLE_REGION),
    ("Buéa", CategorieSelecteur.VILLE_REGION),

    ("Ebolowa", CategorieSelecteur.VILLE_REGION),
    ("Maroua", CategorieSelecteur.VILLE_REGION),
    ("Ngaoundere", CategorieSelecteur.VILLE_REGION),
    ("Ngaoundéré", CategorieSelecteur.VILLE_REGION),
    ("Bertoua", CategorieSelecteur.VILLE_REGION),
    ("Kribi", CategorieSelecteur.VILLE_REGION),
    ("Limbe", CategorieSelecteur.VILLE_REGION),
    ("Kumba", CategorieSelecteur.VILLE_REGION),
    ("Edea", CategorieSelecteur.VILLE_REGION),
    ("Edéa", CategorieSelecteur.VILLE_REGION),
    ("Nkongsamba", CategorieSelecteur.VILLE_REGION),
    ("Dschang", CategorieSelecteur.VILLE_REGION),
    ("Foumban", CategorieSelecteur.VILLE_REGION),
    ("Bafang", CategorieSelecteur.VILLE_REGION),
    ("Kousseri", CategorieSelecteur.VILLE_REGION),
    ("Mokolo", CategorieSelecteur.VILLE_REGION),
    ("Meiganga", CategorieSelecteur.VILLE_REGION),
    ("Bertoua", CategorieSelecteur.VILLE_REGION),
    ("Yagoua", CategorieSelecteur.VILLE_REGION),
    ("Mbalmayo", CategorieSelecteur.VILLE_REGION),
    ("Sangmelima", CategorieSelecteur.VILLE_REGION),
    ("Edea", CategorieSelecteur.VILLE_REGION),

    ("Adamaoua", CategorieSelecteur.VILLE_REGION),
    ("Centre", CategorieSelecteur.VILLE_REGION),
    ("Est", CategorieSelecteur.VILLE_REGION),
    ("Extreme-Nord", CategorieSelecteur.VILLE_REGION),
    ("Extreme Nord", CategorieSelecteur.VILLE_REGION),
    ("Littoral", CategorieSelecteur.VILLE_REGION),
    ("Nord", CategorieSelecteur.VILLE_REGION),
    ("Nord-Ouest", CategorieSelecteur.VILLE_REGION),
    ("Ouest", CategorieSelecteur.VILLE_REGION),
    ("Sud", CategorieSelecteur.VILLE_REGION),
    ("Sud-Ouest", CategorieSelecteur.VILLE_REGION),

    ("North West Region", CategorieSelecteur.VILLE_REGION),
    ("South West Region", CategorieSelecteur.VILLE_REGION),
    ("North Region Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Far North Region Cameroon", CategorieSelecteur.VILLE_REGION),
    ("West Region Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Littoral Region Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Centre Region Cameroon", CategorieSelecteur.VILLE_REGION),
    ("South Region Cameroon", CategorieSelecteur.VILLE_REGION),
    ("East Region Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Adamaoua Region", CategorieSelecteur.VILLE_REGION),

    ("Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Cameroun", CategorieSelecteur.VILLE_REGION),
    ("Republic of Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Republique du Cameroun", CategorieSelecteur.VILLE_REGION),

    # ------------------------------------------------------------------------
    # IDENTIFIANTS / TERMINOLOGIE ADMINISTRATIVE UTILE
    # ------------------------------------------------------------------------
    ("Republic of Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Republique du Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Etat du Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Government of Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Gouvernement du Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("National Identification Number Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CNI Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CNI", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("NIU Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Numero d'Identification Unique", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Identifiant Unique", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("RCCM Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("RCCM", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("Contribuable Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Numero de contribuable", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    ("NIF Cameroun", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("TIN Cameroon", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
]


# ============================================================================
# Seed idempotent
# ============================================================================

def seed():
    init_db()
    session = get_session()

    added_count = 0
    skipped_count = 0

    # Le projet possède déjà un SEED_SELECTEURS dans le seed initial.
    # On l'importe dynamiquement pour pouvoir utiliser ce fichier seul ou
    # en complément d'un seed existant.
    try:
        from app.matching.seed_selecteurs import SEED_SELECTEURS as SEED_ORIGINAL
    except (ImportError, AttributeError):
        SEED_ORIGINAL = []

    # Fusion + déduplication tout en conservant l'ordre.
    tous = list(SEED_ORIGINAL) + list(SEED_SELECTEURS_ENRICHIS)
    uniques = list(dict.fromkeys(tous))

    cache_categories = {}

    try:
        for valeur, nom_categorie in uniques:
            valeur = valeur.strip()

            if not valeur:
                continue

            categorie = _categorie(session, cache_categories, nom_categorie)

            existing = (
                session.query(Selecteur)
                .filter_by(
                    valeur=valeur,
                    categorie_id=categorie.id,
                )
                .first()
            )

            if existing:
                skipped_count += 1
                continue

            selecteur = Selecteur(
                valeur=valeur,
                categorie=categorie,
                actif=True,
                propose_par_ner=False,
                valide_par_analyste=True,
            )

            session.add(selecteur)
            added_count += 1

        session.commit()

        logger.info(
            "Seed termine : %d ajoutes, %d deja presents, %d uniques.",
            added_count,
            skipped_count,
            len(uniques),
        )

    except Exception:
        session.rollback()
        logger.exception("Erreur lors du seed des selecteurs.")
        raise

    finally:
        session.close()


if __name__ == "__main__":
    seed()
