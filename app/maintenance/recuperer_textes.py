"""
Rattrapage du texte des annonces et de leurs selecteurs (cf. app.conservation).

Un signalement n'a ni texte conserve ni selecteurs enregistres quand son
annonce a ete analysee avant ces fonctions. La collecte le complete
d'elle-meme, dans le budget de pages de detail de chaque cycle et tant que
l'annonce figure dans les pages de listing parcourues. Cet outil fait la
meme chose A LA DEMANDE, sans budget ni arret de pagination sur la
periode : il relit ces annonces sur leur source comme une collecte
(BaseConnector.collect : listing puis page de detail, delai FR-06, journal
d'audit).

Pour chaque annonce retrouvee, il :
  - conserve son texte complet, masque, et ses selecteurs sur le signalement ;
  - relance la chaine d'analyse (matching, faux positifs, criticite) et
    remonte la criticite et les categories de l'exposition si elles ont
    augmente - jamais a la baisse, comme en collecte - avec l'alerte de
    confirmation correspondante ;
  - la marque TRAITEE dans le registre du crawl (une annonce remise en file
    ne sera pas relue une seconde fois au cycle suivant).

La fenetre d'analyse (periode_collecte_jours) ne s'applique PAS : il s'agit
de completer des expositions deja enregistrees, pas d'en detecter de
nouvelles. Aucune exposition n'est creee, aucune n'est rattachee par son nom.

LIMITES
  - une annonce retiree du site, ou reculee au-dela des pages parcourues
    (pages_listing_max), n'est pas retrouvee : elle est signalee ;
  - orion_leaks et cmd_organization n'ont pas de reference propre a chaque
    annonce : leurs textes sont conserves par la collecte, au prochain cycle
    ou l'annonce est encore listee dans la periode ;
  - le scheduler doit etre ARRETE (deux processus ne partagent pas leur
    delai FR-06) : l'outil refuse de demarrer sinon.

A executer A LA MAIN. Par defaut l'outil SIMULE : il liste ce qu'il relirait
et le temps a prevoir, sans rien demander aux sources. Seul --confirmer lance
la relecture.

Usage :
    python3 -m app.maintenance.recuperer_textes
    python3 -m app.maintenance.recuperer_textes --source everest --confirmer
    python3 -m app.maintenance.recuperer_textes --source everest --tous --confirmer
"""

import argparse
import logging

from sqlalchemy.orm import joinedload

from app import supervision
from app.alerting.dispatcher import declencher_alertes
from app.config_system import get_config_int
from app.connectors import connecteurs_actifs
from app.conservation import (
    identifiants_des_references, preparer_texte_conserve, signalements_a_completer,
    texte_complet,
)
from app.crawl.registre import marquer_traitee
from app.db import get_session, init_db
from app.matching.criticite import calculer_criticite
from app.matching.deduplication import completer_signalements
from app.matching.engine import match_text_against_catalogue
from app.matching.exclusion import filtrer_faux_positifs
from app.models import Selecteur, Source
from app.pipeline import _normaliser_entry

logger = logging.getLogger(__name__)

# Duree moyenne d'une requete sur une source .onion, delai FR-06 compris
# (30 a 45 s d'attente, plus la latence Tor) : sert a l'estimation affichee.
SECONDES_PAR_REQUETE = 45


class _ToutSaufCibles:
    """
    "Entrees deja traitees" au sens de BaseConnector.collect() : TOUT, sauf
    les annonces a relire. Seules les cibles sont donc "nouvelles" : elles
    seules consomment des pages de detail, et la pagination s'arrete quand
    les pages n'en contiennent plus.
    """

    def __init__(self, cibles):
        self.cibles = cibles

    def __contains__(self, identifiant):
        return identifiant not in self.cibles

    def __bool__(self):
        return True


def _inventaire(session, tous) -> list:
    """(connecteur, source, {reference: [signalements]}, ecartes) par source concernee."""
    plan = []
    for classe in connecteurs_actifs():
        source = session.query(Source).filter_by(nom=classe.SOURCE_NAME).first()
        if source is None:
            continue
        connecteur = classe(db_session=session, source_id=source.id)
        par_reference, ecartes = signalements_a_completer(session, source, connecteur, tous)
        if par_reference or ecartes:
            plan.append((connecteur, source, par_reference, ecartes))
    return plan


def _estimation(connecteur, nb_cibles) -> str:
    pages = min(connecteur.MAX_PAGES_LISTING, get_config_int("pages_listing_max"))
    requetes = pages + (nb_cibles if connecteur.SUPPORTE_DETAIL else 0)
    return f"{requetes} requete(s) au plus, environ {requetes * SECONDES_PAR_REQUETE // 60 + 1} min"


