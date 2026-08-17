
"""
FR-25/FR-26 - Interface generique des "senders" d'alertes.

Chaque canal (email, SMS, WhatsApp) implemente cette interface. Pour le
moment, tous les senders sont des MOCKS (simulation en log, aucun envoi
reel) en attendant que les cles API de l'ANTIC soient disponibles.
Remplacer uniquement le corps de send() dans chaque classe concrete pour
brancher le vrai fournisseur, sans toucher au reste du systeme d'alerte.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseSender(ABC):
    """Interface commune a tous les canaux d'alerte."""

    CANAL_NOM = "unknown"

    @abstractmethod
    def send(self, destinataire: str, sujet: str, message: str) -> bool:
        """
        Envoie l'alerte. Retourne True si succes, False si echec.
        Ne doit JAMAIS lever d'exception - toute erreur doit etre
        capturee et journalisee, pour ne pas interrompre le traitement
        des autres canaux/alertes.
        """
        raise NotImplementedError


class MockEmailSender(BaseSender):
    """
    Sender EMAIL simule (mock). A remplacer par une vraie integration
    SMTP/SendGrid/etc. une fois les identifiants ANTIC disponibles.
    """
    CANAL_NOM = "email"

    def send(self, destinataire: str, sujet: str, message: str) -> bool:
        logger.info(
            f"[MOCK EMAIL] A: {destinataire} | Sujet: {sujet} | "
            f"Message: {message[:100]}..."
        )
        return True


class MockSmsSender(BaseSender):
    """
    Sender SMS simule (mock). A remplacer par une vraie integration
    (Twilio ou autre) une fois les identifiants ANTIC disponibles.
    """
    CANAL_NOM = "sms"

    def send(self, destinataire: str, sujet: str, message: str) -> bool:
        logger.info(f"[MOCK SMS] A: {destinataire} | Message: {message[:100]}...")
        return True


class MockWhatsAppSender(BaseSender):
    """
    Sender WhatsApp simule (mock). A remplacer par une vraie integration
    (Twilio WhatsApp Business API ou autre) une fois les identifiants
    ANTIC disponibles.
    """
    CANAL_NOM = "whatsapp"

    def send(self, destinataire: str, sujet: str, message: str) -> bool:
        logger.info(f"[MOCK WHATSAPP] A: {destinataire} | Message: {message[:100]}...")
        return True


# Registre des senders actifs - un seul point de bascule pour passer
# des mocks aux vraies implementations une fois les cles API disponibles
SENDERS = {
    "email": MockEmailSender(),
    "sms": MockSmsSender(),
    "whatsapp": MockWhatsAppSender(),
}