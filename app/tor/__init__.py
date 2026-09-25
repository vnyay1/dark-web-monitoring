"""
FR-01 - Module centralise de connexion Tor.

Regroupe la configuration du proxy SOCKS, le renouvellement de circuit,
et la requete HTTP via Tor (get_via_tor) - seul chemin reseau des
connecteurs .onion, qui l'appellent par BaseConnector.requete.

Renouvellement PROACTIF a intervalle ALEATOIRE (entre 10 et 120s, tire
apres chaque renouvellement) pendant une session de collecte prolongee, en
plus du renouvellement REACTIF entre deux tentatives d'une requete, que
BaseConnector.requete demande par renew_tor_circuit().

COLLECTE PARALLELE - plusieurs sources passent par ce module en meme temps,
depuis des fils differents. L'etat du renouvellement est donc protege par
un verrou, et l'echeance proactive est tiree UNE fois par renouvellement :
la tirer a chaque requete, comme avant, multipliait les occasions de
renouveler par le nombre de sources en parallele. Chaque NEWNYM force la
reconstruction des circuits vers les services .onion : la cadence reste
celle de la collecte sequentielle, quel que soit le nombre de sources.

Chaque renouvellement journalise l'IP de sortie effective (via
check.torproject.org), permettant de verifier que le circuit change
reellement. La derniere IP constatee est aussi MEMORISEE en memoire du
processus : le scheduler la lit periodiquement et la publie pour la console
de supervision (app.supervision). Ce module reste volontairement sans acces
a la base.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
import random
from stem import Signal
from stem.control import Controller

from app.config import Config

logger = logging.getLogger(__name__)


class ReponseTropVolumineuse(Exception):
    """
    Corps de reponse depassant TAILLE_MAX_REPONSE.

    Traitee comme un echec de collecte ordinaire par le pipeline : elle est
    journalisee dans JournalAudit par le connecteur, sans entree dediee dans
    le flux d'evenements de la console de supervision.
    """


# Delai maximal d'attente d'une reponse, en secondes.
DELAI_REPONSE_SECONDES = 30

# 10 Mo : trois ordres de grandeur au-dessus d'une page de listing de site de
# fuite (quelques dizaines de Ko), donc aucune collecte legitime n'est
# tronquee, et le processus ne peut plus etre sature par une reponse geante.
TAILLE_MAX_REPONSE = 10 * 1024 * 1024

# Lus une seule fois, par app.config (.env), comme le reste de la
# configuration.
TOR_SOCKS_PROXY = Config.TOR_SOCKS_PROXY
TOR_CONTROL_PORT = Config.TOR_CONTROL_PORT
TOR_CONTROL_PASSWORD = Config.TOR_CONTROL_PASSWORD

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Duree minimale (secondes) entre deux renouvellements, proactifs OU
# reactifs confondus - garde-fou anti-rafale/anti-collision.
INTERVALLE_MINIMUM_ENTRE_RENOUVELLEMENTS = 10

# Borne haute de l'intervalle aleatoire du renouvellement proactif.
INTERVALLE_MAXIMUM_PROACTIF = 120

_dernier_renouvellement = None
# Echeance du prochain renouvellement proactif (time.time()), tiree au
# hasard apres chaque renouvellement.
_prochain_renouvellement = None
_verrou_renouvellement = threading.Lock()

# Derniere IP de sortie reellement constatee, et quand. Une verification
# echouee ne l'ecrase pas : on garde la derniere valeur SURE, dont l'age
# croissant signale lui-meme que les verifications n'aboutissent plus.
_derniere_ip_sortie = None
_derniere_ip_constatee_le = None
_verrou_ip = threading.Lock()


def _obtenir_ip_sortie_actuelle() -> str:
    """
    Interroge check.torproject.org pour connaitre l'IP de sortie
    actuellement utilisee par le circuit Tor. Utilise uniquement a des
    fins de verification/logging.
    """
    try:
        proxies = {"http": TOR_SOCKS_PROXY, "https": TOR_SOCKS_PROXY}
        response = requests.get(
            "https://check.torproject.org/api/ip",
            proxies=proxies,
            timeout=15,
        )
        data = response.json()
        ip = data.get("IP")
        if ip:
            _memoriser_ip(ip)
        return ip or "inconnue"
    except Exception as e:
        logger.warning(f"[tor] Impossible de recuperer l'IP de sortie actuelle : {e}")
        return "inconnue"


def _memoriser_ip(ip: str):
    global _derniere_ip_sortie, _derniere_ip_constatee_le

    with _verrou_ip:
        _derniere_ip_sortie = ip
        # UTC naif, comme partout dans le projet (cf. app.models.utc_now).
        _derniere_ip_constatee_le = datetime.now(timezone.utc).replace(tzinfo=None)


def verifier_ip_sortie() -> str:
    """
    Verifie a la demande l'IP de sortie du circuit courant.

    La requete part vers check.torproject.org, jamais vers une source
    surveillee : elle ne compte pas dans la collecte (CN-09/CN-10).
    Retourne l'IP, ou None si la verification a echoue.
    """
    ip = _obtenir_ip_sortie_actuelle()
    return None if ip == "inconnue" else ip


def derniere_ip_sortie() -> tuple:
    """(ip, constatee_le) de la derniere verification reussie, ou (None, None)."""
    with _verrou_ip:
        return _derniere_ip_sortie, _derniere_ip_constatee_le


def _planifier_prochain_renouvellement(depuis: float):
    """Tire l'echeance du prochain renouvellement proactif. Sous le verrou."""
    global _prochain_renouvellement
    _prochain_renouvellement = depuis + random.randint(
        INTERVALLE_MINIMUM_ENTRE_RENOUVELLEMENTS, INTERVALLE_MAXIMUM_PROACTIF
    )


