"""
Conservation du texte des annonces : DEROGATION a CN-04/CN-05.

DECISION (2026-09-18, porteur du projet) - l'analyste doit pouvoir relire,
depuis le detail d'une exposition, le texte de l'annonce qui l'a
declenchee ; sans lui, il ne peut ni qualifier l'exposition ni verifier le
travail du moteur de correspondance. Ce texte etait jusqu'ici detruit en
fin de cycle (CN-05). L'accord ecrit de l'encadrant est a consigner.

Ce module est le POINT D'AUDIT UNIQUE de la derogation. Perimetre :

1. Seul le texte DEJA EXTRAIT et analyse d'une entree qui a PRODUIT une
   exposition est conserve (SourceReference.texte_brut). Jamais le HTML
   brut d'une page, jamais le texte d'une entree sans correspondance : le
   registre du crawl reste sans aucun contenu.
2. Il est masque avant stockage (preparer_texte_conserve) : URL (deja
   retirees par BaseConnector.nettoyer_urls), adresses email, empreintes,
   mots de passe annonces, numeros de telephone et longues suites de
   chiffres. LIMITE CONNUE : les noms de personnes ne peuvent pas etre
   detectes de facon fiable et restent en clair.
3. Il est purge apres retention_texte_brut_jours (purger_textes_bruts, en
   fin de cycle). 0 desactive la conservation ET efface les textes deja
   conserves : c'est l'interrupteur si la derogation est retiree.
4. Il n'est lisible que par un superviseur ou plus, par un endpoint dedie
   (Cache-Control: no-store), et n'apparait dans aucune liste, aucun
   export ni aucun rapport.
"""

import logging
import re
from datetime import timedelta

from app.config_system import get_config_int
from app.models import SourceReference, utc_now

logger = logging.getLogger(__name__)


# Ordre d'application significatif : l'email avant les suites de chiffres
# (un email peut en contenir), le mot de passe avant tout le reste (sa
# valeur peut ressembler a n'importe quoi).
MASQUES = (
    (re.compile(r"(?i)\b(password|passwd|pwd|mot de passe|mdp)(\s*[:=]\s*)\S+"),
     r"\1\2[SECRET MASQUE]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
     "[EMAIL MASQUE]"),
    # Empreintes MD5 (32), SHA-1 (40), SHA-256 (64)... en hexadecimal.
    (re.compile(r"\b[a-fA-F0-9]{32,}\b"), "[EMPREINTE MASQUEE]"),
    # Telephones camerounais : +237 / 00237 suivi de 8 ou 9 chiffres, avec
    # ou sans separateurs.
    (re.compile(r"(?:\+|\b00)237[\s.-]?\d(?:[\s.-]?\d){7,8}\b"), "[NUMERO MASQUE]"),
    # Numero national a 9 chiffres (6XX XX XX XX mobile, 2XX XX XX XX
    # fixe). Les separateurs admis excluent le tiret : une date
    # 2026-09-18 ne doit pas etre prise pour un numero.
    (re.compile(r"(?<!\d)[62]\d{2}(?:[ .]?\d{2}){3}(?!\d)"), "[NUMERO MASQUE]"),
    # Toute suite d'au moins 9 chiffres : numero de CNI, de compte,
    # d'identifiant client. Une date compacte (20260918) en a 8.
    (re.compile(r"(?<!\d)\d{9,}(?!\d)"), "[NUMERO MASQUE]"),
)


def preparer_texte_conserve(texte):
    """Texte d'une entree tel qu'il peut etre conserve : masque (cf. MASQUES)."""
    if not texte:
        return texte
    for motif, remplacement in MASQUES:
        texte = motif.sub(remplacement, texte)
    return texte


def duree_conservation_jours() -> int:
    """Retention reglee par l'administrateur ; 0 = aucun texte conserve."""
    return get_config_int("retention_texte_brut_jours")


def purger_textes_bruts(session, jours=None) -> int:
    """
    Efface les textes conserves depuis plus de 'jours' (tous si 0). Le
    signalement lui-meme est garde : seul son texte disparait.
    """
    jours = duree_conservation_jours() if jours is None else jours

    requete = session.query(SourceReference).filter(SourceReference.date_texte_brut.isnot(None))
    if jours > 0:
        requete = requete.filter(
            SourceReference.date_texte_brut < utc_now() - timedelta(days=jours)
        )

    effaces = requete.update(
        {SourceReference.texte_brut: None, SourceReference.date_texte_brut: None},
        synchronize_session=False,
    )
    session.commit()

    if effaces:
        logger.info(f"[conservation] {effaces} texte(s) d'annonce efface(s) (retention {jours} j).")
    return effaces
