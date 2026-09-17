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

ECHEANCE MANQUEE - le cycle quotidien est un job ponctuel, et c'est lui qui
programme le suivant a sa fin. Si l'echeance passait sans qu'il s'execute
(machine en veille ou eteinte, processus bloque, reprogrammation en
echec), plus rien n'etait programme et la console affichait indefiniment
une date passee. Trois detections se completent : l'evenement "missed"
d'APScheduler au reveil, une surveillance toutes les minutes, et un
controle au demarrage. Une echeance manquee est signalee dans la console
(ECHEANCE_MANQUEE) et une nouvelle collecte est programmee le jour meme si
la plage horaire le permet encore, sinon le lendemain.

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
from datetime import datetime, time as heure_du_jour, timedelta, timezone

from apscheduler.events import EVENT_JOB_MISSED
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config_system import get_config_int
from app.db import init_db
from app.models import TypeEvenementCollecte, utc_now
from app.pipeline import executer_tous_les_connecteurs
from app import supervision, tor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# Frequence a laquelle le processus regarde si une collecte immediate a ete
# demandee depuis l'interface. Assez court pour que le bouton paraisse
# reactif, assez long pour ne pas marteler la base.
INTERVALLE_VERIFICATION_DEMANDE_SECONDES = 5

ID_COLLECTE_QUOTIDIENNE = "collecte_quotidienne"

# Retard tolere par APScheduler : un cycle reveille jusqu'a une heure apres
# son echeance s'execute quand meme ; au-dela, il est abandonne ("missed").
MISFIRE_GRACE_SECONDES = 3600

# Frequence de la surveillance des echeances, filet de securite de
# l'evenement "missed".
INTERVALLE_SURVEILLANCE_SECONDES = 60

# Delai minimum avant une collecte de rattrapage : laisse a une machine qui
# se reveille le temps de retrouver le reseau et Tor.
DELAI_MINIMUM_RATTRAPAGE = timedelta(minutes=10)

# Une seule collecte a la fois, quelle que soit son origine (echeance
# quotidienne ou demande manuelle). APScheduler garantit deja
# max_instances=1 par job, mais pas ENTRE deux jobs distincts.
_verrou_collecte = threading.Lock()

# L'evenement "missed" et la surveillance peuvent constater la meme echeance
# manquee au meme instant (au reveil) : un seul des deux la traite.
_verrou_echeance = threading.Lock()

_scheduler = None

# Derniere constatation d'IP deja publiee par ce processus : evite de
# reecrire la base toutes les 5 secondes quand rien n'a change.
_derniere_ip_publiee = None


def _plage_horaire() -> tuple:
    """
    Plage horaire autorisee (heure_min, heure_max), en UTC.

    Les bornes sont relues a chaque tirage (et non au demarrage) pour qu'un
    changement de reglage prenne effet des le cycle suivant, sans avoir a
    redemarrer le processus.
    """
    heure_min = max(0, min(23, get_config_int("collecte_heure_min")))
    heure_max = max(0, min(23, get_config_int("collecte_heure_max")))
    if heure_min > heure_max:
        # Reglage incoherent : on ne veut ni planter, ni figer la collecte.
        logger.warning(
            f"[scheduler] Plage horaire incoherente ({heure_min}h-{heure_max}h), "
            f"bornes inversees."
        )
        heure_min, heure_max = heure_max, heure_min
    return heure_min, heure_max


def _tirage_du_lendemain(depuis: datetime, heure_min: int, heure_max: int) -> datetime:
    demain = (depuis + timedelta(days=1)).date()
    tirage = heure_du_jour(
        hour=random.randint(heure_min, heure_max),
        minute=random.randint(0, 59),
    )
    return datetime.combine(demain, tirage)


def prochaine_execution_aleatoire(depuis: datetime = None) -> datetime:
    """
    Tire l'echeance du prochain cycle : le jour suivant, a une heure et une
    minute aleatoires dans la plage autorisee.
    """
    depuis = depuis or utc_now()
    return _tirage_du_lendemain(depuis, *_plage_horaire())


