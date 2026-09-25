"""
FR-25/FR-26 - Point d'entree principal : cree et envoie les alertes
pour une exposition donnee, selon les canaux determines par les regles.
"""

import logging

from app.models import Alerte, CanalAlerte, NiveauCriticite, StatutEnvoiAlerte, utc_now
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
    sujet = (
        f"{prefixe} SENTINEL - {exposition.nom_entite} - "
        f"criticite {exposition.niveau_criticite.value.upper()}"
    )

    intro = (
        "La criticite de cette exposition deja connue a augmente suite a une nouvelle source."
        if est_confirmation
        else "Une nouvelle exposition potentielle a ete detectee."
    )

    message = (
        f"{intro}\n\n"
        f"Entite : {exposition.nom_entite}\n"
        f"Categories : {', '.join(c.nom for c in exposition.categories) or 'non precisee'}\n"
        f"Criticite : {exposition.niveau_criticite.value.upper()} "
        f"(score {exposition.criticite} : selecteurs camerounais distincts, ponderes par leur poids)\n"
        f"Detection : {exposition.date_premiere_detection.strftime('%d/%m/%Y %H:%M')}\n"
        f"Consultez le tableau de bord Sentinel pour plus de details."
    )
    return sujet, message


# Ordre des paliers, du moins au plus grave. Sert a comparer le niveau
# d'une exposition au niveau minimum configure : NiveauCriticite est une
# enumeration de chaines, donc non ordonnable telle quelle.
ORDRE_NIVEAUX = {niveau: rang for rang, niveau in enumerate(NiveauCriticite)}


def declencher_alertes(session, exposition, est_nouvelle: bool = True,
                        ancienne_criticite: int = None) -> list:
    """
    FR-25 - Point d'entree : declenche les alertes pour une exposition.

    Aucune alerte sous le palier niveau_alerte_minimum (configuration
    systeme). Une exposition deja connue n'alerte que si sa criticite a
    augmente d'au moins hausse_criticite_confirmation depuis
    ancienne_criticite : c'est l'alerte de CONFIRMATION.
    """
    from app.config_system import get_config_int, get_config_niveau

    niveau_minimum = get_config_niveau("niveau_alerte_minimum")
    if ORDRE_NIVEAUX[exposition.niveau_criticite] < ORDRE_NIVEAUX[niveau_minimum]:
        return []

    est_confirmation = False

    if not est_nouvelle:
        if ancienne_criticite is None:
            return []
        hausse_minimale = get_config_int("hausse_criticite_confirmation")
        if (exposition.criticite - ancienne_criticite) < hausse_minimale:
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