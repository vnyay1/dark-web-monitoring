"""
FR-17 - Point d'ecriture unique du journal d'audit (table journal_audit).

Le journal avait deux ecrivains independants qui instanciaient JournalAudit
et commitaient chacun de leur cote : la synthese de collecte
(BaseConnector._journaliser_synthese) et les tentatives de connexion
(app.web.api.auth). Toute regle transverse - le plafond ci-dessous - devait
donc etre ecrite deux fois. Tout ajout d'une ligne d'audit passe desormais
par journaliser().

PLAFOND (evolution demandee) - le journal est une FILE CIRCULAIRE de
LIMITE_JOURNAL entrees : au-dela, les plus anciennes sortent a l'ecriture de
la suivante. Il reste append-only pour l'application (aucune route ne modifie
ni ne supprime une ligne en particulier), mais ce n'est plus une archive de
duree illimitee. Deux consequences assumees :

  - une ligne ancienne finit par disparaitre. Ce qui doit etre conserve
    durablement est exporte AVANT (GET /compliance/export-complet).
  - la purge de conformite l'ampute aussi, sur sa date limite
    (purger_avant), la ou elle ne le touchait pas du tout.

L'elagage est fait a l'ecriture, et non par une tache de nettoyage a lancer
a la main : une tache oubliee laisserait le journal croitre indefiniment,
ce qui est precisement le probleme a resoudre.

CN-04 : ce module n'inspecte jamais le contenu de `details`. Ce sont les
appelants qui garantissent qu'il ne porte ni contenu de page ni donnee
personnelle.
"""

import logging

from sqlalchemy import func

from app.models import JournalAudit

logger = logging.getLogger(__name__)

# Taille maximale du journal, en nombre de lignes.
LIMITE_JOURNAL = 1000


def journaliser(session, lignes, commit: bool = True) -> int:
    """
    Ajoute des lignes au journal puis le ramene a LIMITE_JOURNAL entrees.
    Retourne le nombre de lignes evincees.

    session : l'appelant reste proprietaire de la session ET du verrou.
    Pendant une collecte parallele, l'ecriture doit se faire sous
    app.db.verrou_base (cf. BaseConnector._journaliser_synthese).

    lignes : un JournalAudit ou une sequence de JournalAudit.
    """
    if isinstance(lignes, JournalAudit):
        lignes = [lignes]

    session.add_all(lignes)
    # Flush avant le comptage : sans lui, les lignes qu'on vient d'ajouter ne
    # seraient pas vues par le count() et le journal depasserait le plafond
    # d'autant a chaque ecriture.
    session.flush()

    evincees = _elaguer(session)

    if commit:
        session.commit()
    return evincees


def _elaguer(session) -> int:
    """
    Supprime les entrees les plus anciennes au-dela de LIMITE_JOURNAL.

    Le tri est fait sur horodatage, jamais sur id : JournalAudit.id est un
    UUID, son ordre lexicographique n'a aucun rapport avec la chronologie.
    La suppression passe par une liste d'id explicite parce que SQLite
    n'accepte pas de LIMIT dans un DELETE.
    """
    total = session.query(func.count(JournalAudit.id)).scalar() or 0
    surplus = total - LIMITE_JOURNAL
    if surplus <= 0:
        return 0

    identifiants = [
        ligne[0] for ligne in session.query(JournalAudit.id)
        .order_by(JournalAudit.horodatage.asc(), JournalAudit.id.asc())
        .limit(surplus)
        .all()
    ]
    if not identifiants:
        return 0

    session.query(JournalAudit).filter(
        JournalAudit.id.in_(identifiants)
    ).delete(synchronize_session=False)

    logger.info(
        f"[audit] Journal ramene a {LIMITE_JOURNAL} entrees : "
        f"{len(identifiants)} ligne(s) la plus ancienne evincee(s)."
    )
    return len(identifiants)


def purger_avant(session, date_limite, commit: bool = True) -> int:
    """
    Purge de conformite : supprime les entrees anterieures a date_limite.
    Retourne le nombre de lignes supprimees.

    Meme critere de date que la purge des expositions, pour qu'une purge de
    conformite ne laisse pas derriere elle un journal decrivant les collectes
    dont les resultats viennent d'etre effaces.
    """
    supprimees = session.query(JournalAudit).filter(
        JournalAudit.horodatage < date_limite
    ).delete(synchronize_session=False)

    if commit:
        session.commit()

    if supprimees:
        logger.warning(
            f"[audit] PURGE : {supprimees} entree(s) de journal anterieure(s) "
            f"a {date_limite} supprimee(s)."
        )
    return supprimees


def compter_avant(session, date_limite) -> int:
    """Nombre d'entrees qu'une purge a cette date limite supprimerait."""
    return session.query(func.count(JournalAudit.id)).filter(
        JournalAudit.horodatage < date_limite
    ).scalar() or 0
