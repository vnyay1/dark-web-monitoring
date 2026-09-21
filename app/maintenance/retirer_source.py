"""
Retrait definitif d'une source surveillee et des donnees qui n'existent
que par elle.

A executer A LA MAIN. Par defaut l'outil SIMULE : il affiche ce qui serait
supprime sans rien toucher. Seul --confirmer ecrit en base, et seulement
apres un export JSON des expositions concernees.

PORTEE
  - signalements (SourceReference) de la source : par source_id, et, pour
    les signalements anterieurs a cette cle, par prefixe d'URL de la source ;
  - expositions qui n'ont PLUS AUCUN signalement apres ce retrait, avec
    leurs alertes (cascade du modele). Une exposition vue aussi sur une
    autre source est conservee, seul le signalement retire disparait ;
  - file du crawl incremental (EntreeCollectee) de la source.

CE QUI N'EST JAMAIS SUPPRIME
  - le journal d'audit : aucune ligne n'est supprimee par ce retrait
    (FR-17). Il s'elague seul par ancienneté (file circulaire, cf.
    app.audit) et la purge de conformite peut l'amputer, mais ce n'est
    jamais le retrait d'une source qui le decide ;
  - la ligne Source elle-meme. Source.audits porte cascade="all,
    delete-orphan" : supprimer la source par l'ORM effacerait son journal
    d'audit. Elle passe en actif=False et disparait de l'interface.

Usage :
    python3 -m app.maintenance.retirer_source --lister
    python3 -m app.maintenance.retirer_source thehackernews
    python3 -m app.maintenance.retirer_source thehackernews --confirmer
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import or_

from app.db import get_session
from app.models import (
    EntreeCollectee, EvenementCollecte, Exposition, JournalAudit, Source,
    SourceReference, utc_now,
)

logger = logging.getLogger(__name__)

RACINE_PROJET = Path(__file__).resolve().parents[2]
# Repertoire deja exclu du depot par .gitignore.
REPERTOIRE_EXPORTS = RACINE_PROJET / "exports"


def _noms_connecteurs_actifs() -> set:
    from app.connectors import connecteurs_actifs

    return {classe.SOURCE_NAME for classe in connecteurs_actifs()}


def lister():
    """Inventaire des sources, avec celles qu'aucun connecteur ne collecte plus."""
    session = get_session()
    try:
        actifs = _noms_connecteurs_actifs()
        sources = session.query(Source).order_by(Source.nom).all()

        print(f"\n{'Source':28} {'Etat':10} {'Signalements':>13} {'Audit':>7}  Connecteur")
        print("-" * 78)
        for source in sources:
            nb_refs = session.query(SourceReference).filter_by(source_id=source.id).count()
            nb_audit = session.query(JournalAudit).filter_by(source_id=source.id).count()
            connecteur = "oui" if source.nom in actifs else "AUCUN (orpheline)"
            etat = "active" if source.actif else "inactive"
            print(f"{source.nom:28} {etat:10} {nb_refs:>13} {nb_audit:>7}  {connecteur}")

        print(
            "\nUne source orpheline n'est plus collectee par aucun connecteur : "
            "elle peut etre retiree avec cet outil."
        )
    finally:
        session.close()


def _prefixe_url(source) -> str:
    """Schema + hote de l'URL de la source, pour les signalements sans source_id."""
    from urllib.parse import urlparse

    url = urlparse(source.url_ou_identifiant or "")
    if not url.scheme or not url.netloc:
        return None
    return f"{url.scheme}://{url.netloc}"


def _inventaire(session, source) -> dict:
    """Calcule, sans rien modifier, ce qu'implique le retrait."""
    conditions = [SourceReference.source_id == source.id]
    prefixe = _prefixe_url(source)
    if prefixe:
        conditions.append(
            (SourceReference.source_id.is_(None))
            & SourceReference.reference_source.like(f"{prefixe}%")
        )

    references = session.query(SourceReference).filter(or_(*conditions)).all()
    ids_references = {r.id for r in references}

    expositions_touchees = {r.exposition_id for r in references}
    a_supprimer, a_conserver = [], []

    for exposition_id in expositions_touchees:
        exposition = session.get(Exposition, exposition_id)
        if exposition is None:
            continue
        restantes = [sr for sr in exposition.sources if sr.id not in ids_references]
        (a_conserver if restantes else a_supprimer).append(exposition)

    return {
        "references": references,
        "expositions_supprimees": a_supprimer,
        "expositions_conservees": a_conserver,
        "entrees_crawl": session.query(EntreeCollectee).filter_by(source_id=source.id).count(),
        "audit": session.query(JournalAudit).filter_by(source_id=source.id).count(),
        "prefixe": prefixe,
    }