def renew_tor_circuit():
    """
    Demande a Tor un nouveau circuit (nouvelle IP de sortie) - FR-01.

    Protege par un verrou pour eviter les collisions entre appels
    rapproches, y compris depuis plusieurs fils de collecte. Journalise
    l'IP de sortie apres renouvellement pour permettre de verifier que le
    circuit change reellement.
    """
    global _dernier_renouvellement

    with _verrou_renouvellement:
        maintenant = time.time()

        if (_dernier_renouvellement is not None
                and maintenant - _dernier_renouvellement < INTERVALLE_MINIMUM_ENTRE_RENOUVELLEMENTS):
            logger.debug("[tor] Renouvellement ignore (trop rapproche du precedent).")
            return

        stem_logger = logging.getLogger("stem")
        niveau_original = stem_logger.level
        stem_logger.setLevel(logging.CRITICAL)

        try:
            with Controller.from_port(port=TOR_CONTROL_PORT) as controller:
                controller.authenticate(password=TOR_CONTROL_PASSWORD)
                controller.signal(Signal.NEWNYM)
                _dernier_renouvellement = time.time()
                logger.info("[tor] Nouveau circuit Tor demande.")
        except Exception as e:
            logger.error(f"[tor] Impossible de renouveler le circuit Tor : {e}")
            # Echeance reportee malgre l'echec : sinon chaque requete de
            # chaque fil retenterait aussitot le port de controle.
            _planifier_prochain_renouvellement(time.time())
            return
        finally:
            stem_logger.setLevel(niveau_original)

        _planifier_prochain_renouvellement(_dernier_renouvellement)

    # Verification HORS verrou : jusqu'a 15 s vers check.torproject.org,
    # pendant lesquelles les autres fils de collecte doivent pouvoir
    # continuer leurs requetes.
    ip_sortie = _obtenir_ip_sortie_actuelle()
    if ip_sortie == "inconnue":
        # Le circuit a bien ete renouvele ; c'est seulement sa
        # verification qui n'a pas abouti (check.torproject.org lent
        # ou injoignable sur ce circuit). Rien n'est "confirme".
        logger.warning("[tor] Circuit renouvele, IP de sortie non verifiee.")
    else:
        logger.info(f"[tor] Nouvelle IP de sortie confirmee : {ip_sortie}")


