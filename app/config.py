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