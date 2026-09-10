"""
FR-02 - Interface de connecteurs de sources.

Toute nouvelle source doit etre ajoutee en creant une nouvelle classe
qui herite de BaseConnector, sans jamais modifier la logique principale
de l'application.

CONTRAT DE COLLECTE - collect() orchestre N requetes rate-limitees, en
deux phases :

  1. LISTING : parcours des pages de liste (pagination bornee par
     MAX_PAGES_LISTING). Arret anticipe des qu'une page n'apporte plus
     aucune entree nouvelle - avec PAGES_GRACE pages de tolerance, car
     une entree epinglee ou un reordonnancement peut faire apparaitre
     une page "deja connue" avant les vraies nouveautes.

  2. DETAIL : pour les entrees NOUVELLES uniquement, et dans la limite
     du budget alloue, recuperation de la page de detail dont le texte
     est concatene au texte du listing. C'est cette phase qui rend le
     matching fiable : le listing ne contient souvent qu'un nom et une
     phrase, insuffisants pour reperer une mention camerounaise.

Les entrees nouvelles non servies par le budget ne sont PAS marquees et
seront traitees au run suivant : le crawl est reprenable.

DEFINITION DE L'ECHEC (FR-17) - une collecte est en ECHEC si et
seulement si la PAGE 1 du listing n'a pu etre recuperee ou parsee. Une
page 2+ ou une page de detail en erreur est une DEGRADATION : elle est
comptabilisee mais ne marque pas la source comme indisponible. C'est la
seule definition qui garde Source.nombre_erreurs et est_indisponible()
interpretables comme "la source est-elle joignable ?".

CN-05 : le contenu brut n'existe qu'en memoire et est libere des que le
parsing est termine - jamais ecrit sur disque.

CN-04 : url_detail() est le SEUL endroit ou l'on decide qu'un lien est
visitable. Par defaut il retourne None : aucune page de detail n'est
visitee tant qu'un connecteur ne l'a pas explicitement autorise. Les
sources dont le seul lien par entree pointe vers les donnees divulguees
(orion_leaks) ou vers un site tiers hors perimetre (cmd_organization)
restent donc en listing-only.

FR-06 : le delai minimum entre deux requetes est applique PAR SOURCE
(et non par instance de connecteur), et ne peut jamais descendre sous
DELAI_MINIMUM_ABSOLU. Il se compte depuis la FIN de la reponse precedente,
et non depuis son debut : via Tor, une page peut mettre 25 s a arriver, et
un delai compte de debut a debut ne laissait alors que quelques secondes de
silence entre deux requetes. Une part aleatoire s'y ajoute, pour que la
cadence ne soit pas un metronome reconnaissable cote source. Enfin, chaque
REESSAI est une requete a part entiere, soumise au meme delai.
"""

import hashlib
import json
import logging
import random
import re
import time
from urllib.parse import urlparse

from app.tor import get_via_tor, renew_tor_circuit

logger = logging.getLogger(__name__)


# CN-04/OS-03 - toute URL trouvee dans un texte conserve est retiree : sur
# plusieurs sources, la description d'une victime contient un lien pointant
# DIRECTEMENT vers les donnees divulguees.
URL_PATTERN = re.compile(r"https?://\S+")

# FR-06 / CN-09 / CN-10 - plancher non negociable, quel que soit le reglage
# d'un connecteur concret.
DELAI_MINIMUM_ABSOLU = 30

# Part aleatoire ajoutee au delai minimum, tiree a chaque requete : l'ecart
# reel entre deux requetes sur une source varie entre 30 et 45 s.
DELAI_ALEATOIRE_MAX = 15

# Tentatives par page de listing. Chacune attend le delai complet : une
# source en panne coute donc quelques minutes, jamais une rafale.
TENTATIVES_PAR_DEFAUT = 3

# Le fuzzy matching de app.matching.engine est en O(len(texte) x nb_selecteurs).
# Un post integral peut faire plusieurs centaines de Ko et faire exploser la
# duree du run sans rien apporter au matching.
LIMITE_TEXTE_BRUT = 20000


