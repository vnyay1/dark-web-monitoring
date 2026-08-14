"""
Factory Flask - initialise l'application et enregistre les blueprints.
"""

from flask import Flask
from app.config import Config
from app.db import init_db


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.FLASK_SECRET_KEY

    init_db()

    from app.web.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    return app