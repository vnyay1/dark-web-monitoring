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
from datetime import datetime, timezone

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


def parser_date(valeur, formats=(), source: str = "?") -> datetime:
    """
    Convertit la date brute d'une entree en datetime naif UTC.

    valeur  : chaine issue du site (ou deja un datetime, laisse tel quel).
    formats : formats strptime propres a la source, essayes en premier.
    source  : nom du connecteur, pour un log exploitable.

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
        ("structure inconnue !!", ()),
        (None, ()),
    ]

    print("=" * 64)
    print("PARSEUR DE DATES - verification manuelle")
    print("=" * 64)
    for brut, formats in exemples:
        resultat = parser_date(brut, formats, source="demo")
        print(f"  {str(brut)[:32]:34} -> {resultat}")