def _renouvellement_proactif_si_necessaire():
    """
    Force un nouveau circuit, AVANT meme qu'un echec ne survienne, quand
    l'echeance proactive est atteinte. L'echeance est tiree au hasard
    (10-120 s) apres chaque renouvellement, pas a chaque appel : avec
    plusieurs sources en parallele, les appels sont plus frequents, la
    cadence des renouvellements ne doit pas l'etre.
    """
    global _dernier_renouvellement

    with _verrou_renouvellement:
        maintenant = time.time()

        if _prochain_renouvellement is None:
            # Premier appel du processus : l'horloge demarre, le circuit
            # courant est neuf pour cette session.
            if _dernier_renouvellement is None:
                _dernier_renouvellement = maintenant
            _planifier_prochain_renouvellement(_dernier_renouvellement)
            return

        if maintenant < _prochain_renouvellement:
            return

        intervalle = int(_prochain_renouvellement - (_dernier_renouvellement or maintenant))

    logger.info(
        f"[tor] Renouvellement proactif du circuit "
        f"(intervalle de {intervalle}s atteint)."
    )
    renew_tor_circuit()


def _lire_avec_limite(response: requests.Response) -> requests.Response:
    """
    Lit le corps de la reponse par blocs, en s'arretant net au-dela de
    TAILLE_MAX_REPONSE.

    Les serveurs interroges sont operes par des acteurs malveillants : rien
    ne les empeche de repondre un corps de plusieurs Go, que `response.text`
    chargerait integralement en memoire. Le connecteur consomme ensuite
    `.text` (base_connector.fetch), donc on renseigne `_content` nous-memes
    plutot que de renvoyer un flux : l'appelant garde une Response normale.
    """
    annonce = response.headers.get("Content-Length")
    if annonce and annonce.isdigit() and int(annonce) > TAILLE_MAX_REPONSE:
        response.close()
        raise ReponseTropVolumineuse(
            f"Content-Length annonce ({annonce} octets) au-dela de la limite "
            f"de {TAILLE_MAX_REPONSE} octets."
        )

    morceaux = []
    total = 0
    for morceau in response.iter_content(chunk_size=65536):
        total += len(morceau)
        if total > TAILLE_MAX_REPONSE:
            response.close()
            raise ReponseTropVolumineuse(
                f"Corps de reponse au-dela de la limite de "
                f"{TAILLE_MAX_REPONSE} octets."
            )
        morceaux.append(morceau)

    # _content / _content_consumed : ce que requests renseigne lui-meme quand
    # il lit une reponse non streamee. `.text` decode ensuite normalement.
    response._content = b"".join(morceaux)
    response._content_consumed = True
    return response


def get_via_tor(url: str) -> requests.Response:
    """
    Effectue UNE requete GET via le proxy SOCKS Tor, avec :
    - renouvellement PROACTIF du circuit periodiquement, meme sans echec
    - corps de reponse BORNE a TAILLE_MAX_REPONSE (voir _lire_avec_limite)

    Une seule tentative, deliberement : les reessais - et le renouvellement
    reactif du circuit entre deux essais - sont faits par
    BaseConnector.requete, qui soumet chacun au delai FR-06. La boucle de
    reessai qui vivait ici repartait a 5 s d'intervalle, hors de tout rate
    limiting.
    """
    _renouvellement_proactif_si_necessaire()

    proxies = {
        "http": TOR_SOCKS_PROXY,
        "https": TOR_SOCKS_PROXY,
    }

    # CN-03 : l'URL complete d'un site de fuite ne doit jamais atterrir dans
    # un journal. base_connector fait deja cet effort de son cote ; le faire
    # ici aussi evite que le domaine .onion ressorte par la porte de derriere
    # a chaque echec reseau.
    chemin = urlparse(url).path or "/"

    try:
        response = requests.get(
            url,
            proxies=proxies,
            headers=DEFAULT_HEADERS,
            timeout=DELAI_REPONSE_SECONDES,
            stream=True,
        )
        response.raise_for_status()
        return _lire_avec_limite(response)
    except ReponseTropVolumineuse as e:
        logger.warning(f"[tor] Reponse rejetee pour {chemin} : {e}")
        raise
    except requests.exceptions.RequestException as e:
        logger.warning(f"[tor] Requete echouee pour {chemin} : {e}")
        raise