"""
FR-07 - Planification automatique de la collecte.

CADENCE - UNE collecte par jour, a une heure TIREE AU HASARD dans la plage
autorisee (reglee par l'administrateur : collecte_heure_min /
collecte_heure_max). L'ancienne version passait toutes les 6h a heure fixe,
ce qui dessinait cote sources un schema parfaitement previsible : quatre
visites quotidiennes, toujours aux memes minutes. Une fenetre quotidienne
imprevisible sert mieux la collecte passive (CN-09/CN-10) tout en restant
suffisante pour des sites de fuite qui publient au rythme de quelques
annonces par jour.

INSTANCE UNIQUE - le processus reclame un verrou en base au demarrage
(app.supervision) et refuse de tourner si un autre scheduler est deja
actif, qu'il ait ete lance depuis l'interface web ou en ligne de commande.
Le verrou expire de lui-meme si le processus disparait sans arret propre.

Ce script est concu pour tourner comme un PROCESSUS INDEPENDANT du serveur
Flask (run.py) - ne pas l'importer dans l'application web, pour eviter les
doublons de planification en cas de rechargement automatique du serveur en
mode developpement.

Usage : python3 -m app.scheduler
"""

import logging
import random
import signal
import sys
import threading
from datetime import datetime, time as heure_du_jour, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config_system import get_config_int
from app.db import init_db
from app.models import StatutScheduler, TypeEvenementCollecte, utc_now
from app.pipeline import executer_tous_les_connecteurs
from app import supervision

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# Frequence a laquelle le processus regarde si une collecte immediate a ete
# demandee depuis l'interface. Assez court pour que le bouton paraisse
# reactif, assez long pour ne pas marteler la base.
INTERVALLE_VERIFICATION_DEMANDE_SECONDES = 5

# Une seule collecte a la fois, quelle que soit son origine (echeance
# quotidienne ou demande manuelle). APScheduler garantit deja
# max_instances=1 par job, mais pas ENTRE deux jobs distincts.
_verrou_collecte = threading.Lock()

_scheduler = None


def prochaine_execution_aleatoire(depuis: datetime = None) -> datetime:
    """
    Tire l'echeance du prochain cycle : le jour suivant, a une heure et une
    minute aleatoires dans la plage autorisee.

    Les bornes sont relues a chaque tirage (et non au demarrage) pour qu'un
    changement de reglage prenne effet des le cycle suivant, sans avoir a
    redemarrer le processus.
    """
    depuis = depuis or utc_now()

    heure_min = max(0, min(23, get_config_int("collecte_heure_min")))
    heure_max = max(0, min(23, get_config_int("collecte_heure_max")))
    if heure_min > heure_max:
        # Reglage incoherent : on ne veut ni planter, ni figer la collecte.
        logger.warning(
            f"[scheduler] Plage horaire incoherente ({heure_min}h-{heure_max}h), "
            f"bornes inversees."
        )
        heure_min, heure_max = heure_max, heure_min

    demain = (depuis + timedelta(days=1)).date()
    tirage = heure_du_jour(
        hour=random.randint(heure_min, heure_max),
        minute=random.randint(0, 59),
    )
    return datetime.combine(demain, tirage)


def _executer_cycle(origine: str):
    """
    Execute un cycle de collecte complet et publie son avancement.

    Le verrou empeche qu'une demande manuelle ne se superpose au cycle
    quotidien : deux collectes simultanees violeraient le rate limiting
    par source (FR-06), BaseConnector serialisant les requetes par source
    et non par processus.
    """
    if not _verrou_collecte.acquire(blocking=False):
        logger.warning(f"[scheduler] Cycle ({origine}) ignore : une collecte est deja en cours.")
        return

    try:
        logger.info("=" * 60)
        logger.info(f"[scheduler] Debut de la collecte ({origine})")
        logger.info("=" * 60)

        supervision.battre_coeur(
            statut=StatutScheduler.COLLECTE_EN_COURS, source_en_cours=None
        )
        supervision.emettre(
            TypeEvenementCollecte.DEBUT_CYCLE,
            f"Debut du cycle de collecte ({origine}).",
        )

        resultats = executer_tous_les_connecteurs()

        total_expositions = sum(
            r.get("nb_expositions_creees_ou_maj", 0) for r in resultats
        )
        total_echecs = sum(1 for r in resultats if not r.get("collecte_reussie"))

        resume = (
            f"{total_expositions} exposition(s) traitee(s), "
            f"{total_echecs} source(s) en echec sur {len(resultats)}"
        )
        logger.info(f"[scheduler] Collecte terminee : {resume}")

        supervision.enregistrer_fin_de_cycle(resultats)
        supervision.emettre(TypeEvenementCollecte.FIN_CYCLE, f"Cycle termine : {resume}.")

    except Exception as e:
        # Une erreur dans une collecte ne doit JAMAIS arreter le scheduler -
        # sinon toutes les collectes futures seraient perdues silencieusement.
        logger.exception(f"[scheduler] Erreur inattendue durant la collecte : {e}")
        supervision.battre_coeur(statut=StatutScheduler.EN_ATTENTE, source_en_cours=None)
    finally:
        _verrou_collecte.release()


