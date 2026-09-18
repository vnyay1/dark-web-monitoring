"""
Acces au registre du crawl incremental (table entrees_collectees).

Toute l'ecriture du registre est isolee ici : le connecteur, lui, ne
touche jamais a la base. Le pipeline lui passe simplement l'ensemble des
identifiants deja traites en argument de collect().

ORDRE D'ECRITURE, IMPORTANT - une entree n'est marquee TRAITEE qu'APRES
avoir traverse le matching et la persistance. L'ordre inverse serait un
bug : CN-05 interdit de stocker le texte enrichi (seule derogation : celui
d'une entree qui a PRODUIT une exposition, cf. app.conservation), donc un
crash entre la recuperation de la page de detail et l'enregistrement de
l'Exposition perdrait definitivement la correspondance. Avec cet ordre, un crash se
traduit par un simple re-crawl au cycle suivant : l'operation est
idempotente.
"""

import logging
from datetime import timedelta

from app.models import EntreeCollectee, StatutDetailEntree, utc_now

logger = logging.getLogger(__name__)

# Une entree qui n'a plus ete vue depuis ce delai est oubliee : le registre
# est une file de travail, pas une archive (cf. docstring du modele).
RETENTION_JOURS = 90


def identifiants_traites(session, source_id) -> set:
    """
    Identifiants qui ne doivent plus consommer de budget : deja analyses,
    sans page de detail, ou definitivement abandonnes.

    A_TRAITER en est volontairement exclu : ce sont les entrees vues mais
    non encore servies par le budget, qui doivent etre reprises.
    """
    lignes = session.query(EntreeCollectee.identifiant_entree).filter(
        EntreeCollectee.source_id == source_id,
        EntreeCollectee.statut_detail.in_((
            StatutDetailEntree.TRAITEE,
            StatutDetailEntree.SANS_DETAIL,
            StatutDetailEntree.ECHEC,
        )),
    ).all()

    return {ligne[0] for ligne in lignes}


def identifiants_a_relire(session, source_id, candidats) -> set:
    """
    Parmi ces identifiants, ceux d'entrees deja analysees (TRAITEE ou
    SANS_DETAIL) qu'il faut relire pour completer leur exposition (cf.
    app.conservation, "completion"). Une entree abandonnee (ECHEC) n'est
    pas relue : sa page est cassee, la relire a chaque cycle userait le
    budget pour rien.
    """
    if not candidats:
        return set()
    lignes = session.query(EntreeCollectee.identifiant_entree).filter(
        EntreeCollectee.source_id == source_id,
        EntreeCollectee.identifiant_entree.in_(list(candidats)),
        EntreeCollectee.statut_detail.in_((
            StatutDetailEntree.TRAITEE,
            StatutDetailEntree.SANS_DETAIL,
        )),
    ).all()
    return {ligne[0] for ligne in lignes}


def enregistrer_entrees_vues(session, source_id, entrees) -> dict:
    """
    Cree les lignes manquantes et rafraichit date_derniere_vue des autres,
    en UN SEUL commit (sinon plusieurs centaines de commits SQLite par run).

    Une entree d'une source listing-only est creee directement en
    SANS_DETAIL : sans cela le budget la reproposerait a chaque cycle.

    Retourne {identifiant: EntreeCollectee}.
    """
    if not entrees:
        return {}

    identifiants = [e["identifiant_entree"] for e in entrees]

    existantes = {
        ligne.identifiant_entree: ligne
        for ligne in session.query(EntreeCollectee).filter(
            EntreeCollectee.source_id == source_id,
            EntreeCollectee.identifiant_entree.in_(identifiants),
        ).all()
    }

    maintenant = utc_now()
    for entree in entrees:
        identifiant = entree["identifiant_entree"]
        ligne = existantes.get(identifiant)

        if ligne is None:
            ligne = EntreeCollectee(
                source_id=source_id,
                identifiant_entree=identifiant,
                statut_detail=(
                    StatutDetailEntree.A_TRAITER if entree.get("a_page_detail")
                    else StatutDetailEntree.SANS_DETAIL
                ),
                date_premiere_vue=maintenant,
                date_derniere_vue=maintenant,
            )
            session.add(ligne)
            existantes[identifiant] = ligne
        else:
            ligne.date_derniere_vue = maintenant

    session.commit()
    return existantes


def marquer_traitee(session, source_id, identifiant, a_produit_exposition=False):
    """
    Marque une entree comme analysee. Appele MEME si l'entree n'a matche
    aucun selecteur : sinon les entrees non camerounaises - la grande
    majorite - resteraient eternellement A_TRAITER et le budget tournerait
    en rond sans jamais progresser.
    """
    ligne = _ligne(session, source_id, identifiant)
    if ligne is None:
        return

    ligne.statut_detail = StatutDetailEntree.TRAITEE
    ligne.date_detail_traite = utc_now()
    ligne.a_produit_exposition = bool(a_produit_exposition)


