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

    @app.context_processor
    def inject_alertes_count():
        from flask_login import current_user
        if current_user.is_authenticated:
            return {"nb_alertes_non_lues": compter_alertes_non_lues()}
        return {"nb_alertes_non_lues": 0}

    return app