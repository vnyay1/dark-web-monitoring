"""
FR-01 - Module centralise de connexion Tor.

Regroupe la configuration du proxy SOCKS, le renouvellement de circuit,
et une fonction utilitaire de requete HTTP via Tor - utilisee par tous
les connecteurs .onion, pour eviter la duplication de cette logique
dans chaque fichier de connecteur.
"""

import logging
import requests
from stem import Signal
from stem.control import Controller

from app.config import Config

logger = logging.getLogger(__name__)


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


def renew_tor_circuit():
    """Demande a Tor un nouveau circuit (nouvelle IP de sortie) - FR-01."""
    try:
        with Controller.from_port(port=TOR_CONTROL_PORT) as controller:
            controller.authenticate(password=TOR_CONTROL_PASSWORD)
            controller.signal(Signal.NEWNYM)
            logger.info("[tor] Nouveau circuit Tor demande.")
    except Exception as e:
        logger.error(f"[tor] Impossible de renouveler le circuit Tor : {e}")


def get_via_tor(url: str, timeout: int = 30, max_retries: int = 3,
                 retry_delay_seconds: int = 5, headers: dict = None) -> requests.Response:
    """
    Effectue une requete GET via le proxy SOCKS Tor, avec renouvellement
    automatique du circuit en cas d'echec (FR-01), reutilisable par tous
    les connecteurs .onion (FR-02).

    Leve la derniere exception rencontree si toutes les tentatives echouent,
    afin que l'appelant (BaseConnector.collect()) puisse la capturer et la
    journaliser normalement (FR-17), comme pour toute autre erreur de fetch().
    """
    import time

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