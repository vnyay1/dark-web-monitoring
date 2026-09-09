"""
FR-07 - Pilotage et supervision du scheduler de collecte.

Le sondage par curseur (?depuis=<id>) est prefere a un flux SSE : ce
dernier immobiliserait un thread du serveur de developpement par onglet
ouvert, et perdrait les evenements emis pendant une reconnexion. Le curseur
reprend exactement la ou il s'etait arrete.
"""

import subprocess
import sys
from pathlib import Path

from flask import jsonify, request
from flask_login import login_required

from app import supervision
from app.models import RoleUtilisateur
from app.web.permissions import role_requis

# Racine du depot : le sous-processus doit demarrer la ou "app" est
# importable, quel que soit le repertoire courant du serveur web.
RACINE_PROJET = Path(__file__).resolve().parents[3]


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
        depuis = request.args.get("depuis", type=int)

        # Sans curseur, la console demande seulement ou en est le fil, pour
        # suivre le direct sans rejouer tout l'historique.
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

        try:
            processus = subprocess.Popen(
                [sys.executable, "-m", "app.scheduler"],
                cwd=str(RACINE_PROJET),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as erreur:
            return jsonify({
                "succes": False,
                "message": f"Impossible de lancer le scheduler : {erreur}",
            }), 500

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

        erreur_signal = None
        if etat["pid"]:
            try:
                _terminer_processus(etat["pid"])
            except ProcessLookupError:
                pass  # deja disparu : reste a liberer le verrou
            except Exception as erreur:
                erreur_signal = str(erreur)

        # Le verrou est libere quoi qu'il arrive : un processus injoignable
        # ne doit pas bloquer le systeme jusqu'a la peremption.
        supervision.liberer_verrou()

        if erreur_signal:
            return jsonify({
                "succes": True,
                "message": (
                    f"Verrou libere, mais l'arret du processus a echoue "
                    f"({erreur_signal}). Verifiez le pid {etat['pid']} sur "
                    f"{etat['hostname']}."
                ),
            })

        return jsonify({"succes": True, "message": "Scheduler arrete."})

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
