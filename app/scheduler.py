"""
FR-07 - Planification automatique de la collecte.

Execute le pipeline complet (7 connecteurs) toutes les 6 heures, sans
intervention humaine, conformement a FR-07 (Should).

Ce script est concu pour tourner comme un PROCESSUS INDEPENDANT du
serveur Flask (run.py) - ne pas l'importer dans l'application web, pour
eviter les doublons de planification en cas de rechargement automatique
du serveur en mode developpement.

Usage : python3 -m app.scheduler
Le processus reste actif en avant-plan (ou a lancer via tmux/screen/
systemd pour une execution persistante dans la VM).
"""

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.pipeline import executer_tous_les_connecteurs
from app.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# FR-07 : frequence par defaut = toutes les 6 heures
INTERVALLE_HEURES = 6


def job_collecte():
    """Tache executee a chaque declenchement du scheduler."""
    logger.info("=" * 60)
    logger.info("[scheduler] Debut de la collecte planifiee")
    logger.info("=" * 60)

    try:
        resultats = executer_tous_les_connecteurs()

        total_expositions = sum(r["nb_expositions_creees_ou_maj"] for r in resultats)
        total_echecs = sum(1 for r in resultats if not r["collecte_reussie"])

        logger.info(
            f"[scheduler] Collecte planifiee terminee : "
            f"{total_expositions} exposition(s) traitee(s), "
            f"{total_echecs} source(s) en echec sur {len(resultats)}"
        )
    except Exception as e:
        # Une erreur dans une collecte ne doit JAMAIS arreter le scheduler -
        # sinon toutes les collectes futures seraient perdues silencieusement
        logger.error(f"[scheduler] Erreur inattendue durant la collecte planifiee : {e}")


def _handle_shutdown(signum, frame):
    logger.info("[scheduler] Signal d'arret recu, arret propre du scheduler...")
    sys.exit(0)


def demarrer_scheduler():
    init_db()

    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        job_collecte,
        trigger=IntervalTrigger(hours=INTERVALLE_HEURES),
        id="collecte_periodique",
        name="Collecte automatique des 7 sources (FR-07)",
        next_run_time=datetime.now(timezone.utc),  # declenchement immediat au demarrage
        max_instances=1,     # empeche deux collectes de tourner en meme temps
        coalesce=True,       # si plusieurs executions ont ete manquees, n'en rattrape qu'une
    )

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info(f"[scheduler] Demarrage - premiere collecte immediate, puis toutes les {INTERVALLE_HEURES}h.")
    logger.info("[scheduler] Appuyer sur Ctrl+C pour arreter.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[scheduler] Arret du scheduler.")


if __name__ == "__main__":
    demarrer_scheduler()