"""
Politique de robustesse des mots de passe (FR-24).

Vit au niveau de l'application et non dans app/web/ : la regle est la meme
pour l'API et pour la creation de compte en ligne de commande
(app/create_user.py), qui ne passe par aucune couche web.
"""

import re

CARACTERES_SPECIAUX = r"!@#$%^&*()_+\-=\[\]{};':\"\|,.<>\/?~`"
# 12 caracteres plutot que 8 : a classe de caracteres egale, 8 reste a portee
# d'une attaque hors ligne si la base venait a etre copiee. La politique ne
# s'applique qu'a la CREATION d'un compte - les comptes existants ne sont pas
# invalides par ce changement.
LONGUEUR_MINIMALE = 12


def valider_mot_de_passe(mot_de_passe: str) -> tuple:
    """
    Verifie qu'un mot de passe respecte la politique de robustesse :
    - au moins 12 caracteres
    - au moins une majuscule
    - au moins une minuscule
    - au moins un chiffre
    - au moins un caractere special

    Retourne un tuple (valide: bool, message: str). Le message est vide si
    le mot de passe est valide, sinon il decrit la premiere regle non
    respectee.
    """
    if len(mot_de_passe) < LONGUEUR_MINIMALE:
        return False, f"Le mot de passe doit contenir au moins {LONGUEUR_MINIMALE} caracteres."

    if not re.search(r"[A-Z]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins une majuscule."

    if not re.search(r"[a-z]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins une minuscule."

    if not re.search(r"[0-9]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins un chiffre."

    if not re.search(f"[{re.escape(CARACTERES_SPECIAUX)}]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins un caractere special."

    return True, ""
