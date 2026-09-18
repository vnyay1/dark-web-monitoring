"""
Limitation des tentatives de connexion (FR-24).

L'ecran de connexion etait la seule porte du systeme sans aucun frein : un
script pouvait essayer des mots de passe indefiniment, sans trace et sans
ralentissement. Le hachage PBKDF2 de Werkzeug rend chaque essai couteux,
mais pas assez pour tenir lieu de protection.

POURQUOI EN MEMOIRE ET NON EN BASE - le serveur web est un processus unique
(le scheduler, lui, tourne a part et ne sert aucune requete), donc un simple
dictionnaire suffit et evite d'ecrire en base a chaque echec de connexion.
Consequence assumee : un redemarrage de Flask remet les compteurs a zero.
C'est un frein contre l'automatisation, pas un verrou de comptabilite - la
trace durable, elle, vit dans JournalAudit (FR-17).

Aucune dependance nouvelle : `requirements.txt` ne doit lister que ce que le
code importe reellement.
"""

import threading
from datetime import timedelta

from app.models import utc_now

# 5 essais laissent la place aux fautes de frappe honnetes ; 15 minutes de
# blocage rendent une attaque par dictionnaire inexploitable sans gener
# durablement un analyste qui s'est trompe.
SEUIL_ECHECS = 5
DUREE_BLOCAGE = timedelta(minutes=15)

# Cle : (nom d'utilisateur en minuscules, adresse IP). Valeur : [nb_echecs,
# date du dernier echec]. Le nom est inclus pour qu'un poste partage ne
# bloque pas tous ses comptes d'un coup ; l'IP, pour qu'un attaquant ne
# puisse pas bloquer le compte d'un tiers depuis l'exterieur.
_tentatives = {}
_verrou = threading.Lock()


def _purger(maintenant):
    """
    Retire les entrees expirees. Appele a chaque acces : sans cela, le
    dictionnaire grossirait indefiniment au fil des noms essayes.
    """
    expirees = [
        cle for cle, (_, dernier_echec) in _tentatives.items()
        if maintenant - dernier_echec > DUREE_BLOCAGE
    ]
    for cle in expirees:
        del _tentatives[cle]


def _cle(nom_utilisateur: str, ip: str) -> tuple:
    return ((nom_utilisateur or "").strip().lower(), ip or "inconnue")


def est_bloque(nom_utilisateur: str, ip: str) -> int:
    """
    Retourne le nombre de secondes de blocage restantes, ou 0 si la
    tentative est autorisee.
    """
    maintenant = utc_now()
    with _verrou:
        _purger(maintenant)
        echecs, dernier_echec = _tentatives.get(_cle(nom_utilisateur, ip), (0, None))

        if echecs < SEUIL_ECHECS or dernier_echec is None:
            return 0

        restant = DUREE_BLOCAGE - (maintenant - dernier_echec)
        return max(0, int(restant.total_seconds()))


def enregistrer_echec(nom_utilisateur: str, ip: str) -> None:
    """Incremente le compteur d'echecs et repousse la fin du blocage."""
    maintenant = utc_now()
    with _verrou:
        _purger(maintenant)
        cle = _cle(nom_utilisateur, ip)
        echecs, _ = _tentatives.get(cle, (0, None))
        _tentatives[cle] = (echecs + 1, maintenant)


def reinitialiser(nom_utilisateur: str, ip: str) -> None:
    """Efface le compteur apres une connexion reussie."""
    with _verrou:
        _tentatives.pop(_cle(nom_utilisateur, ip), None)
