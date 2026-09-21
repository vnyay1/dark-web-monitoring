"""
FR-07 - Pilotage et supervision du scheduler de collecte.

Le sondage par curseur (?depuis=<id>) est prefere a un flux SSE : ce
dernier immobiliserait un thread du serveur de developpement par onglet
ouvert, et perdrait les evenements emis pendant une reconnexion. Le curseur
reprend exactement la ou il s'etait arrete.
"""

import logging
import subprocess
import sys
from pathlib import Path

from flask import jsonify, request
from flask_login import login_required

from app import supervision
from app.models import RoleUtilisateur
from app.web.permissions import role_requis

logger = logging.getLogger(__name__)

# Racine du depot : le sous-processus doit demarrer la ou "app" est
# importable, quel que soit le repertoire courant du serveur web.
RACINE_PROJET = Path(__file__).resolve().parents[3]


def _fichier_erreurs_scheduler():
    """
    Fichier ouvert en ajout ou le sous-processus scheduler deverse stderr,
    ou None si le repertoire n'est pas ecrivable (le lancement se fait alors
    sans, plutot que d'echouer). Le parent le referme aussitot apres Popen :
    le descripteur duplique dans l'enfant lui survit.
    """
    from app.journalisation import repertoire_journaux

    try:
        repertoire = repertoire_journaux()
        repertoire.mkdir(parents=True, exist_ok=True)
        return open(repertoire / "scheduler.err.log", "a", encoding="utf-8")
    except OSError:
        logger.warning(
            "[scheduler] Journal d'erreurs indisponible : stderr du "
            "sous-processus sera perdu.", exc_info=True,
        )
        return None


