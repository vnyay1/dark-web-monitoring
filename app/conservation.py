"""
Conservation du texte des annonces : DEROGATION a CN-04/CN-05.

DECISION (2026-09-18) - a la demande de l'encadrant, qui l'a validee, le
texte INTEGRAL de l'annonce qui a declenche une exposition est conserve :
l'analyste doit pouvoir la relire depuis le detail de l'exposition pour la
qualifier et verifier le travail du moteur de correspondance. Ce texte
etait jusqu'ici detruit en fin de cycle (CN-05).

Ce module est le POINT D'AUDIT UNIQUE de la derogation. Perimetre :

1. Seul le texte COMPLET (listing + page de detail quand l'annonce en a
   une) d'une entree qui a PRODUIT une exposition est conserve
   (SourceReference.texte_brut). Jamais le HTML brut d'une page, jamais le
   texte d'une entree sans correspondance : le registre du crawl reste sans
   aucun contenu. Un titre de listing re-analyse seul n'est pas le texte de
   l'annonce : il n'est pas conserve (cf. texte_complet()).
2. Il est masque avant stockage (preparer_texte_conserve) : URL (deja
   retirees par BaseConnector.nettoyer_urls), adresses email, empreintes,
   mots de passe annonces, numeros de telephone et longues suites de
   chiffres. LIMITE CONNUE : les noms de personnes ne peuvent pas etre
   detectes de facon fiable et restent en clair.
3. Il est conserve sans limite de duree (decision de l'encadrant) ; la
   purge de conformite (super_admin) l'efface avec son exposition.
4. Il n'est lisible que par un superviseur ou plus, par un endpoint dedie
   (Cache-Control: no-store), et n'apparait dans aucune liste, aucun
   export ni aucun rapport.

Avec le texte sont enregistres les SELECTEURS trouves dans l'annonce
(termes du catalogue, poids, occurrences), qui justifient la criticite dans
le detail de l'exposition (SourceReference.selecteurs_trouves).

COMPLETION - un signalement sans texte ou sans selecteurs (annonce analysee
avant ces fonctions, ou lue sur son seul titre) est "a completer"
(signalements_a_completer). La collecte le complete d'elle-meme : elle
relit son annonce, page de detail comprise, sans lui appliquer la fenetre
d'analyse (cf. app.pipeline). app.maintenance.recuperer_textes fait la
meme chose a la demande, sans attendre le cycle ni son budget.
"""

import json
import re

from sqlalchemy.orm import joinedload

from app.models import SourceReference, utc_now


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


def texte_complet(entree) -> bool:
    """
    L'entree normalisee porte-t-elle le texte COMPLET de l'annonce ? Oui si
    sa page de detail a ete lue, ou si elle n'en a pas (source listing-only).

    Sinon, l'entree n'a que son titre de listing : elle ne produit pas
    d'exposition (cf. pipeline._traiter_une_entree) et, dans le seul cas ou
    elle en produit une - page de detail definitivement perdue -, ce titre
    n'est pas conserve : il afficherait "CCA Bank" en guise de texte de
    l'annonce, et masquerait qu'il reste a recuperer le vrai texte.
    """
    return entree.get("niveau_detail") == "detail" or not entree.get("a_page_detail")


def conserver_texte(signalement, texte_masque):
    """
    Pose le texte conserve d'un signalement, SEULEMENT s'il est plus long
    que celui deja conserve : une nouvelle lecture partielle (page de detail
    en echec, par exemple) ne doit jamais ecraser un texte complet.
    """
    if not texte_masque:
        return False
    if signalement.date_texte_brut is not None and len(texte_masque) <= len(signalement.texte_brut or ""):
        return False
    signalement.texte_brut = texte_masque
    signalement.date_texte_brut = utc_now()
    return True


def lire_selecteurs(signalement):
    """Selecteurs enregistres sur le signalement (liste), ou None."""
    if not signalement.selecteurs_trouves:
        return None
    try:
        return json.loads(signalement.selecteurs_trouves)
    except ValueError:
        return None


def score_de(selecteurs) -> int:
    """Score d'une liste de selecteurs enregistree : la somme de leurs poids."""
    return sum(s.get("poids", 1) for s in selecteurs or [])


def conserver_selecteurs(signalement, details, noms_categories):
    """
    Enregistre les selecteurs trouves (CriticiteDetail.details) sur le
    signalement, SEULEMENT si leur score depasse celui de la liste deja
    enregistree : comme la criticite, elle ne redescend jamais. Une lecture
    moins complete (titre seul d'une page de detail perdue, annonce
    raccourcie par la source) n'ecrase donc pas les selecteurs deja
    trouves.

    noms_categories : {categorie_id: nom}, fige avec la liste.
    """
    if details is None:
        return False
    actuels = lire_selecteurs(signalement)
    if actuels is not None and score_de(details) <= score_de(actuels):
        return False
    signalement.selecteurs_trouves = json.dumps([
        {**detail, "categorie": noms_categories.get(detail.get("categorie_id"))}
        for detail in details
    ], ensure_ascii=False)
    return True


def reference_exploitable(connecteur, reference) -> bool:
    """
    Une reference designe-t-elle UNE annonce ? Pas quand la collecte s'est
    rabattue sur l'URL du listing, faute de lien propre a l'annonce
    (orion_leaks, cmd_organization).
    """
    return bool(reference) and reference not in ("unknown", connecteur.TARGET_URL)


def signalements_a_completer(session, source, connecteur, tous=False) -> tuple:
    """
    Signalements de la source auxquels il manque le texte de l'annonce ou
    ses selecteurs, groupes par reference : ({reference: [signalements]},
    nombre de signalements ecartes faute de reference exploitable).

    tous : tous les signalements de la source, complets ou non.
    """
    requete = session.query(SourceReference).options(
        joinedload(SourceReference.exposition)
    ).filter(SourceReference.source_id == source.id)
    if not tous:
        requete = requete.filter(
            (SourceReference.date_texte_brut.is_(None))
            | (SourceReference.selecteurs_trouves.is_(None))
        )

    par_reference, ecartes = {}, 0
    for signalement in requete.all():
        if reference_exploitable(connecteur, signalement.reference_source):
            par_reference.setdefault(signalement.reference_source, []).append(signalement)
        else:
            ecartes += 1
    return par_reference, ecartes


def identifiants_des_references(connecteur, references) -> set:
    """
    Identifiants de crawl possibles de ces references : la reference
    elle-meme et son chemin interne (identifiant_entree d'une annonce dont
    le lien est une URL absolue du domaine surveille).
    """
    identifiants = set()
    for reference in references:
        identifiants.add(reference)
        chemin = connecteur._chemin_interne(reference)
        if chemin:
            identifiants.add(chemin)
    return identifiants