def job_collecte_quotidienne():
    """Cycle declenche par l'echeance du jour, puis replanifie la suivante."""
    _executer_cycle("echeance quotidienne")
    _planifier_prochain_cycle()


def job_verifier_demande():
    """Sert le bouton "Collecte immediate" de l'interface de supervision."""
    if supervision.consommer_demande_collecte():
        logger.info("[scheduler] Collecte immediate demandee depuis l'interface.")
        _executer_cycle("demande manuelle")


def job_heartbeat():
    """Signale que le processus est vivant (cf. peremption du verrou)."""
    supervision.battre_coeur()


def _planifier_prochain_cycle():
    """Programme le cycle suivant et publie son echeance pour l'interface."""
    prochaine = prochaine_execution_aleatoire()

    _scheduler.add_job(
        job_collecte_quotidienne,
        trigger=DateTrigger(run_date=prochaine),
        id="collecte_quotidienne",
        name="Collecte automatique quotidienne (FR-07)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    supervision.enregistrer_planification(prochaine)
    logger.info(
        f"[scheduler] Prochaine collecte planifiee le "
        f"{prochaine:%d/%m/%Y a %H:%M} UTC (heure tiree au hasard)."
    )


def _arreter(signum=None, frame=None):
    """Arret propre : le verrou doit etre rendu, sinon il bloque 90s."""
    logger.info("[scheduler] Signal d'arret recu, arret du scheduler...")
    try:
        if _scheduler is not None and _scheduler.running:
            _scheduler.shutdown(wait=False)
    finally:
        supervision.liberer_verrou()
    sys.exit(0)


def demarrer_scheduler(collecte_immediate_au_demarrage: bool = True):
    global _scheduler

    init_db()

    obtenu, detail = supervision.reclamer_verrou()
    if not obtenu:
        logger.error(f"[scheduler] Demarrage refuse. {detail}")
        print(f"\n[REFUS] {detail}")
        print("Arretez le scheduler existant avant d'en lancer un autre.")
        return 1

    _scheduler = BlockingScheduler(timezone="UTC")

    _scheduler.add_job(
        job_heartbeat,
        trigger=IntervalTrigger(seconds=supervision.INTERVALLE_HEARTBEAT_SECONDES),
        id="heartbeat",
        name="Signal de vie du scheduler",
        max_instances=1,
        coalesce=True,
    )

    _scheduler.add_job(
        job_verifier_demande,
        trigger=IntervalTrigger(seconds=INTERVALLE_VERIFICATION_DEMANDE_SECONDES),
        id="verification_demande",
        name="Prise en compte des collectes immediates",
        max_instances=1,
        coalesce=True,
    )

    if collecte_immediate_au_demarrage:
        # Un premier cycle au demarrage donne une retour immediat a
        # l'operateur qui vient d'appuyer sur "Demarrer", et evite
        # d'attendre le lendemain pour la premiere collecte.
        _scheduler.add_job(
            lambda: _executer_cycle("demarrage"),
            trigger=DateTrigger(run_date=utc_now()),
            id="collecte_initiale",
            name="Premiere collecte au demarrage",
        )

    _planifier_prochain_cycle()

    signal.signal(signal.SIGINT, _arreter)
    signal.signal(signal.SIGTERM, _arreter)

    logger.info("[scheduler] Demarre. Une collecte par jour, a heure aleatoire.")
    logger.info("[scheduler] Appuyer sur Ctrl+C pour arreter.")

    try:
        _scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[scheduler] Arret du scheduler.")
    finally:
        supervision.liberer_verrou()

    return 0


def _analyser_arguments():
    import argparse

    parseur = argparse.ArgumentParser(
        description="Planificateur de collecte (FR-07) - une collecte par jour, a heure aleatoire."
    )
    parseur.add_argument(
        "--sans-collecte-initiale", action="store_true",
        help="Demarrer en veille, sans lancer de collecte immediate "
             "(utile pour un redemarrage apres incident).",
    )
    return parseur.parse_args()


if __name__ == "__main__":
    arguments = _analyser_arguments()
    sys.exit(demarrer_scheduler(
        collecte_immediate_au_demarrage=not arguments.sans_collecte_initiale
    ))
