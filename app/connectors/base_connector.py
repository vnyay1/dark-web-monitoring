"""
FR-02 - Interface de connecteurs de sources.

Toute nouvelle source doit etre ajoutee en creant une nouvelle classe
qui herite de BaseConnector, sans jamais modifier la logique principale
de l'application.

CONTRAT DE COLLECTE - collect() orchestre N requetes rate-limitees, en
deux phases :

  1. LISTING : parcours des pages de liste (pagination bornee par
     MAX_PAGES_LISTING et par le plafond reglable pages_listing_max).
     Trois arrets anticipes, le premier atteint l'emporte :
       - "page_connue" : une page n'apporte plus aucune entree nouvelle,
         avec PAGES_GRACE pages de tolerance (une entree epinglee ou un
         reordonnancement peut faire apparaitre une page "deja connue"
         avant les vraies nouveautes) ;
       - "hors_periode" : toutes les dates lisibles de la page sont
         anterieures a la periode reglee par l'administrateur - les pages
         suivantes, plus anciennes encore, n'ont pas a etre demandees ;
       - "dates_illisibles" : aucune date lisible sur la page. Garde-fou :
         sans lui, un site qui changerait son format de date serait
         parcouru jusqu'au plafond a chaque cycle.
     Une source qui ne date ses annonces que sur la page de detail
     (DATE_SUR_DETAIL, safepay) est datee par SONDE : la page de detail de
     la derniere annonce NOUVELLE de la page de listing est visitee des la
     phase de listing. Cette visite n'est pas perdue - l'entree est alors
     enrichie comme en phase de detail, qui ne la revisite pas.
     Chaque lien de pagination est valide par _page_suivante_validee() :
     meme domaine, meme chemin que le listing, page suivante exactement.

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
from urllib.parse import parse_qs, urljoin, urlparse

from app.connectors.dates import CLES_DATE, parser_date
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

    # Le listing ne date pas ses annonces, la page de detail si : l'arret
    # de pagination sur la periode passe alors par une sonde (cf. en-tete).
    DATE_SUR_DETAIL = False

    # Annonces rangees de la plus recente a la plus ancienne, pages suivantes
    # comprises (a verifier par reconnaissance, --phase pages). Une annonce
    # sans date recoit alors une date PLAFOND, cf. _poser_dates_plafond().
    LISTING_CHRONOLOGIQUE = False

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

        cible = url or self.TARGET_URL
        for tentative in range(1, max(1, tentatives) + 1):
            self._respect_rate_limit()
            # Journalise APRES l'attente : l'horodatage est celui de l'envoi
            # reel, ce qui permet de verifier le respect de FR-06 dans les
            # logs. Seul le chemin est ecrit (page d'annonce, cf. CN-03).
            logger.info(f"[{self.SOURCE_NAME}] Requete : {urlparse(cible).path or '/'}")
            try:
                return get_via_tor(cible, max_retries=1, **kwargs)
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

    def collect(self, entrees_connues=None, budget_details=None, profondeur_max=None,
                date_limite=None):
        """
        Point d'entree principal (cf. contrat en tete de module).

        entrees_connues : set d'identifiants deja traites, fourni par le
        pipeline. Les entrees qui s'y trouvent ne consomment pas de budget.
        budget_details  : nombre maximum de pages de detail pour ce run.
        profondeur_max  : plafond de pages de listing pour ce run ; ne peut
                          pas depasser MAX_PAGES_LISTING, plafond propre au
                          connecteur.
        date_limite     : debut de la periode reglee par l'administrateur,
                          fournie par le pipeline (le connecteur ne lit pas
                          la base). Sert a arreter la pagination.

        Appele sans argument sur un connecteur qui ne surcharge rien, il
        fait exactement une requete et retourne exactement la meme
        structure qu'avant l'introduction du crawl profond.
        """
        debut = time.time()
        entrees_connues = entrees_connues or set()
        budget = self.MAX_DETAILS_PAR_RUN if budget_details is None else budget_details
        profondeur = (
            self.MAX_PAGES_LISTING if profondeur_max is None
            else min(self.MAX_PAGES_LISTING, profondeur_max)
        )

        stats = {
            "pages_listing": 0, "entrees": 0, "nouvelles": 0,
            "details_ok": 0, "details_echec": 0, "details_ignores": 0,
            "budget_alloue": budget, "sondes_date": 0, "arret": "page_unique",
        }
        erreurs = {}

        entries, erreur_bloquante = self._phase_listing(
            profondeur, entrees_connues, stats, erreurs, date_limite
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
        if self.LISTING_CHRONOLOGIQUE:
            self._poser_dates_plafond(entries)
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

    def _phase_listing(self, profondeur, entrees_connues, stats, erreurs, date_limite=None):
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

            if date_limite is not None:
                arret = self._arret_par_date(
                    page_entries, date_limite, entrees_connues, stats, erreurs
                )
                if arret:
                    stats["arret"] = arret
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

    def _arret_par_date(self, page_entries, date_limite, entrees_connues, stats, erreurs):
        """
        Motif d'arret si la page ne justifie pas de demander la suivante,
        None sinon. Les entrees de la page elle-meme sont conservees : c'est
        le pipeline qui ecarte celles hors periode.
        """
        if self.DATE_SUR_DETAIL:
            sonde = self._entree_a_sonder(page_entries, entrees_connues)
            if sonde is None:
                # Rien de nouveau a dater sur cette page : c'est l'arret sur
                # pages connues (et sa page de tolerance) qui borne la suite.
                return None
            lisibles = [d for d in [self.dater_par_sonde(sonde, stats, erreurs)] if d]
        else:
            lisibles = self.dates_lisibles(page_entries)

        if not lisibles:
            logger.warning(
                f"[{self.SOURCE_NAME}] Aucune date lisible sur la page : pagination "
                f"arretee par prudence (format de date modifie par le site ?)."
            )
            return "dates_illisibles"
        if all(d < date_limite for d in lisibles):
            logger.info(
                f"[{self.SOURCE_NAME}] Page entierement anterieure au "
                f"{date_limite:%d/%m/%Y} : fin de la pagination."
            )
            return "hors_periode"
        return None

    def dates_lisibles(self, entries):
        """Dates interpretables des entrees (memes regles que le pipeline)."""
        dates = (
            parser_date(
                next((e.get(cle) for cle in CLES_DATE if e.get(cle)), None),
                self.DATE_FORMATS, source=self.SOURCE_NAME, journaliser=False,
            )
            for e in entries
        )
        return [d for d in dates if d is not None]

    def _poser_dates_plafond(self, entries):
        """
        Sur un listing chronologique, une annonce sans date lisible n'est pas
        plus recente que l'annonce datee qui la precede : cette date devient
        sa "date_plafond". Ce n'est PAS une date de publication - elle n'est
        jamais enregistree - mais une borne, qui suffit au pipeline pour
        ecarter l'annonce quand elle tombe avant la periode. Une annonce
        sans date placee avant toute annonce datee n'a pas de plafond : elle
        reste analysee, comme toute annonce non datee.
        """
        plafond = None
        for entry in entries:
            dates = self.dates_lisibles([entry])
            if dates:
                plafond = dates[0]
            elif plafond is not None:
                entry["date_plafond"] = plafond

    def _entree_a_sonder(self, page_entries, entrees_connues):
        """
        Derniere annonce NOUVELLE et visitable de la page, ou None. La
        derniere, car un listing presente les annonces de la plus recente a
        la plus ancienne ; une NOUVELLE, car sa page de detail aurait de
        toute facon ete visitee : la sonde ne coute alors aucune requete
        de plus. Seules les entrees retenues par le listing (niveau_detail
        pose) sont candidates - pas un doublon epingle ecarte.
        """
        for entry in reversed(page_entries):
            if (
                "niveau_detail" in entry
                and entry.get("identifiant_entree") not in entrees_connues
                and self.SUPPORTE_DETAIL
                and self.url_detail(entry)
            ):
                return entry
        return None

    def dater_par_sonde(self, entry, stats, erreurs):
        """
        Visite la page de detail de l'entree (si ce n'est deja fait) et
        retourne sa date interpretee, ou None.
        """
        if entry.get("niveau_detail") != "detail":
            stats["sondes_date"] = stats.get("sondes_date", 0) + 1
            self._enrichir_par_detail(entry, stats, erreurs)
        dates = self.dates_lisibles([entry])
        return dates[0] if dates else None

    def _phase_detail(self, entries, entrees_connues, budget, stats, erreurs):
        """
        Enrichit les entrees NOUVELLES par leur page de detail, dans la
        limite du budget. Un echec sur une entree n'interrompt jamais la
        collecte : il est comptabilise et reessaye au run suivant.
        """
        if not self.SUPPORTE_DETAIL or budget <= 0:
            return

        # Les entrees deja visitees par une sonde de date (ou dont la sonde
        # a echoue) ne sont pas revisitees.
        candidats = [
            e for e in entries
            if e["identifiant_entree"] not in entrees_connues
            and e.get("niveau_detail") != "detail"
            and not e.get("echec_detail")
            and self.url_detail(e)
        ]
        candidats.sort(key=self.priorite_detail, reverse=True)  # tri stable
        stats["details_ignores"] = max(0, len(candidats) - budget)

        for entry in candidats[:budget]:
            self._enrichir_par_detail(entry, stats, erreurs)

    def _enrichir_par_detail(self, entry, stats, erreurs):
        """
        Recupere la page de detail d'une entree et fusionne son contenu.
        Retourne True si l'entree a ete enrichie.
        """
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
            return False

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
        return True

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

    def _page_suivante_validee(self, lien, page_courante):
        """
        URL absolue de la page page_courante + 1 d'apres un lien de
        pagination trouve dans la page, ou None si le lien n'a pas la forme
        attendue. Controle commun a tous les connecteurs pagines :
        - meme domaine et meme chemin que le listing (TARGET_URL) : on ne
          suit jamais, sous couvert de pagination, un lien vers une autre
          page du site (CN-04, comme url_detail) ;
        - parametre "page" egal a page_courante + 1 : un lien "suivant" qui,
          sur la derniere page, pointerait vers elle-meme ferait boucler.
        """
        if not lien:
            return None
        listing = urlparse(self.TARGET_URL)
        cible = urlparse(urljoin(self.TARGET_URL, lien.strip()))
        if cible.netloc != listing.netloc or (cible.path or "/") != (listing.path or "/"):
            return None
        if parse_qs(cible.query).get("page") != [str(page_courante + 1)]:
            return None
        return cible.geturl()

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
