"""
Normalisation des dates de publication annoncees par les sources.

POURQUOI CE MODULE - chaque source date ses annonces a sa facon
("Aug 13, 2026", "2026-08-13", "13/08/2026"...), sous des cles differentes
selon le connecteur, et le pipeline ne les lisait tout simplement pas. Pour
ne parcourir que les entrees publiees sur la periode reglee par
l'administrateur (FR-03), il faut d'abord ramener tout cela a un datetime.

PRINCIPE DE PRUDENCE - une date illisible retourne None, jamais une date
inventee ni la date du jour. Une entree sans date exploitable est ANALYSEE
quand meme (cf. pipeline) : mieux vaut examiner une annonce trop ancienne
que rater une exposition camerounaise parce qu'un site a change son format
d'affichage. Chaque echec est journalise en WARNING avec la chaine brute,
pour qu'un format manquant se voie au lieu de disparaitre en silence.

Les datetime produits sont NAIFS et en UTC, comme partout ailleurs dans le
projet (cf. app.models.utc_now).
"""

import logging
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# Cles sous lesquelles les connecteurs exposent la date d'une entree, par
# ordre de preference : chaque site la nomme a sa facon.
CLES_DATE = ("date_publication", "discovery_date", "date")

# Formats essayes pour toute source, apres ses formats specifiques.
# Ordonnes du plus explicite au plus ambigu.
FORMATS_COMMUNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %B %Y",        # 13 August 2026
    "%d %b %Y",        # 13 Aug 2026
    "%B %d, %Y",       # August 13, 2026
    "%b %d, %Y",       # Aug 13, 2026
    "%d-%m-%Y",
    "%d/%m/%Y",        # jour/mois : convention majoritaire hors Etats-Unis
    "%m/%d/%Y",
)

# Etiquettes que les sources collent devant la date ("Publicated at ...",
# "DISCOVERY DATE: ..."). Retirees avant analyse.
PREFIXES_A_RETIRER = re.compile(
    r"^\s*(publicated\s+at|published\s+at|published|publie\s+le|discovery\s+date|date"
    r"|added|posted\s+on|posted|leaked\s+on|updated)\s*[:\-]?\s*",
    re.IGNORECASE,
)

# Suffixes de fuseau qu'aucun format strptime de la liste ne consomme.
SUFFIXE_UTC = re.compile(r"\s*(utc|gmt|z)\s*$", re.IGNORECASE)


# Formats SANS annee, tels qu'affiches par les sites pour les publications
# recentes ("Sep 1" chez everest). L'annee est deduite (cf. _sans_annee).
FORMATS_SANS_ANNEE = ("%b %d", "%B %d", "%d %b", "%d %B")

# Anciennete relative : "2d" (everest), "5h", "3 days ago", "il y a 2 jours".
# m = minutes (usage des sites), mo = mois.
ANCIENNETE_RELATIVE = re.compile(
    r"^(?:il y a\s+)?(\d+)\s*"
    r"(s|sec|secs?|seconds?|secondes?"
    r"|m|min|mins?|minutes?"
    r"|h|hr|hrs?|hours?|heures?"
    r"|d|j|days?|jours?"
    r"|w|wk|weeks?|sem|semaines?"
    r"|mo|months?|mois"
    r"|y|yr|years?|ans?)"
    r"(?:\s+ago)?$",
    re.IGNORECASE,
)

UNITES = (
    (("s", "sec", "secs", "second", "seconds", "seconde", "secondes"), timedelta(seconds=1)),
    (("m", "min", "mins", "minute", "minutes"), timedelta(minutes=1)),
    (("h", "hr", "hrs", "hour", "hours", "heure", "heures"), timedelta(hours=1)),
    (("d", "j", "day", "days", "jour", "jours"), timedelta(days=1)),
    (("w", "wk", "week", "weeks", "sem", "semaine", "semaines"), timedelta(weeks=1)),
    (("mo", "month", "months", "mois"), timedelta(days=30)),
    (("y", "yr", "year", "years", "an", "ans"), timedelta(days=365)),
)

MOTS_RELATIFS = {
    "now": 0, "just now": 0, "a l'instant": 0, "à l'instant": 0,
    "today": 0, "aujourd'hui": 0, "aujourd hui": 0,
    "yesterday": 1, "hier": 1,
}


