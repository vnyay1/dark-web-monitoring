"""
FR-25/FR-26 - Point d'entree principal : cree et envoie les alertes
pour une exposition donnee, selon les canaux determines par les regles.
"""

import logging

from app.models import Alerte, CanalAlerte, StatutEnvoiAlerte, utc_now
from app.alerting.rules import determiner_canaux
from app.alerting.senders import SENDERS

logger = logging.getLogger(__name__)


# Destinataires par canal - a terme, ceci devrait venir d'une
# configuration (table en base ou .env) plutot que d'etre code en dur.
# Laisse en placeholder en attendant les vraies coordonnees ANTIC.
DESTINATAIRES = {
    "email": "cirt-alertes@antic.cm",
    "sms": "+237000000000",
    "whatsapp": "+237000000000",
}


def _construire_message(exposition) -> tuple:
    """Construit le sujet et le corps du message d'alerte."""
    sujet = f"[SENTINEL] Nouvelle exposition detectee - score {exposition.score_confiance:.2f}"
    message = (
        f"Entite : {exposition.nom_entite}\n"
        f"Categorie : {exposition.categorie_fuite.value}\n"
        f"Score de confiance : {exposition.score_confiance:.2f}\n"
        f"Detection : {exposition.date_premiere_detection.strftime('%d/%m/%Y %H:%M')}\n"
        f"Consultez le tableau de bord Sentinel pour plus de details."
    )
    return sujet, message


def declencher_alertes(session, exposition, seuil_minimum: float = 0.6) -> list:
    """
    FR-25 - Point d'entree : declenche les alertes pour une exposition
    si son score depasse le seuil minimum configurable.

    Retourne la liste des objets Alerte crees.
    """
    if exposition.score_confiance < seuil_minimum:
        return []

    canaux = determiner_canaux(exposition)
    sujet, message = _construire_message(exposition)

    alertes_creees = []

    for canal in canaux:
        alerte = Alerte(
            exposition_id=exposition.id,
            canal=canal,
            statut_envoi=StatutEnvoiAlerte.EN_ATTENTE,
        )
        session.add(alerte)
        session.flush()

        if canal == CanalAlerte.INTERFACE:
            # L'alerte "interface" n'a rien a envoyer - elle est juste
            # affichee dans le tableau de bord/liste d'alertes
            alerte.statut_envoi = StatutEnvoiAlerte.ENVOYEE
            alerte.date_envoi = utc_now()
        else:
            sender = SENDERS.get(canal.value)
            destinataire = DESTINATAIRES.get(canal.value)

            if sender is None or destinataire is None:
                alerte.statut_envoi = StatutEnvoiAlerte.ECHEC
                alerte.details_echec = "Sender ou destinataire non configure"
                logger.error(f"[alerting] Canal {canal.value} non configure.")
            else:
                try:
                    succes = sender.send(destinataire, sujet, message)
                    if succes:
                        alerte.statut_envoi = StatutEnvoiAlerte.ENVOYEE
                        alerte.date_envoi = utc_now()
                    else:
                        alerte.statut_envoi = StatutEnvoiAlerte.ECHEC
                        alerte.details_echec = "Echec signale par le sender"
                except Exception as e:
                    alerte.statut_envoi = StatutEnvoiAlerte.ECHEC
                    alerte.details_echec = str(e)[:500]
                    logger.error(f"[alerting] Exception lors de l'envoi {canal.value} : {e}")

        alertes_creees.append(alerte)

    session.commit()
    logger.info(
        f"[alerting] {len(alertes_creees)} alerte(s) creee(s) pour "
        f"'{exposition.nom_entite}' (canaux: {[c.canal.value for c in alertes_creees]})"
    )

    return alertes_creees