def marquer_echec_detail(session, source_id, identifiant, max_echecs=3):
    """
    Comptabilise un echec de recuperation de page de detail. Au-dela de
    max_echecs, l'entree est abandonnee : une page definitivement cassee
    consommerait sinon 30s de budget a chaque cycle, indefiniment.
    """
    ligne = _ligne(session, source_id, identifiant)
    if ligne is None:
        return

    ligne.nb_echecs_detail += 1
    if ligne.nb_echecs_detail >= max_echecs:
        ligne.statut_detail = StatutDetailEntree.ECHEC
        logger.warning(
            f"[registre] Entree abandonnee apres {ligne.nb_echecs_detail} echecs : "
            f"{identifiant}"
        )


def purger_registre(session, jours=RETENTION_JOURS) -> int:
    """
    Oublie les entrees qui n'ont plus ete vues depuis 'jours'. Une entree
    disparue du site puis reapparue plus tard sera simplement re-crawlee
    une fois.
    """
    seuil = utc_now() - timedelta(days=jours)
    supprimees = session.query(EntreeCollectee).filter(
        EntreeCollectee.date_derniere_vue < seuil
    ).delete(synchronize_session=False)
    session.commit()

    if supprimees:
        logger.info(f"[registre] {supprimees} entree(s) purgee(s) (> {jours} jours).")
    return supprimees


def reinitialiser_pour_recrawl(session, source_id=None) -> int:
    """
    Repasse les entrees TRAITEE en A_TRAITER pour forcer une nouvelle
    analyse.

    Consequence assumee de CN-05 : le texte enrichi n'existe qu'en memoire
    pendant le cycle qui l'a recupere. Quand le catalogue de selecteurs
    s'enrichit, les entrees deja crawlees ne sont donc PAS re-matchees
    automatiquement - cette fonction est le rattrapage.
    """
    requete = session.query(EntreeCollectee).filter(
        EntreeCollectee.statut_detail == StatutDetailEntree.TRAITEE
    )
    if source_id is not None:
        requete = requete.filter(EntreeCollectee.source_id == source_id)

    nombre = requete.update(
        {
            EntreeCollectee.statut_detail: StatutDetailEntree.A_TRAITER,
            EntreeCollectee.date_detail_traite: None,
        },
        synchronize_session=False,
    )
    session.commit()

    logger.info(f"[registre] {nombre} entree(s) remise(s) en file pour re-crawl.")
    return nombre


def remettre_en_file(session, source_id, identifiant) -> bool:
    """
    Remet UNE entree en file (A_TRAITER), quel que soit son statut, avec un
    compteur d'echecs remis a zero : sa page de detail sera recuperee et
    analysee au prochain cycle. Plus cible que reinitialiser_pour_recrawl(),
    qui remettrait en file toute une source - soit des centaines de pages a
    30 s ou plus chacune.

    Retourne False si l'entree est absente du registre.
    """
    ligne = _ligne(session, source_id, identifiant)
    if ligne is None:
        return False

    ligne.statut_detail = StatutDetailEntree.A_TRAITER
    ligne.date_detail_traite = None
    ligne.nb_echecs_detail = 0
    session.commit()

    logger.info(f"[registre] Entree remise en file : {identifiant}")
    return True


def _ligne(session, source_id, identifiant):
    return session.query(EntreeCollectee).filter_by(
        source_id=source_id, identifiant_entree=identifiant
    ).first()


def _analyser_arguments():
    import argparse

    parseur = argparse.ArgumentParser(
        description="Remet des entrees en file de crawl (a lancer apres un "
                    "enrichissement significatif du catalogue de selecteurs)."
    )
    parseur.add_argument("--source", help="SOURCE_NAME a re-crawler (defaut : toutes)")
    parseur.add_argument(
        "--identifiant",
        help="Ne remettre en file QUE cette entree (colonne Reference du signalement, "
             "ex. /news/cca-bank) ; exige --source",
    )
    return parseur.parse_args()


if __name__ == "__main__":
    from app.db import get_session
    from app.models import Source

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    arguments = _analyser_arguments()

    if arguments.identifiant and not arguments.source:
        raise SystemExit("--identifiant exige --source.")

    session = get_session()
    source_id = None

    if arguments.source:
        source = session.query(Source).filter_by(nom=arguments.source).first()
        if source is None:
            raise SystemExit(f"Source inconnue en base : {arguments.source}")
        source_id = source.id

    if arguments.identifiant:
        trouvee = remettre_en_file(session, source_id, arguments.identifiant.strip())
        session.close()
        if not trouvee:
            raise SystemExit(
                f"Entree {arguments.identifiant!r} absente du registre de {arguments.source}."
            )
        print(f"Entree {arguments.identifiant} remise en file de crawl pour {arguments.source}.")
        raise SystemExit(0)

    nombre = reinitialiser_pour_recrawl(session, source_id=source_id)
    session.close()

    print(f"{nombre} entree(s) remise(s) en file de crawl"
          f"{' pour ' + arguments.source if arguments.source else ''}.")
