"""
Libelles francais des valeurs metier, pour tout ce qui est produit cote
serveur a destination d'un lecteur humain (rapport mensuel, export CSV).

Les modeles stockent des identifiants techniques ("under_review",
"donnees_personnelles") qui ne doivent jamais apparaitre tels quels dans un
document remis a l'encadrement. L'interface React tient la meme table de
son cote (frontend/src/components/communs.jsx) : toute valeur ajoutee ici
doit l'etre la-bas aussi.
"""

CATEGORIE = {
    "credentials": "Identifiants",
    "donnees_personnelles": "Données personnelles",
    "donnees_financieres": "Données financières",
    "donnees_sante": "Données de santé",
    "documents_internes": "Documents internes",
    "code_source": "Code source",
    "non_precisee": "Non précisée",
}

STATUT = {
    "new": "Nouvelle",
    "under_review": "En cours d'analyse",
    "confirmed": "Confirmée",
    "false_positive": "Faux positif",
    "notified": "Notifiée",
    "closed": "Clôturée",
}

NIVEAU = {
    "critique": "Critique",
    "elevee": "Élevée",
    "moyenne": "Moyenne",
    "faible": "Faible",
}

TYPE_SOURCE = {
    "ransomware_site": "Site de rançongiciel",
    "paste": "Service de paste",
    "forum": "Forum",
    "telegram": "Telegram",
    "test_clairnet": "Test (clairnet)",
}

MOIS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def libelle(table: dict, valeur) -> str:
    """Libelle d'une valeur (enum ou chaine), la valeur brute a defaut."""
    cle = getattr(valeur, "value", valeur)
    return table.get(cle, cle)


def periode(mois: int, annee: int) -> str:
    """"Septembre 2026"."""
    return f"{MOIS[mois - 1].capitalize()} {annee}"
