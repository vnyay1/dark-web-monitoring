"""
FR-08 - Seed initial du catalogue de selecteurs.

Ce script peuple la table Selecteur avec un echantillon representatif.
Les selecteurs concernant les ministeres utilisent les noms d'INSTITUTIONS
(stables), jamais les noms de ministres (personnes physiques, changeants,
et hors-sujet - CN-04 interdit tout nom de personne).

Cette liste est un POINT DE DEPART a valider/completer avec l'encadrant.
Le catalogue reste configurable (FR-08) : ajouter un selecteur ne
necessite qu'une insertion en base, aucune modification de code.
"""

import logging
from app.db import get_session, init_db
from app.models import Selecteur, CategorieSelecteur

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


SEED_SELECTEURS = [
    # --- Domaines ---
    (".cm", CategorieSelecteur.DOMAINE),
    (".gov.cm", CategorieSelecteur.DOMAINE),

    # --- Telephone ---
    ("+237", CategorieSelecteur.TELEPHONE),

    # --- Ministeres (noms d'institutions, jamais de noms de personnes - CN-04) ---
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
    ("Ministere des Petites et Moyennes Entreprises", CategorieSelecteur.MINISTERE),
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
    ("Ministere de l'Environnement, de la Protection de la Nature et du Developpement Durable", CategorieSelecteur.MINISTERE),
    ("MINEPDED", CategorieSelecteur.MINISTERE),
    ("Ministere des Forets et de la Faune", CategorieSelecteur.MINISTERE),
    ("MINFOF", CategorieSelecteur.MINISTERE),
    ("Ministere de la Decentralisation et du Developpement Local", CategorieSelecteur.MINISTERE),
    ("MINDDEVEL", CategorieSelecteur.MINISTERE),
    ("Ministere de l'Economie, de la Planification et de l'Amenagement du Territoire", CategorieSelecteur.MINISTERE),
    ("MINEPAT", CategorieSelecteur.MINISTERE),

    # --- Agences gouvernementales ---
    ("ANTIC", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("ART", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),  # Agence de Regulation des Telecommunications
    ("CENADI", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("CAMTEL", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Delegation Generale a la Surete Nationale", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("DGSN", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Direction Generale de la Recherche Exterieure", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("DGRE", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("Institut National de la Statistique", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),
    ("INS", CategorieSelecteur.AGENCE_GOUVERNEMENTALE),

    # --- Banques (echantillon a valider/completer) ---
    ("Afriland First Bank", CategorieSelecteur.BANQUE),
    ("BICEC", CategorieSelecteur.BANQUE),
    ("SGC Cameroun", CategorieSelecteur.BANQUE),
    ("UBA Cameroun", CategorieSelecteur.BANQUE),
    ("Ecobank Cameroun", CategorieSelecteur.BANQUE),
    ("Standard Chartered Cameroun", CategorieSelecteur.BANQUE),
    ("SCB Cameroun", CategorieSelecteur.BANQUE),
    ("Banque Atlantique Cameroun", CategorieSelecteur.BANQUE),
    ("BGFIBank Cameroun", CategorieSelecteur.BANQUE),
    ("NFC Bank", CategorieSelecteur.BANQUE),
    ("Commercial Bank of Cameroon", CategorieSelecteur.BANQUE),
    ("CBC", CategorieSelecteur.BANQUE),
    ("La Regionale Bank", CategorieSelecteur.BANQUE),
    ("Union Bank of Cameroon", CategorieSelecteur.BANQUE),
    ("UBC", CategorieSelecteur.BANQUE),
    ("Credit Foncier du Cameroun", CategorieSelecteur.BANQUE),
    ("CFC", CategorieSelecteur.BANQUE),

    # --- Microfinance (echantillon a valider/completer) ---
    ("Express Union", CategorieSelecteur.MICROFINANCE),
    ("CamCCUL", CategorieSelecteur.MICROFINANCE),

    # --- Telecoms ---
    ("MTN Cameroon", CategorieSelecteur.TELECOM),
    ("Orange Cameroun", CategorieSelecteur.TELECOM),
    ("Camtel", CategorieSelecteur.TELECOM),
    ("Nexttel", CategorieSelecteur.TELECOM),
    ("Cameroon Postal Services", CategorieSelecteur.TELECOM),
    ("CAMPOST", CategorieSelecteur.TELECOM),
    ("Blue SA", CategorieSelecteur.TELECOM),
    ("Viettel Cameroun", CategorieSelecteur.TELECOM),

    # --- Universites (echantillon a valider/completer) ---
    ("Universite de Yaounde I", CategorieSelecteur.UNIVERSITE),
    ("Universite de Douala", CategorieSelecteur.UNIVERSITE),
    ("Universite de Buea", CategorieSelecteur.UNIVERSITE),
    ("Universite de Dschang", CategorieSelecteur.UNIVERSITE),
    ("Universite de Maroua", CategorieSelecteur.UNIVERSITE),
    ("Universite de Ngaoundere", CategorieSelecteur.UNIVERSITE),
    ("Universite de Bamenda", CategorieSelecteur.UNIVERSITE),
    ("Universite de Bertoua", CategorieSelecteur.UNIVERSITE),
    ("Universite Catholique d'Afrique Centrale", CategorieSelecteur.UNIVERSITE),
    ("UCAC", CategorieSelecteur.UNIVERSITE),
    ("Institut des Relations Internationales du Cameroun", CategorieSelecteur.UNIVERSITE),
    ("IRIC", CategorieSelecteur.UNIVERSITE),
    ("Ecole Nationale d'Administration et de Magistrature", CategorieSelecteur.UNIVERSITE),
    ("ENAM", CategorieSelecteur.UNIVERSITE),
    ("Ecole Polytechnique de Yaounde", CategorieSelecteur.UNIVERSITE),

    # --- Entreprises (echantillon a valider/completer) ---
    ("SONARA", CategorieSelecteur.ENTREPRISE),
    ("ENEO Cameroun", CategorieSelecteur.ENTREPRISE),
    ("Camair-Co", CategorieSelecteur.ENTREPRISE),
    ("CNPS", CategorieSelecteur.ENTREPRISE),
    ("Camerounaise des Eaux", CategorieSelecteur.ENTREPRISE),
    ("CDE", CategorieSelecteur.ENTREPRISE),
    ("Societe Nationale des Hydrocarbures", CategorieSelecteur.ENTREPRISE),
    ("SNH", CategorieSelecteur.ENTREPRISE),
    ("Port Autonome de Douala", CategorieSelecteur.ENTREPRISE),
    ("PAD", CategorieSelecteur.ENTREPRISE),
    ("Port Autonome de Kribi", CategorieSelecteur.ENTREPRISE),
    ("PAK", CategorieSelecteur.ENTREPRISE),
    ("Camrail", CategorieSelecteur.ENTREPRISE),
    ("Douala International Terminal", CategorieSelecteur.ENTREPRISE),
    ("DIT", CategorieSelecteur.ENTREPRISE),
    ("AES Sonel", CategorieSelecteur.ENTREPRISE),
    ("Hydro Mekin", CategorieSelecteur.ENTREPRISE),
    ("Kribi Power Development Company", CategorieSelecteur.ENTREPRISE),
    ("KPDC", CategorieSelecteur.ENTREPRISE),

    # --- Villes et regions ---
    ("Yaounde", CategorieSelecteur.VILLE_REGION),
    ("Douala", CategorieSelecteur.VILLE_REGION),
    ("Bafoussam", CategorieSelecteur.VILLE_REGION),
    ("Garoua", CategorieSelecteur.VILLE_REGION),
    ("Bamenda", CategorieSelecteur.VILLE_REGION),
    ("Cameroon", CategorieSelecteur.VILLE_REGION),
    ("Cameroun", CategorieSelecteur.VILLE_REGION),
    ("Bafang", CategorieSelecteur.VILLE_REGION),
    ("Ebolowa", CategorieSelecteur.VILLE_REGION),
    ("Maroua", CategorieSelecteur.VILLE_REGION),
    ("Ngaoundere", CategorieSelecteur.VILLE_REGION),
    ("Bertoua", CategorieSelecteur.VILLE_REGION),
    ("Kribi", CategorieSelecteur.VILLE_REGION),
    ("Limbe", CategorieSelecteur.VILLE_REGION),
    ("Kumba", CategorieSelecteur.VILLE_REGION),
    ("Edea", CategorieSelecteur.VILLE_REGION),
    ("Nkongsamba", CategorieSelecteur.VILLE_REGION),
    ("Buea", CategorieSelecteur.VILLE_REGION),
    ("Dschang", CategorieSelecteur.VILLE_REGION),
    ("Foumban", CategorieSelecteur.VILLE_REGION),
    ("Adamaoua", CategorieSelecteur.VILLE_REGION),
    ("Centre", CategorieSelecteur.VILLE_REGION),
    ("Est", CategorieSelecteur.VILLE_REGION),
    ("Extreme-Nord", CategorieSelecteur.VILLE_REGION),
    ("Littoral", CategorieSelecteur.VILLE_REGION),
    ("Nord", CategorieSelecteur.VILLE_REGION),
    ("Nord-Ouest", CategorieSelecteur.VILLE_REGION),
    ("Ouest", CategorieSelecteur.VILLE_REGION),
    ("Sud", CategorieSelecteur.VILLE_REGION),
    ("Sud-Ouest", CategorieSelecteur.VILLE_REGION),
]


def seed():
    init_db()
    session = get_session()

    added_count = 0
    skipped_count = 0

    for valeur, categorie in SEED_SELECTEURS:
        existing = session.query(Selecteur).filter_by(valeur=valeur, categorie=categorie).first()
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
    logger.info(f"Seed termine : {added_count} selecteurs ajoutes, {skipped_count} deja presents.")
    session.close()


if __name__ == "__main__":
    seed()