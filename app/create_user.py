"""
Script CLI pour creer un compte analyste (FR-24).

Usage :
    python3 -m app.create_user                      # compte "user"
    python3 -m app.create_user --role super_admin   # premier compte d'une installation

Le role est le seul moyen de creer le PREMIER administrateur : l'interface
ne permet de creer des comptes qu'a un admin deja connecte.
"""

import argparse
import getpass

from werkzeug.security import generate_password_hash

from app.db import get_session, init_db
from app.models import RoleUtilisateur, User
from app.securite import valider_mot_de_passe


def create_user(role: RoleUtilisateur = RoleUtilisateur.USER):
    init_db()
    session = get_session()
    try:
        nom_utilisateur = input("Nom d'utilisateur : ").strip()

        if not nom_utilisateur:
            print("[ERREUR] Le nom d'utilisateur ne peut pas etre vide.")
            return

        existing = session.query(User).filter_by(nom_utilisateur=nom_utilisateur).first()
        if existing:
            print(f"[ERREUR] L'utilisateur '{nom_utilisateur}' existe deja.")
            return

        mot_de_passe = getpass.getpass("Mot de passe : ")
        confirmation = getpass.getpass("Confirmer le mot de passe : ")

        if mot_de_passe != confirmation:
            print("[ERREUR] Les mots de passe ne correspondent pas.")
            return

        mot_de_passe_valide, message_erreur = valider_mot_de_passe(mot_de_passe)
        if not mot_de_passe_valide:
            print(f"[ERREUR] {message_erreur}")
            return

        user = User(
            nom_utilisateur=nom_utilisateur,
            mot_de_passe_hash=generate_password_hash(mot_de_passe),
            role=role,
        )
        session.add(user)
        session.commit()

        print(f"[OK] Utilisateur '{nom_utilisateur}' cree avec succes (role {role.value}).")
    finally:
        session.close()


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description="Cree un compte analyste (FR-24).")
    parseur.add_argument(
        "--role", default=RoleUtilisateur.USER.value,
        choices=[r.value for r in RoleUtilisateur],
        help="Role du compte (defaut : user).",
    )
    create_user(RoleUtilisateur(parseur.parse_args().role))
