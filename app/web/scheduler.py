"""
Supervision du Scheduler de Collecte (FR-07) - Interface Web & Endpoints API.

Fournit :
1. La route d'affichage de la console de supervision (/scheduler)
2. Les endpoints API REST de contrôle (status, démarrer, arrêter, exécuter maintenant)
3. Le flux d'événements temps réel SSE (Server-Sent Events) pour le streaming des logs
"""

import time
import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, jsonify, Response, request
from flask_login import login_required

scheduler_bp = Blueprint("scheduler", __name__, url_prefix="/scheduler")

# État simulé en mémoire pour l'interface en l'absence de processus dédié
_SCHEDULER_STATE = {
    "actif": True,
    "statut": "actif",  # "actif" | "inactif" | "en_cours"
    "intervalle_heures": 6,
    "sources_actives": 7,
    "derniere_execution": "08:00 UTC",
    "prochaine_execution": "14:00 UTC",
}


@scheduler_bp.route("/")
@scheduler_bp.route("/supervision")
@login_required
def supervision():
    """Rendu de la page de supervision du scheduler."""
    return render_template("scheduler_supervision.html")


@scheduler_bp.route("/api/status", methods=["GET"])
@login_required
def get_status():
    """Contrat d'API - Statut actuel du scheduler."""
    return jsonify(_SCHEDULER_STATE)


@scheduler_bp.route("/api/demarrer", methods=["POST"])
@login_required
def demarrer():
    """Contrat d'API - Démarrage du scheduler."""
    _SCHEDULER_STATE["actif"] = True
    _SCHEDULER_STATE["statut"] = "actif"
    return jsonify({
        "succes": True,
        "message": "Processus scheduler démarré avec succès."
    })


@scheduler_bp.route("/api/arreter", methods=["POST"])
@login_required
def arreter():
    """Contrat d'API - Arrêt du scheduler."""
    _SCHEDULER_STATE["actif"] = False
    _SCHEDULER_STATE["statut"] = "inactif"
    return jsonify({
        "succes": True,
        "message": "Processus scheduler arrêté."
    })


@scheduler_bp.route("/api/executer-maintenant", methods=["POST"])
@login_required
def executer_maintenant():
    """Contrat d'API - Déclenchement d'une collecte manuelle immédiate."""
    _SCHEDULER_STATE["statut"] = "en_cours"
    return jsonify({
        "succes": True,
        "message": "Collecte immédiate déclenchée en tâche de fond."
    })


@scheduler_bp.route("/api/logs/stream", methods=["GET"])
@login_required
def stream_logs():
    """
    Contrat d'API - Flux Server-Sent Events (SSE) pour le streaming temps réel.
    Format de message émis : data: {"timestamp": "...", "level": "INFO", "message": "..."}\n\n
    """
    def event_generator():
        # Envoie un premier message d'état
        init_data = json.dumps({
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "level": "INFO",
            "message": "[scheduler] Connexion au flux de logs de supervision établie.",
            "statut": _SCHEDULER_STATE["statut"]
        })
        yield f"data: {init_data}\n\n"
        
        while True:
            time.sleep(10)
            if _SCHEDULER_STATE["actif"]:
                ping_data = json.dumps({
                    "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    "level": "INFO",
                    "message": "[scheduler] Heartbeat - boucle de surveillance active (veille FR-07).",
                    "statut": _SCHEDULER_STATE["statut"]
                })
                yield f"data: {ping_data}\n\n"

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
