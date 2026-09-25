"""
Journalisation sur fichier des processus de longue duree.

L'application n'ecrivait aucun fichier : logging.basicConfig() etait appele
sans filename, donc tout partait sur la console. Le scheduler lance depuis
l'interface, lui, est un subprocess dont la sortie allait dans DEVNULL - ses
journaux n'existaient nulle part, et un incident de collecte n'etait
diagnosticable qu'en relancant la collecte a la main.

A NE PAS CONFONDRE avec le fil d'activite de la page Collecte : celui-la vit
en base (EvenementCollecte, cf. app.supervision), et c'est lui que le bouton
« Vider les logs » de l'interface supprime. Ni ce bouton, ni aucune route,
ne touche au fichier ecrit ici.

CN-04/CN-05 - ce fichier recoit les memes messages que la console, et les
messages du projet ne contiennent ni contenu de page ni donnee personnelle
(les connecteurs ne journalisent que des compteurs et des libelles
d'exception tronques). Le repertoire est neanmoins ignore par git
(.gitignore : logs/, *.log) et ne doit jamais etre versionne ni sorti de la
VM de collecte.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Racine du projet : app/journalisation.py -> app/ -> racine.
RACINE_PROJET = Path(__file__).resolve().parents[1]

FORMAT = "%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s - %(message)s"

# 5 Mo par fichier, 5 archives : environ 25 Mo au total, soit plusieurs mois
# de cycles quotidiens. Une rotation par TAILLE et non par date : un cycle de
# collecte ecrit beaucoup en quelques heures puis plus rien de la journee.
TAILLE_MAX_OCTETS = 5 * 1024 * 1024
NOMBRE_ARCHIVES = 5


def repertoire_journaux() -> Path:
    """
    Repertoire des journaux : $SENTINEL_LOG_DIR, sinon <racine>/logs.

    Volontairement HORS app/config.py : ce module-la lit ses variables sans
    valeur de repli et leve a l'import quand l'une manque. Un chemin de
    journaux ne doit jamais empecher l'application de demarrer.
    """
    return Path(os.getenv("SENTINEL_LOG_DIR") or (RACINE_PROJET / "logs"))


def configurer_journalisation(nom: str, niveau=logging.INFO):
    """
    Installe un RotatingFileHandler (<repertoire>/<nom>.log) EN PLUS de la
    sortie console, sur le logger racine. Retourne le chemin du fichier, ou
    None si le fichier n'a pas pu etre ouvert (repertoire en lecture seule,
    disque plein) : dans ce cas la console reste en place et le processus
    demarre quand meme.

    Idempotent : deux appels n'empilent pas deux handlers sur le meme fichier.
    """
    racine = logging.getLogger()
    racine.setLevel(niveau)

    if not any(isinstance(h, logging.StreamHandler)
               and not isinstance(h, logging.FileHandler)
               for h in racine.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(FORMAT))
        racine.addHandler(console)

    chemin = repertoire_journaux() / f"{nom}.log"

    for handler in racine.handlers:
        if isinstance(handler, RotatingFileHandler) and \
                Path(handler.baseFilename) == chemin.resolve():
            return chemin

    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fichier = RotatingFileHandler(
            chemin, maxBytes=TAILLE_MAX_OCTETS, backupCount=NOMBRE_ARCHIVES,
            encoding="utf-8",
        )
    except OSError:
        racine.warning(
            f"[journalisation] Journal sur fichier indisponible ({chemin}) : "
            f"la sortie console reste seule.", exc_info=True,
        )
        return None

    fichier.setFormatter(logging.Formatter(FORMAT))
    racine.addHandler(fichier)
    racine.info(f"[journalisation] Journal : {chemin}")
    return chemin