class BaseConnector:
    """
    Classe de base pour tous les connecteurs de sources.

    Un connecteur concret DOIT redefinir :
    - parse(raw_content) -> {"entries": [...], "texte_global": str, "nb_entries": int}

    Il PEUT redefinir :
    - url_page_suivante(raw_content, page)  (avec SUPPORTE_PAGINATION = True)
    - url_detail(entry) + parse_detail(raw_content, entry)  (avec SUPPORTE_DETAIL = True)
    - identifiant_entree(entry), priorite_detail(entry), get_metadata()
    """

    # A redefinir dans chaque connecteur concret
    SOURCE_NAME = "unknown_source"
    SOURCE_TYPE = "unknown"  # ex: "ransomware_site", "paste", "forum", "telegram"
    TARGET_URL = None        # page de listing d'entree de la source

    MIN_DELAY_SECONDS = 30   # FR-06 - jamais applique sous DELAI_MINIMUM_ABSOLU

    # Capacites, activees explicitement source par source apres verification
    # de la structure reelle du site (cf. app.connectors.reconnaissance).
    SUPPORTE_PAGINATION = False
    SUPPORTE_DETAIL = False

    # Formats strptime propres a la source, essayes en premier par
    # app.connectors.dates.parser_date() avant les formats communs.
    DATE_FORMATS = ()

    MAX_PAGES_LISTING = 1
    PAGES_GRACE = 1          # pages explorees au-dela de la 1re page 100% connue
    MAX_DETAILS_PAR_RUN = 0
    MAX_ECHECS_DETAIL = 3    # au-dela, l'entree est abandonnee (cf. registre)

    # Etat de rate limiting PAR SOURCE : instant de FIN de la derniere
    # requete. Volontairement porte par BaseConnector et non par
    # self/type(self) : sinon chaque sous-classe creerait son propre
    # dictionnaire et deux instances du meme connecteur (relance manuelle
    # pendant un run planifie) violeraient FR-06 silencieusement.
    _fin_derniere_requete_par_source = {}

    def __init__(self, db_session=None, source_id=None):
        """
        db_session : session SQLAlchemy pour le journal d'audit (FR-17).
        Optionnelle : sans elle, la journalisation est ignoree (tests
        manuels via les blocs __main__, sans base de donnees).

        source_id : identifiant de l'enregistrement Source correspondant,
        pour lier les entrees du journal a la bonne source.

        Le connecteur n'accede JAMAIS a la base autrement que pour ecrire
        le journal d'audit : la liste des entrees deja traitees lui est
        passee en argument de collect() par le pipeline.
        """
        self.db_session = db_session
        self.source_id = source_id

    # ------------------------------------------------------------------
    # Reseau et conformite
    # ------------------------------------------------------------------

    def _respect_rate_limit(self):
        """
        Attend que le delai minimum, plus sa part aleatoire, se soit ecoule
        depuis la FIN de la derniere requete sur cette source (FR-06).
        """
        delai = (
            max(self.MIN_DELAY_SECONDS, DELAI_MINIMUM_ABSOLU)
            + random.uniform(0, DELAI_ALEATOIRE_MAX)
        )
        fin_precedente = BaseConnector._fin_derniere_requete_par_source.get(self.SOURCE_NAME)

        if fin_precedente is not None:
            attente = delai - (time.time() - fin_precedente)
            if attente > 0:
                logger.info(f"[{self.SOURCE_NAME}] Rate limiting : attente de {attente:.1f}s")
                time.sleep(attente)

    def _marquer_fin_requete(self):
        BaseConnector._fin_derniere_requete_par_source[self.SOURCE_NAME] = time.time()

    def requete(self, url=None, tentatives=TENTATIVES_PAR_DEFAUT, **kwargs):
        """
        Seul point de sortie reseau d'un connecteur (collecte comme
        reconnaissance). Renvoie la reponse HTTP complete.

        Les reessais sont faits ICI, et non par get_via_tor (appele avec
        max_retries=1) : ses propres reessais partaient a 5 s d'intervalle,
        hors de tout rate limiting. Ici, chaque tentative attend le delai
        complet et part sur un circuit Tor renouvele.
        """
        derniere_erreur = None

        for tentative in range(1, max(1, tentatives) + 1):
            self._respect_rate_limit()
            try:
                return get_via_tor(url or self.TARGET_URL, max_retries=1, **kwargs)
            except Exception as erreur:
                derniere_erreur = erreur
                logger.warning(
                    f"[{self.SOURCE_NAME}] Tentative {tentative}/{tentatives} echouee : "
                    f"{self._libelle_erreur(erreur)}"
                )
                if tentative < tentatives:
                    renew_tor_circuit()
            finally:
                # Echec compris : une requete qui echoue a bien touche la source.
                self._marquer_fin_requete()

        raise derniere_erreur

    def fetch(self, url=None, max_retries=TENTATIVES_PAR_DEFAUT, **kwargs):
        """
        Recupere le contenu brut d'une page, en respectant le rate limiting.
        Le contenu reste en memoire (CN-05), jamais ecrit sur disque.

        max_retries garde son nom historique (appelants existants) : c'est le
        nombre de tentatives, chacune soumise au delai.
        """
        return self.requete(url, tentatives=max_retries, **kwargs).text

    def nettoyer_urls(self, texte):
        """
        Retire toute URL du texte avant conservation (CN-04/OS-03).

        Centralise ici plutot que duplique dans chaque connecteur : c'est
        une fonction de conformite, elle doit avoir un seul point d'audit.
        """
        if not texte:
            return texte
        return URL_PATTERN.sub("[LIEN RETIRE]", texte).strip()

    # ------------------------------------------------------------------
    # A redefinir par les connecteurs concrets
    # ------------------------------------------------------------------

    def parse(self, raw_content):
        """
        Extrait les entrees depuis le contenu brut d'une page de listing.
        DOIT etre redefini par chaque connecteur concret.
        """
        raise NotImplementedError(
            f"Le connecteur {self.__class__.__name__} doit implementer parse()"
        )

    def url_page_suivante(self, raw_content, page_courante):
        """URL de la page de listing suivante, ou None s'il n'y en a plus."""
        return None

    def url_detail(self, entry):
        """
        URL de la page de detail d'une entree, ou None si elle ne doit pas
        etre visitee.

        CN-04 : c'est l'UNIQUE endroit ou l'on autorise la visite d'un lien.
        Retourner None est le defaut sur : un lien pointant vers les donnees
        divulguees, un lien vers un site tiers (site officiel de la victime),
        ou toute URL dont la nature n'a pas ete verifiee.
        """
        return None

    def parse_detail(self, raw_content, entry):
        """
        Extrait le texte de la page de detail d'une entree.
        Retourne un dict contenant au moins {"texte_brut": str}, concatene
        au texte du listing par collect().
        """
        raise NotImplementedError(
            f"Le connecteur {self.__class__.__name__} declare SUPPORTE_DETAIL "
            f"mais n'implemente pas parse_detail()"
        )

    def priorite_detail(self, entry):
        """
        Priorite d'une entree dans la depense du budget de pages de detail
        (plus grand = servi en premier). A priorite egale, l'ordre du
        listing est conserve (tri stable).

        Surcharge utile quand le listing revele deja un signal fort et
        gratuit (indicatif pays, domaine .cm) : le systeme devient utile
        des le premier run au lieu du dixieme.
        """
        return 0

    def identifiant_entree(self, entry):
        """
        Identite stable d'une entree au sein de la source, utilisee comme
        cle du registre de crawl.

        Retourne soit un CHEMIN RELATIF de la page de publication sur la
        source surveillee, soit une cle synthetique "h:<sha256>" non
        navigable. JAMAIS une URL absolue : le registre doit rester
        auditable (aucune ligne ne doit commencer par "http").
        """
        chemin = self._chemin_interne(entry.get("lien_detail"))
        if chemin:
            return chemin

        graine = "|".join(
            str(entry.get(cle) or "")
            for cle in ("nom_entite_detecte", "titre", "date_publication", "texte_brut")
        )
        return "h:" + hashlib.sha256(graine.encode("utf-8")).hexdigest()[:32]

    def get_metadata(self):
        """Retourne les informations de base de la source (redefinissable si besoin)."""
        return {
            "source_name": self.SOURCE_NAME,
            "source_type": self.SOURCE_TYPE,
        }

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def collect(self, entrees_connues=None, budget_details=None, profondeur_max=None):
        """
        Point d'entree principal (cf. contrat en tete de module).

        entrees_connues : set d'identifiants deja traites, fourni par le
        pipeline. Les entrees qui s'y trouvent ne consomment pas de budget.
        budget_details  : nombre maximum de pages de detail pour ce run.
        profondeur_max  : nombre maximum de pages de listing pour ce run.

        Appele sans argument sur un connecteur qui ne surcharge rien, il
        fait exactement une requete et retourne exactement la meme
        structure qu'avant l'introduction du crawl profond.
        """
        debut = time.time()
        entrees_connues = entrees_connues or set()
        budget = self.MAX_DETAILS_PAR_RUN if budget_details is None else budget_details
        profondeur = self.MAX_PAGES_LISTING if profondeur_max is None else profondeur_max

        stats = {
            "pages_listing": 0, "entrees": 0, "nouvelles": 0,
            "details_ok": 0, "details_echec": 0, "details_ignores": 0,
            "budget_alloue": budget, "arret": "page_unique",
        }
        erreurs = {}

        entries, erreur_bloquante = self._phase_listing(
            profondeur, entrees_connues, stats, erreurs
        )

        if erreur_bloquante is not None:
            self._journaliser_synthese(stats, erreurs, False, debut)
            return {
                "success": False,
                "error": erreur_bloquante,
                "metadata": self.get_metadata(),
                "statistiques_crawl": stats,
            }

        self._phase_detail(entries, entrees_connues, budget, stats, erreurs)
        self._journaliser_synthese(stats, erreurs, True, debut)

        return {
            "success": True,
            "extracted_text": {
                "entries": entries,
                "texte_global": "\n".join(e.get("texte_brut") or "" for e in entries),
                "nb_entries": len(entries),
            },
            "metadata": self.get_metadata(),
            "statistiques_crawl": stats,
        }

    def _phase_listing(self, profondeur, entrees_connues, stats, erreurs):
        """
        Parcourt les pages de listing. Retourne (entries, erreur_bloquante) ;
        erreur_bloquante n'est non-None que si la PAGE 1 a echoue.
        """
        entries = []
        identifiants_vus = set()
        url = self.TARGET_URL
        page = 1
        pages_sans_nouveaute = 0

        while url and page <= profondeur:
            try:
                raw = self.fetch(url)
            except Exception as e:
                self._compter_erreur(erreurs, "listing", e)
                if page == 1:
                    logger.error(f"[{self.SOURCE_NAME}] Echec de la page 1 du listing : {e}")
                    return [], self._libelle_erreur(e)
                logger.warning(f"[{self.SOURCE_NAME}] Page {page} inaccessible, arret : {e}")
                stats["arret"] = "erreur_page"
                break

            try:
                resultat = self.parse(raw)
                url_suivante = (
                    self.url_page_suivante(raw, page) if self.SUPPORTE_PAGINATION else None
                )
            except Exception as e:
                self._compter_erreur(erreurs, "parse", e)
                if page == 1:
                    logger.error(f"[{self.SOURCE_NAME}] Echec du parsing de la page 1 : {e}")
                    return [], self._libelle_erreur(e)
                logger.warning(f"[{self.SOURCE_NAME}] Parsing de la page {page} echoue : {e}")
                stats["arret"] = "erreur_page"
                break
            finally:
                del raw  # CN-05 - le contenu brut ne survit pas au parsing

            stats["pages_listing"] += 1
            page_entries = resultat.get("entries") or []

            nouvelles_sur_la_page = 0
            for entry in page_entries:
                identifiant = entry.get("identifiant_entree") or self.identifiant_entree(entry)
                # Une entree epinglee peut reapparaitre d'une page a l'autre.
                if identifiant in identifiants_vus:
                    continue
                identifiants_vus.add(identifiant)
                entry["identifiant_entree"] = identifiant
                entry["niveau_detail"] = "listing"
                if identifiant not in entrees_connues:
                    nouvelles_sur_la_page += 1
                entries.append(entry)

            if not page_entries:
                stats["arret"] = "page_vide"
                break

            pages_sans_nouveaute = 0 if nouvelles_sur_la_page else pages_sans_nouveaute + 1
            if pages_sans_nouveaute > self.PAGES_GRACE:
                stats["arret"] = "page_connue"
                break

            if not self.SUPPORTE_PAGINATION:
                stats["arret"] = "page_unique"
                break
            if url_suivante is None:
                stats["arret"] = "fin_pagination"
                break
            if page + 1 > profondeur:
                stats["arret"] = "profondeur_max"
                break

            url = url_suivante
            page += 1

        stats["entrees"] = len(entries)
        stats["nouvelles"] = sum(
            1 for e in entries if e["identifiant_entree"] not in entrees_connues
        )
        return entries, None

    def _phase_detail(self, entries, entrees_connues, budget, stats, erreurs):
        """
        Enrichit les entrees NOUVELLES par leur page de detail, dans la
        limite du budget. Un echec sur une entree n'interrompt jamais la
        collecte : il est comptabilise et reessaye au run suivant.
        """
        if not self.SUPPORTE_DETAIL or budget <= 0:
            return

        candidats = [
            e for e in entries
            if e["identifiant_entree"] not in entrees_connues and self.url_detail(e)
        ]
        candidats.sort(key=self.priorite_detail, reverse=True)  # tri stable
        stats["details_ignores"] = max(0, len(candidats) - budget)

        for entry in candidats[:budget]:
            try:
                # Une seule tentative : une page de detail en echec est
                # reessayee au run suivant via le registre, plutot que de
                # consommer ici plusieurs delais complets sur une entree.
                raw = self.fetch(self.url_detail(entry), max_retries=1)
                try:
                    enrichi = self.parse_detail(raw, entry) or {}
                finally:
                    del raw  # CN-05
            except Exception as e:
                logger.warning(
                    f"[{self.SOURCE_NAME}] Detail indisponible pour "
                    f"{entry['identifiant_entree']} : {e}"
                )
                entry["echec_detail"] = self._libelle_erreur(e)
                self._compter_erreur(erreurs, "detail", e)
                stats["details_echec"] += 1
                continue

            # Le listing garde la priorite, SAUF la ou il n'avait rien : un
            # listing qui pose "date_publication": None ne doit pas masquer la
            # date trouvee sur la page de detail (setdefault() l'ignorait,
            # la cle existant deja).
            for cle, valeur in enrichi.items():
                if cle != "texte_brut" and entry.get(cle) in (None, ""):
                    entry[cle] = valeur

            entry["texte_brut"] = " ".join(filter(None, [
                entry.get("texte_brut"), enrichi.get("texte_brut"),
            ]))[:LIMITE_TEXTE_BRUT]
            entry["niveau_detail"] = "detail"
            stats["details_ok"] += 1

    # ------------------------------------------------------------------
    # Journal d'audit (FR-17, append-only)
    # ------------------------------------------------------------------

    def _journaliser_synthese(self, stats, erreurs, succes, debut):
        """
        Ecrit 1 ligne de synthese, plus au plus 3 lignes d'erreurs AGREGEES
        par classe.

        Une ligne par requete HTTP produirait environ un millier de lignes
        par jour dans une table append-only sans purge. L'agregation rend
        au contraire visible un motif systematique (le site a change ses
        URLs de detail) sans qu'une instabilite Tor ne noie le journal.

        details ne contient jamais de corps de reponse (CN-04) : uniquement
        des compteurs et des libelles d'exception tronques.
        """
        stats["duree_s"] = round(time.time() - debut, 1)

        if self.db_session is None:
            return

        from app.models import JournalAudit, ResultatAudit

        lignes = [JournalAudit(
            source_id=self.source_id,
            resultat=ResultatAudit.SUCCES if succes else ResultatAudit.ECHEC,
            details=json.dumps(stats, ensure_ascii=False)[:500],
        )]

        principales = sorted(erreurs.items(), key=lambda kv: kv[1], reverse=True)[:3]
        for cle, occurrences in principales:
            phase, _, libelle = cle.partition(":")
            lignes.append(JournalAudit(
                source_id=self.source_id,
                resultat=ResultatAudit.ECHEC,
                details=json.dumps(
                    {"phase": phase, "erreur": libelle, "occurrences": occurrences},
                    ensure_ascii=False,
                )[:500],
            ))

        self.db_session.add_all(lignes)
        self.db_session.commit()

    @staticmethod
    def _libelle_erreur(exception):
        """Libelle court et sans contenu de page (CN-04)."""
        return f"{type(exception).__name__}: {str(exception)[:200]}"

    @staticmethod
    def _compter_erreur(erreurs, phase, exception):
        cle = f"{phase}:{type(exception).__name__}"
        erreurs[cle] = erreurs.get(cle, 0) + 1

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _chemin_interne(self, lien):
        """
        Reduit un lien a son chemin relatif s'il appartient bien au domaine
        surveille. Retourne None pour un lien vers un domaine tiers, afin
        que l'appelant retombe sur un identifiant synthetique non navigable.
        """
        if not lien:
            return None

        lien = lien.strip()
        if lien.startswith("/"):
            return lien[:500]

        analyse = urlparse(lien)
        if not analyse.netloc:
            return ("/" + lien.lstrip("/"))[:500]

        if self.TARGET_URL and analyse.netloc == urlparse(self.TARGET_URL).netloc:
            chemin = analyse.path or "/"
            if analyse.query:
                chemin += "?" + analyse.query
            return chemin[:500]

        return None
