"""
FR-28 - Export des indicateurs d'exposition en JSON et CSV, et export de
conformite (expositions, journal d'audit, historique des roles).

Aucun export ne porte le texte conserve des annonces (SourceReference.
texte_brut, derogation CN-04/CN-05) : il n'est lisible que par son
endpoint dedie.
"""

import csv
import json
import io
import logging

from app import libelles
from app.db import get_session
from app.models import Exposition, HistoriqueRole, JournalAudit, Source, User, utc_now

logger = logging.getLogger(__name__)

# Un tableur (Excel, LibreOffice, Google Sheets) interprete comme FORMULE
# toute cellule commencant par l'un de ces caracteres. Or nom_entite provient
# du HTML scrape : c'est une chaine choisie par l'operateur du site de fuite.
# Une "victime" nommee =cmd|'/c calc'!A1 s'executerait donc a l'ouverture du
# CSV sur le poste de l'analyste.
CARACTERES_FORMULE = ("=", "+", "-", "@", "\t", "\r")


def _neutraliser_formule(valeur):
    """
    Prefixe d'une apostrophe une valeur que le tableur prendrait pour une
    formule. L'apostrophe n'est pas affichee dans la cellule : la lecture
    reste identique, seule l'evaluation est desamorcee.
    """
    if isinstance(valeur, str) and valeur.startswith(CARACTERES_FORMULE):
        return "'" + valeur
    return valeur


def _exposition_vers_dict(exposition) -> dict:
    """Convertit une Exposition en dictionnaire exportable (CN-03/CN-04 compatible)."""
    return {
        "id": exposition.id,
        "nom_entite": exposition.nom_entite,
        # Plusieurs categories possibles (FR-13) : jointes par " ; " pour
        # rester une seule colonne lisible dans un tableur.
        "categories": " ; ".join(c.nom for c in exposition.categories),
        "date_premiere_detection": exposition.date_premiere_detection.date().isoformat(),
        "date_derniere_detection": exposition.date_derniere_detection.date().isoformat(),
        "criticite": exposition.criticite,
        "niveau_criticite": exposition.niveau_criticite.value,
        "date_publication_source": (
            exposition.date_publication_source.date().isoformat()
            if exposition.date_publication_source else None
        ),
        "sources": ", ".join(sorted({
            sr.source.nom for sr in exposition.sources if sr.source is not None
        })),
        "statut": exposition.statut.value,
        "nb_sources": len(exposition.sources),
    }


def exporter_json() -> str:
    """FR-28 - Exporte toutes les expositions au format JSON (chaine)."""
    session = get_session()
    try:
        expositions = session.query(Exposition).all()
        data = [_exposition_vers_dict(e) for e in expositions]
    finally:
        # try/finally : une exception pendant la lecture des relations
        # laisserait autrement la session - donc la connexion - ouverte.
        session.close()

    return json.dumps(data, indent=2, ensure_ascii=False)


def exporter_conformite() -> str:
    """
    Export de conformite (super_admin), a faire AVANT une purge : c'est lui
    qui fait foi pour ce qui doit etre conserve. Il porte donc, en plus des
    expositions, le journal d'audit - file circulaire que la purge ampute
    aussi (cf. app.audit) - et l'historique des changements de role.
    """
    session = get_session()
    try:
        noms_sources = {s.id: s.nom for s in session.query(Source)}
        noms_comptes = {u.id: u.nom_utilisateur for u in session.query(User)}
        donnees = {
            "genere_le": utc_now().isoformat(),
            "expositions": [_exposition_vers_dict(e) for e in session.query(Exposition).all()],
            "journal_audit": [
                {
                    "horodatage": ligne.horodatage.isoformat(),
                    "resultat": ligne.resultat.value,
                    "source": noms_sources.get(ligne.source_id),
                    "details": ligne.details,
                }
                for ligne in session.query(JournalAudit).order_by(JournalAudit.horodatage)
            ],
            "historique_roles": [
                {
                    "date_modification": ligne.date_modification.isoformat(),
                    "compte": noms_comptes.get(ligne.user_cible_id, "(compte supprime)"),
                    "modifie_par": noms_comptes.get(ligne.modifie_par_id, "(compte supprime)"),
                    "ancien_role": ligne.ancien_role.value,
                    "nouveau_role": ligne.nouveau_role.value,
                }
                for ligne in session.query(HistoriqueRole).order_by(HistoriqueRole.date_modification)
            ],
        }
    finally:
        session.close()

    return json.dumps(donnees, indent=2, ensure_ascii=False)


def exporter_csv() -> str:
    """FR-28 - Exporte toutes les expositions au format CSV (chaine)."""
    session = get_session()
    try:
        expositions = session.query(Exposition).all()

        if not expositions:
            return ""

        output = io.StringIO()
        fieldnames = list(_exposition_vers_dict(expositions[0]).keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        # Le CSV s'ouvre dans un tableur, devant un lecteur humain : libelles
        # francais. Le JSON, format d'echange entre outils, garde les
        # identifiants techniques, stables et sans ambiguite.
        for e in expositions:
            ligne = _exposition_vers_dict(e)
            ligne["statut"] = libelles.libelle(libelles.STATUT, ligne["statut"])
            ligne["niveau_criticite"] = libelles.libelle(libelles.NIVEAU, ligne["niveau_criticite"])

            # Assainissement applique a TOUTES les colonnes, pas seulement a
            # nom_entite : les libelles de categories et de sources sont eux
            # aussi saisis a la main, et le champ le plus expose aujourd'hui
            # n'est pas forcement celui de demain.
            writer.writerow({c: _neutraliser_formule(v) for c, v in ligne.items()})

        return output.getvalue()
    finally:
        session.close()