def _maintenant() -> datetime:
    """UTC naif a la seconde, comme partout dans le projet (cf. app.models.utc_now)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _relative(texte: str, reference: datetime):
    """
    "2d" -> il y a 2 jours, par rapport au moment de la collecte. La precision
    est celle de l'affichage du site : suffisante pour la fenetre de collecte
    (en jours), pas davantage.
    """
    if texte.lower() in MOTS_RELATIFS:
        return reference - timedelta(days=MOTS_RELATIFS[texte.lower()])

    correspondance = ANCIENNETE_RELATIVE.match(texte)
    if not correspondance:
        return None

    quantite, unite = int(correspondance.group(1)), correspondance.group(2).lower()
    for variantes, duree in UNITES:
        if unite in variantes:
            return reference - quantite * duree
    return None


def _sans_annee(texte: str, reference: datetime):
    """
    "Sep 1" -> le 1er septembre le plus RECENT qui ne soit pas dans le futur.
    Un site n'annonce pas une publication a venir : une date qui tomberait
    apres la collecte appartient forcement a l'annee precedente (un "Dec 28"
    lu le 3 janvier date de fin decembre dernier).
    """
    for motif in FORMATS_SANS_ANNEE:
        try:
            # L'annee est ajoutee AVANT l'analyse : sans elle, strptime
            # prendrait 1900, qui n'est pas bissextile, et refuserait "Feb 29".
            moment = datetime.strptime(f"{texte} {reference.year}", f"{motif} %Y")
        except ValueError:
            continue
        if moment > reference + timedelta(days=1):
            moment = moment.replace(year=moment.year - 1)
        return moment
    return None


def _nettoyer(valeur: str) -> str:
    texte = valeur.strip()
    texte = PREFIXES_A_RETIRER.sub("", texte)
    texte = SUFFIXE_UTC.sub("", texte)
    # Les ordinaux anglais ("13th August") ne sont pas geres par strptime.
    texte = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", texte, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", texte).strip(" ,;")


def _en_naif_utc(moment: datetime) -> datetime:
    """Ramene un datetime eventuellement aware en naif UTC (cf. utc_now)."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def parser_date(valeur, formats=(), source: str = "?", journaliser: bool = True) -> datetime:
    """
    Convertit la date brute d'une entree en datetime naif UTC.

    valeur  : chaine issue du site (ou deja un datetime, laisse tel quel).
    formats : formats strptime propres a la source, essayes en premier.
    source  : nom du connecteur, pour un log exploitable.
    journaliser : False pour une lecture de controle (arret de pagination),
                  afin que la meme date illisible ne soit pas signalee deux
                  fois - le pipeline la signale deja en l'analysant.

    Retourne None si la valeur est vide ou non interpretable.
    """
    if valeur is None:
        return None

    if isinstance(valeur, datetime):
        return _en_naif_utc(valeur)

    # Certaines sources exposent un epoch (JSON), en secondes ou millisecondes.
    if isinstance(valeur, (int, float)):
        secondes = valeur / 1000 if valeur > 1e11 else valeur
        try:
            return datetime.fromtimestamp(secondes, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            logger.warning(f"[dates:{source}] Horodatage numerique hors limites : {valeur!r}")
            return None

    texte = _nettoyer(str(valeur))
    if not texte:
        return None

    for motif in tuple(formats) + FORMATS_COMMUNS:
        try:
            return datetime.strptime(texte, motif)
        except ValueError:
            continue

    # Repli ISO 8601 (gere "2026-08-13T14:22:00+01:00").
    try:
        return _en_naif_utc(datetime.fromisoformat(texte.replace("Z", "+00:00")))
    except ValueError:
        pass

    # Formes que les sites reservent aux publications recentes.
    reference = _maintenant()
    for interpretation in (_relative, _sans_annee):
        moment = interpretation(texte, reference)
        if moment is not None:
            return moment

    if journaliser:
        logger.warning(
            f"[dates:{source}] Date non reconnue : {str(valeur)[:80]!r} "
            f"(nettoyee : {texte[:80]!r}). Entree traitee sans date."
        )
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    exemples = [
        ("Aug 13, 2026", ()),
        ("Publicated at 2026-08-13", ()),
        ("DISCOVERY DATE: 13/08/2026", ()),
        ("2026-08-13T14:22:00Z", ()),
        ("13th August 2026", ()),
        ("August 13, 2026 UTC", ()),
        (1755093720, ()),
        ("2d", ()),                 # everest : anciennete relative
        ("5h", ()),
        ("3 days ago", ()),
        ("il y a 2 jours", ()),
        ("Sep 1", ()),              # everest : sans annee
        ("Dec 28", ()),             # sans annee, forcement l'annee derniere si futur
        ("structure inconnue !!", ()),
        (None, ()),
    ]

    print("=" * 64)
    print("PARSEUR DE DATES - verification manuelle")
    print("=" * 64)
    for brut, formats in exemples:
        resultat = parser_date(brut, formats, source="demo")
        print(f"  {str(brut)[:32]:34} -> {resultat}")
