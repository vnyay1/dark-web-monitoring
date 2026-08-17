"""
Script CLI pour creer un compte analyste (FR-24).
Usage : python3 -m app.create_user
"""

import getpass
from werkzeug.security import generate_password_hash

from app.db import get_session, init_db
from app.models import User


def create_user():
    init_db()
    session = get_session()

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

    if len(mot_de_passe) < 8:
        print("[ERREUR] Le mot de passe doit faire au moins 8 caracteres.")
        return

    user = User(
        nom_utilisateur=nom_utilisateur,
        mot_de_passe_hash=generate_password_hash(mot_de_passe),
    )
    session.add(user)
    session.commit()

    print(f"[OK] Utilisateur '{nom_utilisateur}' cree avec succes.")
    session.close()


if __name__ == "__main__":
    create_user()