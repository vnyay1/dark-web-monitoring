"""
FR-07 - Etat partage du scheduler de collecte et fil d'evenements.

POURQUOI CE MODULE - le scheduler tourne dans un processus SEPARE du
serveur Flask. Sans etat partage, l'interface de supervision ne pouvait
rien savoir de lui : la version precedente affichait donc un dictionnaire
de valeurs simulees en memoire, et ses boutons ne pilotaient rien.

Tout passe desormais par la base, seul canal commun aux deux processus :

  - EtatScheduler porte le VERROU d'instance unique et le tableau de bord ;
  - EvenementCollecte porte le fil d'activite lu par la console.

Ce module est le SEUL point d'acces a ces deux tables : le pipeline y
publie son avancement, le web l'interroge, le scheduler y tient son
verrou. Aucun des trois ne manipule ces modeles directement.
"""

import json
import logging
import os
import socket
from datetime import timedelta

from sqlalchemy import or_, update

from app.db import get_session
from app.models import (
    EtatScheduler,
    EvenementCollecte,
    StatutScheduler,
    TypeEvenementCollecte,
    utc_now,
)

logger = logging.getLogger(__name__)


# Le processus rafraichit son heartbeat a cet intervalle...
INTERVALLE_HEARTBEAT_SECONDES = 30
# ...et son verrou est considere comme abandonne au-dela de celui-ci.
# Trois battements manques : assez pour absorber une VM momentanement
# chargee, sans laisser un verrou fantome bloquer le systeme apres un
# kill -9 ou une coupure brutale.
PEREMPTION_VERROU_SECONDES = 90

# Retention du fil d'activite. C'est un fil de supervision, pas une
# archive : l'audit durable vit dans JournalAudit (FR-17).
RETENTION_EVENEMENTS_JOURS = 7

# Garde-fou : au-dela, la console recevrait plus de lignes qu'elle n'en
# peut afficher utilement en une fois.
MAX_EVENEMENTS_PAR_LECTURE = 500


# ---------------------------------------------------------------------
# Acces a la ligne d'etat
# ---------------------------------------------------------------------

def _etat(session) -> EtatScheduler:
    """Retourne la ligne unique d'etat, en la creant au premier appel."""
    etat = session.get(EtatScheduler, 1)

    if etat is None:
        etat = EtatScheduler(id=1, actif=False, statut=StatutScheduler.ARRETE)
        session.add(etat)
        session.commit()

    return etat


def _verrou_est_perime(etat: EtatScheduler) -> bool:
    """Un verrou sans heartbeat frais appartient a un processus disparu."""
    if not etat.actif or etat.heartbeat is None:
        return True
    return (utc_now() - etat.heartbeat).total_seconds() > PEREMPTION_VERROU_SECONDES


def scheduler_est_actif() -> bool:
    """True si un processus scheduler vivant detient le verrou."""
    session = get_session()
    try:
        return not _verrou_est_perime(_etat(session))
    finally:
        session.close()


# ---------------------------------------------------------------------
# Verrou d'instance unique
# ---------------------------------------------------------------------

def reclamer_verrou() -> tuple:
    """
    Tente de prendre le verrou pour le processus courant.

    Retourne (obtenu: bool, detail: str). L'operation tient en UN SEUL
    UPDATE conditionnel plutot qu'en lire-puis-ecrire : deux processus
    demarres simultanement passeraient tous deux le test de lecture, et
    s'attribueraient tous deux le verrou.
    """
    session = get_session()
    try:
        etat = _etat(session)
        limite = utc_now() - timedelta(seconds=PEREMPTION_VERROU_SECONDES)
        maintenant = utc_now()

        resultat = session.execute(
            update(EtatScheduler)
            .where(
                EtatScheduler.id == 1,
                or_(
                    EtatScheduler.actif.is_(False),
                    EtatScheduler.heartbeat.is_(None),
                    EtatScheduler.heartbeat < limite,
                ),
            )
            .values(
                actif=True,
                statut=StatutScheduler.EN_ATTENTE,
                pid=os.getpid(),
                hostname=socket.gethostname(),
                demarre_le=maintenant,
                heartbeat=maintenant,
                source_en_cours=None,
                collecte_immediate_demandee=False,
            )
        )
        session.commit()

        if resultat.rowcount == 1:
            logger.info(f"[supervision] Verrou obtenu (pid={os.getpid()}).")
            return True, "Verrou obtenu."

        session.refresh(etat)
        detail = (
            f"Un scheduler est deja actif (pid={etat.pid} sur {etat.hostname}, "
            f"demarre le {etat.demarre_le:%d/%m/%Y a %H:%M} UTC)."
        )
        logger.warning(f"[supervision] Verrou refuse : {detail}")
        return False, detail
    finally:
        session.close()


def liberer_verrou():
    """Rend le verrou et remet l'etat a l'arret."""
    session = get_session()
    try:
        etat = _etat(session)
        etat.actif = False
        etat.statut = StatutScheduler.ARRETE
        etat.pid = None
        etat.hostname = None
        etat.source_en_cours = None
        etat.heartbeat = None
        etat.collecte_immediate_demandee = False
        session.commit()
        logger.info("[supervision] Verrou libere.")
    finally:
        session.close()


def battre_coeur(statut: StatutScheduler = None, source_en_cours=False):
    """
    Rafraichit le heartbeat, et accessoirement le statut ou la source en
    cours d'analyse.

    source_en_cours vaut False par defaut (et non None) pour distinguer
    "ne pas y toucher" de "remettre a vide".
    """
    session = get_session()
    try:
        etat = _etat(session)
        etat.heartbeat = utc_now()
        if statut is not None:
            etat.statut = statut
        if source_en_cours is not False:
            etat.source_en_cours = source_en_cours
        session.commit()
    finally:
        session.close()


