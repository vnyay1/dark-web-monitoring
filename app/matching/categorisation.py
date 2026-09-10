"""
FR-13 - Categorisation automatique de la fuite detectee.

Approche par mots-cles indicateurs : chaque categorie possede une liste de
termes frequemment associes a ce type de fuite dans les annonces de leak
sites / forums. La categorie la mieux representee dans le texte est retenue ;
sans aucun indice, "NON_PRECISEE" (FR-13 : "Categorie non precisee").

POURQUOI CETTE VERSION - la precedente categorisait mal pour quatre raisons :

  1. mots-cles uniquement ANGLAIS, alors que les annonces visant des entites
     camerounaises sont souvent en francais ou mixtes ;
  2. correspondance par SOUS-CHAINE ("mot in texte") : "auth" trouvait
     "author", "contract" trouvait "contractor" ;
  3. aucune normalisation des ACCENTS : "données" ne pouvait pas rencontrer
     "donnees", ni "hôpital" "hopital" ;
  4. EGALITES tranchees par l'ordre du dictionnaire : la premiere categorie
     (identifiants) gagnait systematiquement.

Ce module ne fait QUE de la categorisation textuelle indicative - il ne
remplace pas la validation finale par un analyste (FR-21, changement de
statut manuel).

LIMITE CONNUE - une source lue en listing seul n'offre souvent qu'un nom et
une phrase : peu de matiere pour categoriser. C'est la lecture des pages de
detail (cf. BaseConnector.SUPPORTE_DETAIL) qui ameliore reellement le
resultat, plus que l'enrichissement de ces listes.
"""

import logging
import re
import unicodedata

from app.models import CategorieFuite

logger = logging.getLogger(__name__)


# Mots-cles par categorie. Francais ET anglais : le contenu collecte peut
# etre dans l'une ou l'autre langue, ou les deux. Ecrits au singulier et avec
# leurs accents - la normalisation s'occupe du reste (cf. _motif).
#
# Termes volontairement ECARTES car trop ambigus pour indiquer une categorie
# a eux seuls : "acces", "adresse" (adresse IP, e-mail...), "api",
# "diagnostic" (vocabulaire informatique), "pv", "email", "hash".
MOTS_CLES_PAR_CATEGORIE = {
    CategorieFuite.CREDENTIALS: [
        # francais
        "identifiant", "identifiant de connexion", "mot de passe",
        "nom d'utilisateur", "compte utilisateur", "authentification",
        "jeton d'accès", "clé api", "accès vpn", "accès administrateur",
        # anglais
        "credential", "login", "password", "username", "combo list",
        "combolist", "authentication", "access token", "api key",
        "session token", "password hash",
    ],
    CategorieFuite.DONNEES_PERSONNELLES: [
        "donnée personnelle", "information personnelle",
        "donnée à caractère personnel", "nom complet", "date de naissance",
        "lieu de naissance", "carte nationale d'identité", "cni",
        "numéro de téléphone", "adresse postale", "passeport",
        "donnée client", "fichier client", "base client", "état civil",
        "personal data", "personally identifiable", "pii", "full name",
        "date of birth", "national id", "id card", "passport",
        "customer data", "user record", "citizens data", "phone number",
        "home address",
    ],
    CategorieFuite.DONNEES_FINANCIERES: [
        "donnée financière", "compte bancaire", "relevé bancaire",
        "relevé de compte", "carte bancaire", "carte de crédit",
        "numéro de carte", "rib", "iban", "virement", "transaction",
        "facture", "paiement", "comptabilité", "bilan comptable",
        "fiche de paie", "bulletin de paie", "salaire", "mobile money",
        "orange money",
        "financial data", "bank account", "bank statement", "credit card",
        "card number", "swift", "payment data", "invoice",
        "financial record", "banking", "payroll", "accounting",
    ],
    CategorieFuite.DONNEES_SANTE: [
        "dossier médical", "donnée de santé", "donnée médicale", "patient",
        "hôpital", "clinique", "ordonnance", "diagnostic médical",
        "analyse médicale", "antécédent médical",
        "medical record", "health data", "patient data", "healthcare",
        "hospital", "medical history", "clinical data",
    ],
    CategorieFuite.DOCUMENTS_INTERNES: [
        "document interne", "document confidentiel", "confidentiel",
        "note interne", "mémo interne", "contrat", "rapport interne",
        "fichier interne", "procès-verbal", "correspondance",
        "internal document", "confidential", "internal memo", "contract",
        "internal report", "internal file", "proprietary document",
        "internal communication", "nda",
    ],
    CategorieFuite.CODE_SOURCE: [
        "code source", "dépôt git", "base de code",
        "source code", "repository", "codebase", "github", "gitlab",
        "bitbucket", "proprietary code", "software code",
    ],
}

# Departage des egalites : la categorie la plus SENSIBLE l'emporte. En cas de
# doute, surestimer la gravite d'une fuite coute moins que la sous-estimer.
PRIORITE_EN_CAS_D_EGALITE = (
    CategorieFuite.DONNEES_SANTE,
    CategorieFuite.DONNEES_FINANCIERES,
    CategorieFuite.DONNEES_PERSONNELLES,
    CategorieFuite.CREDENTIALS,
    CategorieFuite.CODE_SOURCE,
    CategorieFuite.DOCUMENTS_INTERNES,
)

