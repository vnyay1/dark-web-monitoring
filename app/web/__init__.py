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

    from app.web.auth import auth_bp, login_manager
    from app.web.dashboard import dashboard_bp
    from app.web.expositions import expositions_bp

    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(expositions_bp)

    return app