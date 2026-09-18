"""
Configuration de l'application, chargee depuis .env (python-dotenv).
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

    TOR_SOCKS_PROXY = os.getenv("TOR_SOCKS_PROXY")
    TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT"))
    TOR_CONTROL_PASSWORD = os.getenv("TOR_CONTROL_PASSWORD")

    # Marque le cookie de session "Secure" (jamais transmis en clair). Le
    # deploiement actuel est en HTTP sur la VM : l'activer par defaut
    # empecherait toute connexion. C'est donc la SEULE variable a porter une
    # valeur par defaut, parce qu'elle durcit sans etre indispensable au
    # demarrage - a passer a true des qu'un reverse proxy TLS est en place.
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in (
        "1", "true", "oui",
    )