def _terminer_processus(pid: int):
    """
    Demande l'arret du processus scheduler.

    Windows ne permet pas d'envoyer SIGTERM a un processus tiers : on passe
    par taskkill, qui aboutit au meme arret.
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=True, capture_output=True,
        )
    else:
        import os
        import signal as signaux

        os.kill(pid, signaux.SIGTERM)


def enregistrer(api_bp):

    @api_bp.route("/scheduler/etat", methods=["GET"])
    @login_required
    def etat_scheduler():
        return jsonify(supervision.etat_courant())

    @api_bp.route("/scheduler/evenements", methods=["GET"])
    @login_required
    def evenements_scheduler():
        # Au (re)chargement de la page : evenements du cycle en cours ou du
        # dernier cycle, et le curseur a partir duquel suivre le direct. Les
        # evenements etant stockes en base, quitter la page ne perd rien.
        if request.args.get("historique") == "cycle":
            historique = supervision.evenements_du_dernier_cycle()
            lignes = historique["evenements"]
            return jsonify({
                "evenements": lignes,
                "tronque": historique["tronque"],
                "dernier_id": lignes[-1]["id"] if lignes else supervision.dernier_evenement_id(),
            })

        depuis = request.args.get("depuis", type=int)

        # Sans curseur, seulement la position courante du fil.
        if depuis is None:
            return jsonify({
                "evenements": [],
                "dernier_id": supervision.dernier_evenement_id(),
            })

        lignes = supervision.evenements_depuis(
            depuis, limite=request.args.get("limite", 100, type=int)
        )

        return jsonify({
            "evenements": lignes,
            "dernier_id": lignes[-1]["id"] if lignes else depuis,
        })

    @api_bp.route("/scheduler/demarrer", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def demarrer_scheduler():
        """
        Lance le processus de collecte.

        Ce test prealable sert a repondre proprement ; c'est le processus
        lui-meme qui reclame le verrou de facon atomique au demarrage. Deux
        clics simultanes ne peuvent donc pas produire deux schedulers, meme
        si tous deux franchissent ce test.
        """
        etat = supervision.etat_courant()

        if etat["actif"]:
            return jsonify({
                "succes": False,
                "message": (
                    f"Un scheduler est deja actif (pid {etat['pid']} "
                    f"sur {etat['hostname']})."
                ),
            }), 409

        # stdout part dans DEVNULL : le processus installe son propre
        # RotatingFileHandler (logs/scheduler.log, cf. app.journalisation) et
        # les deux feraient double emploi. stderr, lui, est redirige vers un
        # fichier : une trace d'exception qui tue le processus AVANT
        # l'installation du handler - import manquant, .env incomplet,
        # migration en retard - n'apparaitrait nulle part autrement, et le
        # scheduler semblerait "ne pas demarrer" sans explication.
        erreurs = _fichier_erreurs_scheduler()
        try:
            processus = subprocess.Popen(
                [sys.executable, "-m", "app.scheduler"],
                cwd=str(RACINE_PROJET),
                stdout=subprocess.DEVNULL,
                stderr=erreurs or subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            # Le message d'exception de Popen porte le chemin de
            # l'interpreteur et la ligne de commande complete : utile dans le
            # journal serveur, pas dans une reponse HTTP.
            logger.exception("[scheduler] Echec du lancement du processus.")
            return jsonify({
                "succes": False,
                "message": (
                    "Impossible de lancer le scheduler. Consultez le journal "
                    "du serveur pour le detail."
                ),
            }), 500
        finally:
            # Le descripteur a ete duplique dans l'enfant, qui continue d'y
            # ecrire : le garder ouvert ici ne ferait que fuiter.
            if erreurs is not None:
                erreurs.close()

        return jsonify({
            "succes": True,
            "message": "Scheduler demarre, premiere collecte en cours.",
            "pid": processus.pid,
        })

    @api_bp.route("/scheduler/arreter", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def arreter_scheduler():
        etat = supervision.etat_courant()

        if not etat["actif"]:
            return jsonify({"succes": False, "message": "Aucun scheduler actif."}), 409

        arret_echoue = False
        if etat["pid"]:
            try:
                _terminer_processus(etat["pid"])
            except ProcessLookupError:
                pass  # deja disparu : reste a liberer le verrou
            except Exception:
                logger.exception("[scheduler] Echec de l'arret du processus.")
                arret_echoue = True

        # Le verrou est libere quoi qu'il arrive : un processus injoignable
        # ne doit pas bloquer le systeme jusqu'a la peremption.
        supervision.liberer_verrou()

        if arret_echoue:
            # pid et hostname restent affiches : ce sont les informations dont
            # l'administrateur a besoin pour terminer le processus a la main.
            # Seul le message d'exception brut disparait.
            return jsonify({
                "succes": True,
                "message": (
                    f"Verrou libere, mais l'arret du processus a echoue. "
                    f"Verifiez le pid {etat['pid']} sur {etat['hostname']}."
                ),
            })

        return jsonify({"succes": True, "message": "Scheduler arrete."})

    @api_bp.route("/scheduler/verifier-ip", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def verifier_ip():
        """
        Demande au scheduler de verifier l'IP de sortie Tor. Le serveur web
        ne parle jamais a Tor lui-meme : sans scheduler actif, il n'y a pas
        de circuit a verifier.
        """
        if not supervision.demander_verification_ip():
            return jsonify({
                "succes": False,
                "message": "Aucun scheduler actif : pas de circuit Tor a verifier.",
            }), 409

        return jsonify({
            "succes": True,
            "message": "Verification demandee, resultat dans quelques secondes.",
        })

    @api_bp.route("/scheduler/collecte-immediate", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.ADMIN)
    def collecte_immediate():
        etat = supervision.etat_courant()

        if not etat["actif"]:
            return jsonify({
                "succes": False,
                "message": "Aucun scheduler actif : demarrez-le d'abord.",
            }), 409

        if etat["statut"] == "collecte_en_cours":
            return jsonify({
                "succes": False,
                "message": "Une collecte est deja en cours.",
            }), 409

        if not supervision.demander_collecte_immediate():
            return jsonify({
                "succes": False,
                "message": "Le scheduler ne repond plus.",
            }), 409

        return jsonify({
            "succes": True,
            "message": "Collecte immediate demandee, elle demarre dans quelques secondes.",
        })
