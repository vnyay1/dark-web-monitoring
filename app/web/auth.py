"""
FR-24 - Socle d'authentification Flask-Login.

Les ROUTES de connexion sont passees en JSON (app/web/api/auth.py) : ne
subsiste ici que ce dont Flask-Login a besoin pour reconnaitre une session,
c'est-a-dire le gestionnaire et le chargeur d'utilisateur.

`login_view` n'est volontairement PAS defini : il provoquerait une
redirection 302 vers une page de connexion qui n'existe plus cote serveur.
La couche API installe a la place un gestionnaire qui repond 401 en JSON,
que l'interface React traduit par un retour a l'ecran de connexion.
"""

from flask_login import LoginManager, UserMixin

from app.db import get_session
from app.models import User

login_manager = LoginManager()


class AuthenticatedUser(UserMixin):
    """Enveloppe Flask-Login autour du modele User SQLAlchemy."""

    def __init__(self, user: User):
        self.id = user.id
        self.nom_utilisateur = user.nom_utilisateur
        self.role = user.role  # necessaire au controle de privileges


@login_manager.user_loader
def load_user(user_id):
    """
    Recharge l'utilisateur a chaque requete, en verifiant qu'il est
    toujours ACTIF : desactiver un compte doit couper ses sessions en
    cours, pas seulement empecher les connexions futures.
    """
    session = get_session()
    user = session.query(User).filter_by(id=user_id, actif=True).first()
    session.close()
    return AuthenticatedUser(user) if user else None
