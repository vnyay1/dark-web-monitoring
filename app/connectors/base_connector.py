"""
FR-02 - Interface de connecteurs de sources.

Toute nouvelle source doit etre ajoutee en creant une nouvelle classe
qui herite de BaseConnector et redefinit les methodes necessaires,
sans jamais modifier la logique principale de l'application.

Convention (pas de contrainte stricte via ABC) :
- fetch()   : recupere le contenu brut de la source (en memoire uniquement, CN-05)
- parse()   : extrait le texte pertinent depuis le contenu brut
- get_metadata() : retourne les informations de la source (nom, type)

FR-17 : chaque appel a collect() journalise son resultat (succes/echec)
dans la table JournalAudit, de maniere append-only (aucune methode de
modification/suppression n'est exposee pour cette table).
"""

import logging
import time

logger = logging.getLogger(__name__)


class BaseConnector:
    """
    Classe de base pour tous les connecteurs de sources.

    Un connecteur concret doit redefinir :
    - fetch()
    - parse(raw_content)

    Il peut optionnellement redefinir :
    - get_metadata()
    """

    # A redefinir dans chaque connecteur concret
    SOURCE_NAME = "unknown_source"
    SOURCE_TYPE = "unknown"  # ex: "ransomware_site", "paste", "forum", "telegram"
    MIN_DELAY_SECONDS = 30   # FR-06 - delai minimum entre deux requetes (jamais < 30s)

    def __init__(self, tor_session=None, db_session=None, source_id=None):
        """
        tor_session : session de connexion Tor deja etablie (cf module FR-01),
        injectee ici plutot que recreee dans chaque connecteur.

        db_session : session SQLAlchemy pour ecrire le journal d'audit (FR-17).
        Optionnelle : si non fournie, la journalisation en base est ignoree
        (utile pour les tests manuels sans base de donnees, ex: FR-01/FR-02).

        source_id : identifiant de l'enregistrement Source correspondant en
        base (table sources), utilise pour lier les entrees du journal
        d'audit a la bonne source. Optionnel pour les memes raisons.
        """
        self.tor_session = tor_session
        self.db_session = db_session
        self.source_id = source_id
        self._last_request_time = None

    def _respect_rate_limit(self):
        """Applique le delai minimum entre deux requetes (FR-06)."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            wait_time = self.MIN_DELAY_SECONDS - elapsed
            if wait_time > 0:
                logger.info(f"[{self.SOURCE_NAME}] Rate limiting : attente de {wait_time:.1f}s")
                time.sleep(wait_time)
        self._last_request_time = time.time()

    def fetch(self):
        """
        Recupere le contenu brut de la source.
        DOIT etre redefini par chaque connecteur concret.
        Le contenu retourne doit rester en memoire (CN-05), jamais ecrit sur disque.
        """
        raise NotImplementedError(
            f"Le connecteur {self.__class__.__name__} doit implementer fetch()"
        )

    def parse(self, raw_content):
        """
        Extrait le texte pertinent depuis le contenu brut recupere par fetch().
        DOIT etre redefini par chaque connecteur concret.
        """
        raise NotImplementedError(
            f"Le connecteur {self.__class__.__name__} doit implementer parse()"
        )

    def get_metadata(self):
        """Retourne les informations de base de la source (redefinissable si besoin)."""
        return {
            "source_name": self.SOURCE_NAME,
            "source_type": self.SOURCE_TYPE,
        }

    def _journaliser(self, resultat, details=None):
        """
        FR-17 - Ecrit une entree dans le journal d'audit (append-only).
        Ne fait rien si aucune db_session n'a ete fournie (mode test sans base).
        """
        if self.db_session is None:
            return

        from app.models import JournalAudit, ResultatAudit

        entry = JournalAudit(
            source_id=self.source_id,
            resultat=ResultatAudit.SUCCES if resultat == "succes" else ResultatAudit.ECHEC,
            details=details,
        )
        self.db_session.add(entry)
        self.db_session.commit()

    def collect(self):
        """
        Point d'entree principal : orchestre fetch() + parse() en respectant
        le rate limiting (FR-06), et journalise systematiquement le resultat
        (FR-17).

        Retourne un dict contenant le texte extrait et les metadonnees,
        jamais le contenu brut complet au-dela de cette fonction (CN-05).
        """
        self._respect_rate_limit()

        try:
            raw_content = self.fetch()
        except Exception as e:
            logger.error(f"[{self.SOURCE_NAME}] Echec fetch() : {e}")
            self._journaliser("echec", details=f"fetch() : {str(e)[:500]}")
            return {"success": False, "error": str(e), "metadata": self.get_metadata()}

        try:
            extracted_text = self.parse(raw_content)
        except Exception as e:
            logger.error(f"[{self.SOURCE_NAME}] Echec parse() : {e}")
            self._journaliser("echec", details=f"parse() : {str(e)[:500]}")
            return {"success": False, "error": str(e), "metadata": self.get_metadata()}
        finally:
            # Le contenu brut n'est plus reference apres le parsing (CN-05)
            del raw_content

        self._journaliser("succes", details=None)

        return {
            "success": True,
            "extracted_text": extracted_text,
            "metadata": self.get_metadata(),
        }