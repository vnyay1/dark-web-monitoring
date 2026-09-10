"""
FR-01 - Module centralise de connexion Tor.

Regroupe la configuration du proxy SOCKS, le renouvellement de circuit,
et une fonction utilitaire de requete HTTP via Tor - utilisee par tous
les connecteurs .onion.

Renouvellement PROACTIF a intervalle ALEATOIRE (entre 10 et 120s, tire
a chaque cycle) pendant une session de collecte prolongee, en plus du
renouvellement reactif en cas d'echec.

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
import requests
import random
from stem import Signal
from stem.control import Controller
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TOR_SOCKS_PROXY = os.getenv("TOR_SOCKS_PROXY")
TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT"))
TOR_CONTROL_PASSWORD = os.getenv("TOR_CONTROL_PASSWORD")

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

_dernier_renouvellement = None
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


def renew_tor_circuit():
    """
    Demande a Tor un nouveau circuit (nouvelle IP de sortie) - FR-01.

    Protege par un verrou pour eviter les collisions entre appels
    rapproches. Journalise l'IP de sortie apres renouvellement pour
    permettre de verifier que le circuit change reellement.
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

            ip_sortie = _obtenir_ip_sortie_actuelle()
            if ip_sortie == "inconnue":
                # Le circuit a bien ete renouvele ; c'est seulement sa
                # verification qui n'a pas abouti (check.torproject.org lent
                # ou injoignable sur ce circuit). Rien n'est "confirme".
                logger.warning("[tor] Circuit renouvele, IP de sortie non verifiee.")
            else:
                logger.info(f"[tor] Nouvelle IP de sortie confirmee : {ip_sortie}")
        except Exception as e:
            logger.error(f"[tor] Impossible de renouveler le circuit Tor : {e}")
        finally:
            stem_logger.setLevel(niveau_original)


def _renouvellement_proactif_si_necessaire():
    """
    Verifie si le delai de renouvellement proactif est ecoule et, le cas
    echeant, force un nouveau circuit AVANT meme qu'un echec ne survienne.
    Le seuil est retire aleatoirement (10-120s) a chaque appel.
    """
    global _dernier_renouvellement

    maintenant = time.time()

    if _dernier_renouvellement is None:
        _dernier_renouvellement = maintenant
        return

    interval_renouvellement_proactif = random.randint(INTERVALLE_MINIMUM_ENTRE_RENOUVELLEMENTS, 120)
    if maintenant - _dernier_renouvellement >= interval_renouvellement_proactif:
        logger.info(
            f"[tor] Renouvellement proactif du circuit "
            f"(intervalle de {interval_renouvellement_proactif}s atteint)."
        )
        renew_tor_circuit()


def get_via_tor(url: str, timeout: int = 30, max_retries: int = 3,
                 retry_delay_seconds: int = 5, headers: dict = None) -> requests.Response:
    """
    Effectue une requete GET via le proxy SOCKS Tor, avec :
    - renouvellement REACTIF du circuit en cas d'echec (FR-01)
    - renouvellement PROACTIF du circuit periodiquement, meme sans echec
    """
    _renouvellement_proactif_si_necessaire()

    proxies = {
        "http": TOR_SOCKS_PROXY,
        "https": TOR_SOCKS_PROXY,
    }
    request_headers = headers or DEFAULT_HEADERS

    derniere_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, proxies=proxies, headers=request_headers, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            derniere_exception = e
            logger.warning(f"[tor] Tentative {attempt}/{max_retries} echouee pour {url} : {e}")
            if attempt < max_retries:
                renew_tor_circuit()
                time.sleep(retry_delay_seconds)

    raise derniere_exception