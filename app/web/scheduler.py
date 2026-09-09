"""
FR-07 - Supervision du scheduler de collecte : interface web et API.

Cette version PILOTE REELLEMENT le scheduler. La precedente maintenait un
dictionnaire `_SCHEDULER_STATE` en memoire du processus Flask, sans aucun
lien avec le processus de collecte : les boutons mutaient ce dictionnaire,
le flux SSE emettait un battement fictif toutes les 10 secondes, et la page
rejouait des logs ecrits en dur cote JavaScript. Rien de tout cela ne
refletait l'etat du systeme.

Tout l'etat transite desormais par la base (app.supervision), seul canal
commun entre le serveur web et le processus de collecte.

CHOIX DU SONDAGE PLUTOT QUE SSE - la console interroge
/api/evenements?depuis=<id> toutes les deux secondes. Un flux SSE aurait
immobilise un thread du serveur de developpement par onglet ouvert, et une
reconnexion aurait perdu les evenements emis entre-temps. Le curseur par
identifiant est repris exactement la ou il s'etait arrete, et se teste a la
main avec curl.
"""

import subprocess
import sys
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app import supervision
from app.models import RoleUtilisateur
from app.web.permissions import role_requis

scheduler_bp = Blueprint("scheduler", __name__, url_prefix="/scheduler")

# Racine du depot : le sous-processus doit demarrer la ou "app" est
# importable, quel que soit le repertoire courant du serveur web.
RACINE_PROJET = Path(__file__).resolve().parents[2]


# endpoint explicite : base.html reference url_for("scheduler.supervision"),
# le nom de la fonction ne peut pas servir (collision avec le module
# app.supervision importe plus haut).
@scheduler_bp.route("/", endpoint="supervision")
@scheduler_bp.route("/supervision", endpoint="supervision")
@login_required
def supervision_page():
    """Console de supervision du scheduler."""
    return render_template("scheduler_supervision.html")


@scheduler_bp.route("/api/etat", methods=["GET"])
@login_required
def etat():
    """Etat courant du scheduler, tel que publie par le processus de collecte."""
    return jsonify(supervision.etat_courant())


@scheduler_bp.route("/api/evenements", methods=["GET"])
@login_required
def evenements():
    """
    Evenements posterieurs a `depuis`. Sans parametre, la console demande
    le dernier identifiant connu pour suivre le direct sans rejouer
    l'historique.
    """
    depuis = request.args.get("depuis", type=int)

    if depuis is None:
        return jsonify({
            "evenements": [],
            "dernier_id": supervision.dernier_evenement_id(),
        })

    lignes = supervision.evenements_depuis(depuis, limite=request.args.get("limite", 100, type=int))

    return jsonify({
        "evenements": lignes,
        "dernier_id": lignes[-1]["id"] if lignes else depuis,
    })


@scheduler_bp.route("/api/demarrer", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def demarrer():
    """
    Lance le processus de collecte.

    Le verrou en base fait foi : on le consulte d'abord pour repondre
    proprement, mais c'est le processus lui-meme qui le reclame de facon
    atomique au demarrage. Deux clics simultanes ne peuvent donc pas
    aboutir a deux schedulers, meme si tous deux passent ce test.
    """
    etat_actuel = supervision.etat_courant()

    if etat_actuel["actif"]:
        return jsonify({
            "succes": False,
            "message": (
                f"Un scheduler est deja actif (pid {etat_actuel['pid']} "
                f"sur {etat_actuel['hostname']})."
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
        "message": "Scheduler demarre. Premiere collecte en cours.",
        "pid": processus.pid,
    })


@scheduler_bp.route("/api/arreter", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def arreter():
    """
    Arrete le processus de collecte par signal, puis libere le verrou.

    On n'attend pas la fin d'une collecte en cours : les connecteurs
    passent l'essentiel de leur temps a respecter le delai de FR-06, et un
    arret pendant cette attente ne laisse aucune ecriture a moitie faite
    (chaque entree est commitee individuellement).
    """
    etat_actuel = supervision.etat_courant()

    if not etat_actuel["actif"]:
        return jsonify({
            "succes": False,
            "message": "Aucun scheduler actif.",
        }), 409

    pid = etat_actuel["pid"]
    erreur_signal = None

    if pid:
        try:
            _terminer_processus(pid)
        except ProcessLookupError:
            pass  # deja disparu : le verrou reste a liberer
        except Exception as erreur:
            erreur_signal = str(erreur)

    # Le verrou est libere quoi qu'il arrive : un processus injoignable ne
    # doit pas laisser le systeme bloque pendant la peremption.
    supervision.liberer_verrou()

    if erreur_signal:
        return jsonify({
            "succes": True,
            "message": (
                f"Verrou libere, mais le signal d'arret a echoue ({erreur_signal}). "
                f"Verifiez le processus {pid} sur {etat_actuel['hostname']}."
            ),
        })

    return jsonify({"succes": True, "message": "Scheduler arrete."})


@scheduler_bp.route("/api/collecte-immediate", methods=["POST"])
@login_required
@role_requis(RoleUtilisateur.ADMIN)
def collecte_immediate():
    """Demande au scheduler actif de lancer un cycle sans attendre l'echeance."""
    etat_actuel = supervision.etat_courant()

    if not etat_actuel["actif"]:
        return jsonify({
            "succes": False,
            "message": "Aucun scheduler actif : demarrez-le d'abord.",
        }), 409

    if etat_actuel["statut"] == "collecte_en_cours":
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


def _terminer_processus(pid: int):
    """
    Envoie une demande d'arret propre au processus scheduler.

    Windows ne connait pas SIGTERM pour un processus tiers : on passe par
    taskkill, qui declenche la meme sortie propre.
    """
    import os

    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=True, capture_output=True,
        )
    else:
        import signal as signaux

        os.kill(pid, signaux.SIGTERM)
