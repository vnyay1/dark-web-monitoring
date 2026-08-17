"""
FR-24 - Authentification des analystes via Flask-Login.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from app.db import get_session
from app.models import User

auth_bp = Blueprint("auth", __name__)
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour acceder a cette page."
login_manager.login_message_category = "error"


class AuthenticatedUser(UserMixin):
    """Wrapper Flask-Login autour du modele User SQLAlchemy."""

    def __init__(self, user: User):
        self.id = user.id
        self.nom_utilisateur = user.nom_utilisateur


@login_manager.user_loader
def load_user(user_id):
    session = get_session()
    user = session.query(User).filter_by(id=user_id, actif=True).first()
    session.close()
    return AuthenticatedUser(user) if user else None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        nom_utilisateur = request.form.get("nom_utilisateur", "").strip()
        mot_de_passe = request.form.get("mot_de_passe", "")

        session = get_session()
        user = session.query(User).filter_by(
            nom_utilisateur=nom_utilisateur, actif=True
        ).first()
        session.close()

        if user and check_password_hash(user.mot_de_passe_hash, mot_de_passe):
            login_user(AuthenticatedUser(user))
            flash(f"Bienvenue, {user.nom_utilisateur}.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard.index"))

        flash("Identifiants incorrects.", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Vous avez ete deconnecte.", "success")
    return redirect(url_for("auth.login"))