"""
Configuration de l'application, chargee depuis .env (python-dotenv).
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dark_web_monitoring.db")
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev_key_change_me")

    TOR_SOCKS_PROXY = os.getenv("TOR_SOCKS_PROXY", "socks5h://127.0.0.1:9050")
    TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT", 9051))
    TOR_CONTROL_PASSWORD = os.getenv("TOR_CONTROL_PASSWORD", "")