def echeance_de_rattrapage(maintenant: datetime = None) -> datetime:
    """
    Echeance qui remplace une collecte manquee : le jour meme, a une minute
    tiree au hasard entre maintenant + DELAI_MINIMUM_RATTRAPAGE et la fin de
    la plage horaire ; le lendemain (tirage habituel) si la plage du jour
    est deja passee. L'heure reste imprevisible pour les sources.
    """
    maintenant = maintenant or utc_now()
    heure_min, heure_max = _plage_horaire()
    jour = maintenant.date()

    debut = max(
        maintenant + DELAI_MINIMUM_RATTRAPAGE,
        datetime.combine(jour, heure_du_jour(hour=heure_min)),
    )
    # Minute pleine superieure, comme le tirage quotidien.
    if debut.second or debut.microsecond:
        debut = debut.replace(second=0, microsecond=0) + timedelta(minutes=1)
    fin = datetime.combine(jour, heure_du_jour(hour=heure_max, minute=59))

    if debut > fin:
        return _tirage_du_lendemain(maintenant, heure_min, heure_max)

    minutes_disponibles = int((fin - debut).total_seconds() // 60)
    return debut + timedelta(minutes=random.randint(0, minutes_disponibles))


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

        supervision.marquer_debut_collecte()
        supervision.emettre(
            TypeEvenementCollecte.DEBUT_CYCLE,
            f"Debut du cycle de collecte ({origine}).",
        )

        # IP de reference en debut de cycle : chaque renouvellement de
        # circuit pendant la collecte se lira ensuite par rapport a elle.
        _publier_ip(tor.verifier_ip_sortie())

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
        supervision.interrompre_collecte()
    finally:
        _verrou_collecte.release()


def job_collecte_quotidienne():
    """Cycle declenche par l'echeance du jour, puis replanifie la suivante."""
    _executer_cycle("echeance quotidienne")
    try:
        _planifier_prochain_cycle()
    except Exception as e:
        # Sans job programme, plus aucune collecte n'aurait lieu : la
        # surveillance des echeances reessaie a la minute suivante.
        logger.exception(
            f"[scheduler] Reprogrammation impossible apres le cycle : {e}. "
            f"Nouvel essai par la surveillance des echeances."
        )


def job_verifier_demande():
    """Sert le bouton "Collecte immediate" de l'interface de supervision."""
    if supervision.consommer_demande_collecte():
        logger.info("[scheduler] Collecte immediate demandee depuis l'interface.")
        _executer_cycle("demande manuelle")


def _publier_ip(ip):
    """Publie une IP de sortie constatee ; une verification echouee n'efface rien."""
    global _derniere_ip_publiee

    if not ip:
        return
    constatation = (ip, tor.derniere_ip_sortie()[1] or utc_now())
    supervision.publier_ip_sortie(*constatation)
    _derniere_ip_publiee = constatation


def job_synchroniser_tor():
    """
    Publie pour la console l'IP de sortie Tor constatee par ce processus,
    et sert le bouton "Verifier maintenant".

    Job DISTINCT de job_verifier_demande : ce dernier execute la collecte
    immediate dans son propre fil et reste donc occupe pendant toute sa
    duree. Greffee sur lui, la synchronisation ne tournerait jamais pendant
    une collecte manuelle - precisement quand les circuits se renouvellent.
    """
    if supervision.consommer_demande_verification_ip():
        logger.info("[scheduler] Verification de l'IP de sortie demandee depuis l'interface.")
        ip = tor.verifier_ip_sortie()
        if ip:
            _publier_ip(ip)
        else:
            logger.warning("[scheduler] Verification de l'IP de sortie echouee.")
        return

    # Sinon, simple report de la derniere IP constatee par le module Tor,
    # qui la releve a chaque renouvellement de circuit. Aucune requete Tor,
    # et aucune ecriture en base si rien de neuf n'a ete constate.
    ip, constatee_le = tor.derniere_ip_sortie()
    if ip and (ip, constatee_le) != _derniere_ip_publiee:
        _publier_ip(ip)


def job_heartbeat():
    """Signale que le processus est vivant (cf. peremption du verrou)."""
    supervision.battre_coeur()


def _planifier_prochain_cycle(prochaine: datetime = None) -> datetime:
    """
    Programme le cycle suivant et publie son echeance pour l'interface.

    prochaine : echeance imposee (rattrapage) ; par defaut, tirage au
    hasard le lendemain.
    """
    if prochaine is None:
        prochaine = prochaine_execution_aleatoire()

    _scheduler.add_job(
        job_collecte_quotidienne,
        # Fuseau explicite : sans lui, APScheduler lit cette heure UTC naive
        # dans le fuseau LOCAL de la machine (et non celui du scheduler), et
        # la collecte partait decalee de l'heure affichee.
        trigger=DateTrigger(run_date=prochaine, timezone=timezone.utc),
        id=ID_COLLECTE_QUOTIDIENNE,
        name="Collecte automatique quotidienne (FR-07)",
        replace_existing=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDES,
    )

    supervision.enregistrer_planification(prochaine)
    logger.info(
        f"[scheduler] Prochaine collecte planifiee le "
        f"{prochaine:%d/%m/%Y a %H:%M} UTC (heure tiree au hasard)."
    )
    return prochaine


# ---------------------------------------------------------------------
# Echeance manquee
# ---------------------------------------------------------------------

def _utc_naif(instant: datetime) -> datetime:
    """APScheduler manipule des datetimes avec fuseau ; le projet, de l'UTC naif."""
    if instant.tzinfo is None:
        return instant
    return instant.astimezone(timezone.utc).replace(tzinfo=None)


def _signaler_echeance_manquee(echeance: datetime, cause: str,
                               prochaine: datetime = None) -> datetime:
    """
    Journalise l'echeance manquee en erreur, la signale dans la console de
    supervision et programme la collecte suivante (rattrapage du jour par
    defaut). Retourne la nouvelle echeance.
    """
    prochaine = _planifier_prochain_cycle(prochaine or echeance_de_rattrapage())
    message = (
        f"Collecte prevue le {echeance:%d/%m/%Y a %H:%M} UTC non effectuee ({cause}). "
        f"Nouvelle collecte programmee le {prochaine:%d/%m/%Y a %H:%M} UTC."
    )
    logger.error(f"[scheduler] {message}")
    supervision.emettre(TypeEvenementCollecte.ECHEANCE_MANQUEE, message)
    return prochaine


def _rattraper_si_necessaire(cause: str, echeance_manquee: datetime = None) -> bool:
    """
    Verifie qu'une collecte est bien programmee, et sinon en programme une.
    Retourne True si une (re)programmation a eu lieu.

    echeance_manquee : echeance signalee par APScheduler ; a defaut, celle
    enregistree en base.
    """
    with _verrou_echeance:
        # Un cycle en cours reprogramme lui-meme la suite a sa fin.
        if _verrou_collecte.locked():
            return False

        maintenant = utc_now()
        marge = timedelta(seconds=supervision.MARGE_ECHEANCE_SECONDES)
        job = _scheduler.get_job(ID_COLLECTE_QUOTIDIENNE)
        if job is not None and job.next_run_time is not None:
            # Un job en retard mais dans la tolerance d'APScheduler va
            # s'executer : ce n'est pas une echeance manquee.
            tolerance = timedelta(seconds=MISFIRE_GRACE_SECONDES) + marge
            if _utc_naif(job.next_run_time) > maintenant - tolerance:
                return False

        planification = supervision.derniere_planification()
        echeance = echeance_manquee or planification["prochaine_execution"]
        debut_cycle = planification["debut_collecte"]

        if echeance is None:
            logger.warning("[scheduler] Aucune collecte programmee : planification.")
            _planifier_prochain_cycle()
            return True

        if echeance > maintenant - marge:
            # Job perdu, mais son echeance n'est pas encore passee : on le remet.
            logger.warning("[scheduler] Job de collecte absent : echeance reprogrammee.")
            _planifier_prochain_cycle(echeance)
            return True

        if debut_cycle is not None and debut_cycle >= echeance:
            # La collecte a eu lieu ; seule sa reprogrammation a echoue.
            logger.warning(
                "[scheduler] Aucune collecte programmee apres le dernier cycle : planification."
            )
            _planifier_prochain_cycle()
            return True

        _signaler_echeance_manquee(echeance, cause)
        return True


def _sur_job_manque(evenement):
    """
    Ecouteur APScheduler : le cycle quotidien a ete abandonne, reveille plus
    de MISFIRE_GRACE_SECONDES apres son echeance.
    """
    if evenement.job_id != ID_COLLECTE_QUOTIDIENNE:
        return
    # Traitement differe dans un job DISTINCT : APScheduler peut appeler cet
    # ecouteur depuis sa boucle principale avant d'avoir retire le job manque
    # du magasin. Un job de meme identifiant ajoute ici serait aussitot
    # supprime avec lui (constate en test).
    try:
        _scheduler.add_job(
            _rattraper_si_necessaire,
            trigger=DateTrigger(run_date=utc_now(), timezone=timezone.utc),
            args=["reveil trop tardif : machine en veille ou processus bloque"],
            kwargs={"echeance_manquee": _utc_naif(evenement.scheduled_run_time)},
            id="rattrapage_echeance",
            name="Rattrapage d'une echeance de collecte manquee",
            replace_existing=True,
            misfire_grace_time=MISFIRE_GRACE_SECONDES,
        )
    except Exception:
        logger.exception(
            "[scheduler] Echeance manquee non traitee ; nouvel essai par la surveillance."
        )


def job_surveiller_echeance():
    """
    Filet de securite, toutes les minutes : aucune echeance ne doit rester
    dans le passe sans qu'une collecte soit programmee apres elle.
    """
    _rattraper_si_necessaire(
        "echeance depassee sans declenchement : machine en veille, "
        "processus bloque ou reprogrammation en echec"
    )


def _planifier_au_demarrage(collecte_initiale: bool):
    """
    Planification du premier cycle. Si l'echeance enregistree par le
    processus precedent est passee sans avoir ete executee (scheduler
    arrete, machine eteinte), elle est signalee comme manquee.
    """
    planification = supervision.derniere_planification()
    echeance = planification["prochaine_execution"]
    debut_cycle = planification["debut_collecte"]

    manquee = (
        echeance is not None
        and echeance < utc_now()
        and (debut_cycle is None or debut_cycle < echeance)
    )
    if not manquee:
        _planifier_prochain_cycle()
        return

    if collecte_initiale:
        # Une collecte part tout de suite : la suivante reste au lendemain,
        # pour ne pas en faire deux le meme jour.
        _signaler_echeance_manquee(
            echeance,
            "scheduler arrete ou machine eteinte ; une collecte est lancee au demarrage",
            prochaine=prochaine_execution_aleatoire(),
        )
    else:
        _signaler_echeance_manquee(echeance, "scheduler arrete ou machine eteinte")


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

    _scheduler.add_job(
        job_synchroniser_tor,
        trigger=IntervalTrigger(seconds=INTERVALLE_VERIFICATION_DEMANDE_SECONDES),
        id="synchronisation_tor",
        name="Publication de l'IP de sortie Tor",
        max_instances=1,
        coalesce=True,
    )

    _scheduler.add_job(
        job_surveiller_echeance,
        trigger=IntervalTrigger(seconds=INTERVALLE_SURVEILLANCE_SECONDES),
        id="surveillance_echeance",
        name="Detection des echeances de collecte manquees",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_listener(_sur_job_manque, EVENT_JOB_MISSED)

    if collecte_immediate_au_demarrage:
        # Un premier cycle au demarrage donne une retour immediat a
        # l'operateur qui vient d'appuyer sur "Demarrer", et evite
        # d'attendre le lendemain pour la premiere collecte.
        _scheduler.add_job(
            lambda: _executer_cycle("demarrage"),
            trigger=DateTrigger(run_date=utc_now(), timezone=timezone.utc),
            id="collecte_initiale",
            name="Premiere collecte au demarrage",
        )

    _planifier_au_demarrage(collecte_immediate_au_demarrage)

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