# Une expression de plusieurs mots ("carte bancaire") est un indice plus sur
# qu'un mot isole ("facture") : elle compte double.
POIDS_EXPRESSION = 2
POIDS_MOT = 1

# Les mots tres courts (articles, prepositions, sigles) ne prennent pas la
# marque du pluriel : "de" ne doit pas devenir "des".
LONGUEUR_MIN_PLURIEL = 4


def normaliser(texte: str) -> str:
    """
    Forme canonique partagee par le texte et les mots-cles : minuscules,
    accents retires, et tout ce qui n'est ni lettre ni chiffre ramene a un
    espace (apostrophes, tirets, ponctuation).

        "Carte Nationale d'Identité" -> "carte nationale d identite"
    """
    sans_accents = unicodedata.normalize("NFKD", texte or "")
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def _motif_mot(mot: str) -> str:
    """Un mot, avec son pluriel regulier : -s/-x, et -al -> -aux."""
    if len(mot) < LONGUEUR_MIN_PLURIEL:
        return re.escape(mot)
    if mot.endswith("al"):
        return re.escape(mot[:-2]) + "(?:al|aux)"      # medical -> medicaux
    if mot.endswith(("s", "x", "z")):
        return re.escape(mot)
    return re.escape(mot) + "[sx]?"


def _motif(mot_cle: str):
    """
    Expression reguliere d'un mot-cle, en mots ENTIERS : les frontieres
    empechent "auth" de trouver "author". Le texte etant normalise, un simple
    espace separe les mots d'une expression.
    """
    mots = normaliser(mot_cle).split()
    corps = r"\s".join(_motif_mot(m) for m in mots)
    return re.compile(rf"(?<![a-z0-9]){corps}(?![a-z0-9])")


# Compilation unique au chargement du module.
_REGLES = {
    categorie: [
        (_motif(mot_cle), POIDS_EXPRESSION if " " in normaliser(mot_cle) else POIDS_MOT, mot_cle)
        for mot_cle in dict.fromkeys(mots_cles)   # dedoublonnage, ordre conserve
    ]
    for categorie, mots_cles in MOTS_CLES_PAR_CATEGORIE.items()
}


def categoriser_texte(texte: str) -> tuple:
    """
    Determine la categorie de fuite la plus probable a partir du texte.

    Retourne un tuple (categorie, details) ou details associe a chaque
    categorie reperee son score, utile pour la tracabilite/debug. Chaque
    mot-cle compte une fois, quel que soit son nombre d'occurrences : une
    annonce qui repete "password" dix fois n'est pas dix fois plus une fuite
    d'identifiants.
    """
    texte_normalise = normaliser(texte)
    scores = {}

    for categorie, regles in _REGLES.items():
        score = sum(poids for motif, poids, _ in regles if motif.search(texte_normalise))
        if score:
            scores[categorie] = score

    if not scores:
        return CategorieFuite.NON_PRECISEE, {}

    meilleur = max(scores.values())
    ex_aequo = [c for c in PRIORITE_EN_CAS_D_EGALITE if scores.get(c) == meilleur]
    categorie_retenue = ex_aequo[0]

    details = {c.value: n for c, n in scores.items()}
    logger.info(f"[FR-13] Categorisation : {categorie_retenue.value} (scores : {details})")

    return categorie_retenue, details


if __name__ == "__main__":
    exemples = [
        ("Fuite de la base clients : noms complets, dates de naissance et numéros de téléphone",
         CategorieFuite.DONNEES_PERSONNELLES),
        ("Relevés bancaires et fiches de paie des employés, cartes bancaires",
         CategorieFuite.DONNEES_FINANCIERES),
        ("Dossiers médicaux des patients de l'hôpital",
         CategorieFuite.DONNEES_SANTE),
        ("Identifiants de connexion et mots de passe du portail",
         CategorieFuite.CREDENTIALS),
        ("Leaked source code from the internal GitLab repository",
         CategorieFuite.CODE_SOURCE),
        ("Documents internes et procès-verbaux confidentiels de la direction",
         CategorieFuite.DOCUMENTS_INTERNES),
        ("Customer data dump: full names, passport numbers, bank account details",
         CategorieFuite.DONNEES_PERSONNELLES),
        ("Données clients + credit card numbers leaked",
         CategorieFuite.DONNEES_FINANCIERES),
        # Faux amis de l'ancienne version (sous-chaines)
        ("Article by the author about a new contractor",
         CategorieFuite.NON_PRECISEE),
        ("Annonce de rançongiciel, aucune précision sur les données",
         CategorieFuite.NON_PRECISEE),
    ]

    print("=" * 76)
    print("CATEGORISATION - verification sur exemples FR / EN / mixtes")
    print("=" * 76)
    echecs = 0
    for texte, attendue in exemples:
        obtenue, scores = categoriser_texte(texte)
        ok = obtenue == attendue
        echecs += not ok
        print(f"{'OK ' if ok else 'KO '} {obtenue.value:22} {texte[:46]!r}")
        if not ok:
            print(f"     attendu {attendue.value}, scores {scores}")
    print("-" * 76)
    print("Tous les exemples passent." if not echecs else f"{echecs} echec(s).")
