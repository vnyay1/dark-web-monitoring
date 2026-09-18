"""
Version du code EXECUTE par un processus, comparee a celle du code INSTALLE.

POURQUOI - le serveur web et le scheduler sont des processus de longue
duree : ils gardent en memoire le code charge a leur demarrage. Apres un
`git pull`, tant qu'ils ne sont pas relances, ils executent l'ANCIENNE
version, sans rien en laisser paraitre : un nouveau reglage n'apparait pas,
une nouvelle section reste vide, la collecte suit l'ancienne logique. Cela
s'est produit sur la VM.

Chaque processus fige donc sa version au demarrage (VERSION_AU_DEMARRAGE) ;
l'interface la compare a celle du depot sur le disque (version_du_code) et
previent l'administrateur quand un redemarrage manque.

La version est le commit courant, lu directement dans .git : pas de
dependance a l'executable git, et rien a maintenir a la main. Hors depot
git, elle vaut None et aucune comparaison n'est faite.
"""

from pathlib import Path

RACINE_PROJET = Path(__file__).resolve().parents[1]
LONGUEUR_VERSION = 7


def _lire_ref(depot: Path, ref: str):
    """Commit d'une reference (refs/heads/main...), fichier ou packed-refs."""
    fichier = depot / ref
    if fichier.is_file():
        return fichier.read_text(encoding="utf-8").strip()

    empaquetees = depot / "packed-refs"
    if empaquetees.is_file():
        for ligne in empaquetees.read_text(encoding="utf-8").splitlines():
            parties = ligne.strip().split(" ", 1)
            if len(parties) == 2 and parties[1] == ref:
                return parties[0]
    return None


def version_du_code(racine: Path = RACINE_PROJET):
    """Commit courant du depot sur le disque (7 caracteres), ou None."""
    depot = racine / ".git"
    try:
        tete = (depot / "HEAD").read_text(encoding="utf-8").strip()
        commit = _lire_ref(depot, tete[5:]) if tete.startswith("ref: ") else tete
    except OSError:
        return None
    return commit[:LONGUEUR_VERSION] if commit else None


# Version du code charge par CE processus, figee a son demarrage.
VERSION_AU_DEMARRAGE = version_du_code()