def _completer(session, source, entree, signalements, selecteurs) -> list:
    """
    Complete les expositions d'une annonce relue (meme regle qu'en collecte).

    source_id est transmis pour que les regles d'exclusion portant sur UNE
    source s'appliquent ici comme en collecte. Comme dans
    pipeline._completer_exposition, les regles de type ENTITE ne sont pas
    appliquees : une regle n'est jamais retroactive.
    """
    texte = entree["texte_brut"]
    detail = calculer_criticite(filtrer_faux_positifs(
        texte, match_text_against_catalogue(texte, selecteurs),
        session=session, source_id=source.id,
    ))

    completees = completer_signalements(
        session, signalements,
        categorie_ids=detail.categories,
        criticite=detail.score,
        niveau_criticite=detail.niveau,
        date_publication=entree.get("date_publication"),
        texte_brut=preparer_texte_conserve(texte),
        selecteurs=detail.details,
    )
    if entree["niveau_detail"] == "detail":
        # Signature comprise, comme en collecte : sans elle, une annonce
        # everest relue ici serait "amorcee" - relue - au cycle suivant.
        marquer_traitee(
            session, source.id, entree["identifiant_entree"], a_produit_exposition=True,
            signature_listing=entree["signature_listing"],
        )
        session.commit()

    lignes = []
    for exposition, ancienne in completees:
        # Meme regle qu'en collecte : une hausse significative de criticite
        # sur une exposition connue declenche l'alerte de confirmation.
        declencher_alertes(session, exposition, est_nouvelle=False, ancienne_criticite=ancienne)
        lignes.append(
            f"  {exposition.nom_entite!r} : texte {len(texte)} car., "
            f"{detail.nb_selecteurs} selecteur(s), criticite {ancienne} -> {exposition.criticite}"
        )
    return lignes


def _relire_source(session, connecteur, source, par_reference, selecteurs):
    """Relit les annonces d'une source ; retourne les references non retrouvees."""
    cibles = identifiants_des_references(connecteur, par_reference)

    resultat = connecteur.collect(
        entrees_connues=_ToutSaufCibles(cibles),
        budget_details=len(par_reference),
        profondeur_max=get_config_int("pages_listing_max"),
        date_limite=None,
    )
    if not resultat["success"]:
        print(f"  source injoignable : {resultat['error']} (detail dans la page Audit)")
        return list(par_reference)

    retrouvees = set()
    for brute in resultat["extracted_text"]["entries"]:
        try:
            entree = _normaliser_entry(brute, connecteur)
        except Exception as erreur:
            logger.warning(f"[rattrapage] Entree illisible ({connecteur.SOURCE_NAME}) : {erreur}")
            continue
        signalements = par_reference.get(entree["reference_source"])
        if not signalements:
            continue
        retrouvees.add(entree["reference_source"])

        if not entree["texte_brut"] or not texte_complet(entree):
            print(f"  {entree['reference_source']} : page de detail en echec "
                  f"({entree.get('echec_detail') or 'non servie'}), a relancer plus tard")
            continue
        for ligne in _completer(session, source, entree, signalements, selecteurs):
            print(ligne)

    return [reference for reference in par_reference if reference not in retrouvees]


def executer(nom_source=None, tous=False, confirmer=False):
    init_db()

    if confirmer and supervision.etat_courant()["actif"]:
        raise SystemExit(
            "Le scheduler est en marche : arretez-le avant le rattrapage (deux processus "
            "ne partagent pas leur delai FR-06 entre deux requetes a une source)."
        )

    session = get_session()
    try:
        plan = [
            ligne for ligne in _inventaire(session, tous)
            if nom_source is None or ligne[0].SOURCE_NAME == nom_source
        ]
        if not plan:
            print("Aucun signalement a completer.")
            return

        selecteurs = (
            session.query(Selecteur).options(joinedload(Selecteur.categorie))
            .filter_by(actif=True).all()
        )

        for connecteur, source, par_reference, ecartes in plan:
            nb = sum(len(s) for s in par_reference.values())
            print(f"\n{connecteur.SOURCE_NAME} : {nb} signalement(s) a completer"
                  + (f" ({_estimation(connecteur, len(par_reference))})" if par_reference else ""))
            if ecartes:
                print(f"  {ecartes} signalement(s) sans reference propre a l'annonce : texte "
                      f"conserve par la collecte, au prochain cycle ou l'annonce est listee")
            if not par_reference:
                continue
            if not confirmer:
                for reference, signalements in par_reference.items():
                    noms = ", ".join(repr(s.exposition.nom_entite) for s in signalements)
                    print(f"  {reference} -> {noms}")
                continue

            introuvables = _relire_source(session, connecteur, source, par_reference, selecteurs)
            for reference in introuvables:
                print(f"  {reference} : annonce introuvable (retiree du site, ou au-dela des "
                      f"pages parcourues)")

        if not confirmer:
            print("\nSIMULATION : rien n'a ete demande aux sources. Arreter le scheduler, "
                  "puis relancer avec --confirmer.")
    finally:
        session.close()


def _analyser_arguments():
    parseur = argparse.ArgumentParser(
        description="Recupere le texte des annonces et leurs selecteurs pour les "
                    "signalements qui n'en ont pas (simulation sans --confirmer)."
    )
    parseur.add_argument("--source", help="SOURCE_NAME a traiter (defaut : toutes)")
    parseur.add_argument(
        "--tous", action="store_true",
        help="Relire aussi les signalements deja complets (texte et selecteurs ne sont "
             "remplaces que par plus complet)",
    )
    parseur.add_argument("--confirmer", action="store_true",
                         help="Lancer reellement la relecture (sinon : simulation)")
    return parseur.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    arguments = _analyser_arguments()
    executer(arguments.source, tous=arguments.tous, confirmer=arguments.confirmer)