def _exporter(nom_source, inventaire) -> Path:
    """Sauvegarde JSON des expositions impactees, avant toute suppression."""
    from app.reports.export import _exposition_vers_dict

    REPERTOIRE_EXPORTS.mkdir(exist_ok=True)
    horodatage = utc_now().strftime("%Y%m%d_%H%M%S")
    chemin = REPERTOIRE_EXPORTS / f"retrait_{nom_source}_{horodatage}.json"

    donnees = {
        "source": nom_source,
        "genere_le": utc_now().isoformat(),
        "expositions_supprimees": [
            _exposition_vers_dict(e) for e in inventaire["expositions_supprimees"]
        ],
        "expositions_conservees_signalement_retire": [
            _exposition_vers_dict(e) for e in inventaire["expositions_conservees"]
        ],
        "signalements_retires": [
            {
                "exposition_id": r.exposition_id,
                "reference_source": r.reference_source,
                "date_publication": r.date_publication.isoformat() if r.date_publication else None,
            }
            for r in inventaire["references"]
        ],
    }

    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin


def retirer(nom_source: str, confirmer: bool) -> int:
    session = get_session()
    try:
        source = session.query(Source).filter_by(nom=nom_source).first()
        if source is None:
            print(f"Source inconnue : {nom_source!r}. Utilisez --lister.")
            return 1

        if nom_source in _noms_connecteurs_actifs():
            print(
                f"REFUS : {nom_source!r} est encore collectee par un connecteur actif. "
                f"Retirez d'abord le connecteur de app/connectors/__init__.py."
            )
            return 1

        inv = _inventaire(session, source)

        print(f"\nRetrait de la source {nom_source!r}")
        print("-" * 60)
        print(f"  Signalements a supprimer               : {len(inv['references'])}")
        if inv["prefixe"]:
            print(f"    (dont signalements sans source_id reperes par URL {inv['prefixe']})")
        print(f"  Expositions a supprimer (source seule) : {len(inv['expositions_supprimees'])}")
        print(f"  Expositions conservees (multi-sources) : {len(inv['expositions_conservees'])}")
        print(f"  Entrees de la file de crawl            : {inv['entrees_crawl']}")
        print(f"  Journal d'audit                        : {inv['audit']} ligne(s) CONSERVEE(S)")
        print(f"  Ligne Source                           : CONSERVEE, passee en inactive")

        for exposition in inv["expositions_supprimees"][:15]:
            print(f"    - {exposition.nom_entite}")
        if len(inv["expositions_supprimees"]) > 15:
            print(f"    ... et {len(inv['expositions_supprimees']) - 15} autre(s)")

        if not confirmer:
            print("\nSIMULATION : rien n'a ete modifie. Relancez avec --confirmer pour executer.")
            return 0

        chemin = _exporter(nom_source, inv)
        print(f"\nExport de sauvegarde : {chemin}")

        ids_expositions = [e.id for e in inv["expositions_supprimees"]]

        # Les evenements de supervision pointent vers les expositions : la
        # reference est videe plutot que l'evenement supprime, le fil
        # d'activite restant exact sur ce qui s'est passe.
        if ids_expositions:
            (session.query(EvenementCollecte)
             .filter(EvenementCollecte.exposition_id.in_(ids_expositions))
             .update({"exposition_id": None}, synchronize_session=False))

        for reference in inv["references"]:
            session.delete(reference)
        session.flush()

        for exposition in inv["expositions_supprimees"]:
            # Cascade du modele : alertes et signalements restants.
            session.delete(exposition)

        (session.query(EntreeCollectee)
         .filter_by(source_id=source.id)
         .delete(synchronize_session=False))

        source.actif = False
        session.commit()

        logger.warning(
            f"[maintenance] Source {nom_source!r} retiree : "
            f"{len(inv['references'])} signalement(s), "
            f"{len(ids_expositions)} exposition(s) supprimee(s). Export : {chemin}"
        )
        print("\nRetrait effectue.")
        return 0

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _analyser_arguments():
    parseur = argparse.ArgumentParser(
        description="Retire une source et les donnees qui n'existent que par elle."
    )
    parseur.add_argument("source", nargs="?", help="Nom de la source (Source.nom)")
    parseur.add_argument("--lister", action="store_true", help="Inventaire des sources")
    parseur.add_argument(
        "--confirmer", action="store_true",
        help="Execute reellement le retrait (sinon : simulation)",
    )
    return parseur.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    arguments = _analyser_arguments()

    if arguments.lister or not arguments.source:
        lister()
        sys.exit(0)

    sys.exit(retirer(arguments.source, arguments.confirmer))
