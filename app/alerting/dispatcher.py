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


def _construire_message(exposition, est_confirmation: bool = False) -> tuple:
    """Construit le sujet et le corps du message d'alerte."""
    prefixe = "[CONFIRMATION]" if est_confirmation else "[NOUVELLE ALERTE]"
    sujet = f"{prefixe} SENTINEL - {exposition.nom_entite} - score {exposition.score_confiance:.2f}"

    intro = (
        "Le score de confiance de cette exposition deja connue a augmente significativement suite a une nouvelle source."
        if est_confirmation
        else "Une nouvelle exposition potentielle a ete detectee."
    )

    message = (
        f"{intro}\n\n"
        f"Entite : {exposition.nom_entite}\n"
        f"Categorie : {exposition.categorie_fuite.value}\n"
        f"Score de confiance : {exposition.score_confiance:.2f}\n"
        f"Detection : {exposition.date_premiere_detection.strftime('%d/%m/%Y %H:%M')}\n"
        f"Consultez le tableau de bord Sentinel pour plus de details."
    )
    return sujet, message


def declencher_alertes(session, exposition, est_nouvelle: bool = True, ancien_score: float = None,
                        seuil_minimum: float = 0.6) -> list:
    """
    FR-25 - Point d'entree : declenche les alertes pour une exposition.
    """
    from app.config_system import get_config_float

    if seuil_minimum is None:
        seuil_minimum = get_config_float("seuil_alerte_minimum")

    if exposition.score_confiance < seuil_minimum:
        return []

    est_confirmation = False

    if not est_nouvelle:
        if ancien_score is None:
            return []
        seuil_hausse = get_config_float("seuil_hausse_confirmation")
        hausse = exposition.score_confiance - ancien_score
        if hausse < seuil_hausse:
            return []
        est_confirmation = True

    canaux = determiner_canaux(exposition)
    sujet, message = _construire_message(exposition, est_confirmation=est_confirmation)

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
    type_alerte = "CONFIRMATION" if est_confirmation else "NOUVELLE"
    logger.info(
        f"[alerting] [{type_alerte}] {len(alertes_creees)} alerte(s) creee(s) pour "
        f"'{exposition.nom_entite}' (canaux: {[c.canal.value for c in alertes_creees]})"
    )

    return alertes_creees