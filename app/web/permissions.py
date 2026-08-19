"""
Gestion des privileges a 4 roles (consigne complementaire de l'encadrant,
en sus de FR-19 a FR-28 - ne remplace aucune fonctionnalite existante).

Definit les permissions par role et fournit un decorateur reutilisable
pour proteger les routes Flask selon le role requis.
"""

from functools import wraps
from flask import abort
from flask_login import current_user

from app.models import RoleUtilisateur


# Hierarchie des roles : chaque role herite des permissions des roles
# inferieurs (super_admin > admin > supervisor > user)
HIERARCHIE_ROLES = {
    RoleUtilisateur.USER: 0,
    RoleUtilisateur.SUPERVISOR: 1,
    RoleUtilisateur.ADMIN: 2,
    RoleUtilisateur.SUPER_ADMIN: 3,
}


def role_suffisant(role_utilisateur: RoleUtilisateur, role_requis: RoleUtilisateur) -> bool:
    """Verifie si le role de l'utilisateur est au moins egal au role requis."""
    return HIERARCHIE_ROLES.get(role_utilisateur, -1) >= HIERARCHIE_ROLES.get(role_requis, 99)


def role_requis(role_minimum: RoleUtilisateur):
    """
    Decorateur Flask - protege une route en exigeant un role minimum.
    Doit etre utilise APRES @login_required (l'utilisateur doit deja
    etre authentifie pour que current_user.role soit disponible).

    Usage :
        @app.route("/admin/users")
        @login_required
        @role_requis(RoleUtilisateur.ADMIN)
        def gestion_utilisateurs():
            ...
    """
    def decorateur(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)

            if not role_suffisant(current_user.role, role_minimum):
                abort(403)

            return f(*args, **kwargs)
        return wrapper
    return decorateur