def enregistrer_planification(prochaine_execution):
    """Publie la prochaine echeance, affichee par la console."""
    session = get_session()
    try:
        etat = _etat(session)
        etat.prochaine_execution = prochaine_execution
        etat.heartbeat = utc_now()
        session.commit()
    finally:
        session.close()


def enregistrer_fin_de_cycle(stats: list):
    """Archive le resume du cycle qui vient de s'achever."""
    session = get_session()
    try:
        etat = _etat(session)
        etat.derniere_execution = utc_now()
        etat.source_en_cours = None
        etat.statut = StatutScheduler.EN_ATTENTE
        etat.heartbeat = utc_now()
        etat.derniere_stats = json.dumps(stats, default=str)[:100000]
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------
# Collecte immediate demandee depuis l'interface
# ---------------------------------------------------------------------

def demander_collecte_immediate() -> bool:
    """Leve le drapeau lu par le processus scheduler a son prochain reveil."""
    session = get_session()
    try:
        etat = _etat(session)
        if _verrou_est_perime(etat):
            return False
        etat.collecte_immediate_demandee = True
        session.commit()
        return True
    finally:
        session.close()


def consommer_demande_collecte() -> bool:
    """Retourne True si une collecte immediate etait demandee, et l'efface."""
    session = get_session()
    try:
        etat = _etat(session)
        if not etat.collecte_immediate_demandee:
            return False
        etat.collecte_immediate_demandee = False
        session.commit()
        return True
    finally:
        session.close()


# ---------------------------------------------------------------------
# Fil d'evenements
# ---------------------------------------------------------------------

def emettre(type_evenement: TypeEvenementCollecte, message: str,
            source: str = None, exposition_id: str = None,
            session=None):
    """
    Publie un evenement dans le fil de supervision.

    Ne leve JAMAIS : un incident de journalisation ne doit pas interrompre
    une collecte en cours. En cas d'echec on se rabat sur le log fichier.

    session : session existante a reutiliser (le pipeline en a deja une).
    """
    propre = session is None
    session = session or get_session()

    try:
        session.add(EvenementCollecte(
            type_evenement=type_evenement,
            message=str(message)[:500],
            source=source,
            exposition_id=exposition_id,
        ))
        session.commit()
    except Exception as erreur:
        logger.warning(f"[supervision] Evenement non enregistre : {erreur}")
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        if propre:
            session.close()


def evenements_depuis(dernier_id: int = 0, limite: int = 100) -> list:
    """
    Evenements posterieurs a dernier_id, du plus ancien au plus recent.

    L'ordre chronologique est celui d'affichage d'une console : la page
    ajoute les nouvelles lignes en bas sans avoir a les retourner.
    """
    limite = max(1, min(limite, MAX_EVENEMENTS_PAR_LECTURE))

    session = get_session()
    try:
        lignes = (
            session.query(EvenementCollecte)
            .filter(EvenementCollecte.id > (dernier_id or 0))
            .order_by(EvenementCollecte.id.asc())
            .limit(limite)
            .all()
        )
        return [
            {
                "id": e.id,
                "horodatage": e.horodatage.isoformat(),
                "type": e.type_evenement.value,
                "source": e.source,
                "message": e.message,
                "exposition_id": e.exposition_id,
            }
            for e in lignes
        ]
    finally:
        session.close()


def dernier_evenement_id() -> int:
    """
    Id du dernier evenement connu. La console s'en sert au chargement pour
    ne pas rejouer tout l'historique avant de suivre le direct.
    """
    session = get_session()
    try:
        derniere = (
            session.query(EvenementCollecte.id)
            .order_by(EvenementCollecte.id.desc())
            .first()
        )
        return derniere[0] if derniere else 0
    finally:
        session.close()


def purger_evenements(session=None, jours: int = RETENTION_EVENEMENTS_JOURS) -> int:
    """Supprime les evenements plus vieux que la retention."""
    propre = session is None
    session = session or get_session()

    try:
        supprimes = (
            session.query(EvenementCollecte)
            .filter(EvenementCollecte.horodatage < utc_now() - timedelta(days=jours))
            .delete(synchronize_session=False)
        )
        session.commit()
        if supprimes:
            logger.info(f"[supervision] {supprimes} evenement(s) purge(s).")
        return supprimes
    finally:
        if propre:
            session.close()


# ---------------------------------------------------------------------
# Lecture pour l'interface
# ---------------------------------------------------------------------

def etat_courant() -> dict:
    """Instantane complet de l'etat du scheduler, pret a serialiser."""
    session = get_session()
    try:
        etat = _etat(session)
        vivant = not _verrou_est_perime(etat)

        def horodater(valeur):
            return valeur.isoformat() if valeur else None

        return {
            "actif": vivant,
            # Un verrou perime signale un processus disparu sans arret
            # propre : on l'affiche comme arrete plutot que de laisser
            # croire a une collecte en cours qui n'existe plus.
            "statut": etat.statut.value if vivant else StatutScheduler.ARRETE.value,
            "pid": etat.pid if vivant else None,
            "hostname": etat.hostname if vivant else None,
            "demarre_le": horodater(etat.demarre_le) if vivant else None,
            "heartbeat": horodater(etat.heartbeat),
            "source_en_cours": etat.source_en_cours if vivant else None,
            "derniere_execution": horodater(etat.derniere_execution),
            "prochaine_execution": horodater(etat.prochaine_execution) if vivant else None,
            "collecte_immediate_demandee": bool(etat.collecte_immediate_demandee),
            "derniere_stats": json.loads(etat.derniere_stats) if etat.derniere_stats else None,
        }
    finally:
        session.close()
