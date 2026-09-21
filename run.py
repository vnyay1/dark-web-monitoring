"""
Point d'entree pour lancer l'application Flask en developpement.
"""

import os

from app.journalisation import configurer_journalisation
from app.web import create_app

# Console ET fichier (logs/web.log). Avant create_app() : les messages emis
# pendant la construction de l'application sont alors deja captes.
configurer_journalisation("web")

app = create_app()

if __name__ == "__main__":
    # debug=True activerait la console Werkzeug (execution de code arbitraire
    # dans le processus de l'application) et afficherait, a chaque erreur 500,
    # une trace contenant les variables locales - donc des fragments de page
    # collectee, ce qu'interdit CN-05. Jamais actif par defaut : il faut poser
    # FLASK_DEBUG explicitement, le temps d'une session de mise au point.
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "oui")
    app.run(debug=debug, host="127.0.0.1", port=5000)
