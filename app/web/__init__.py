"""
Factory Flask - initialise l'application et enregistre les blueprints.
"""

from flask import Flask
from app.config import Config
from app.db import init_db
from app.web.reports import reports_bp
from app.web.users import users_bp

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.FLASK_SECRET_KEY

    # Durcissement du cookie de session. SameSite=Lax empeche qu'il soit
    # envoye lors d'une navigation declenchee par un site tiers, ce qui
    # constitue la premiere barriere CSRF ; la seconde est l'en-tete
    # X-Requested-With exige par la couche API.
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    init_db()

    from app.web.auth import auth_bp, login_manager
    from app.web.dashboard import dashboard_bp
    from app.web.expositions import expositions_bp
    from app.web.alerts import alerts_bp, compter_alertes_non_lues
    from app.web.audit import audit_bp
    from app.web.compliance import compliance_bp
    from app.web.settings import settings_bp
    from app.web.scheduler import scheduler_bp

    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(expositions_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(compliance_bp)
    app.register_blueprint(scheduler_bp)

    # Couche API JSON consommee par l'interface React. Montee APRES les
    # blueprints Jinja, dont elle prendra la place page par page.
    from app.web.api import enregistrer_api
    enregistrer_api(app)

    @app.context_processor
    def inject_alertes_count():
        from flask_login import current_user
        if current_user.is_authenticated:
            return {"nb_alertes_non_lues": compter_alertes_non_lues()}
        return {"nb_alertes_non_lues": 0}

    return app