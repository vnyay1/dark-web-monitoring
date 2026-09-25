"""
Outil de reconnaissance de la structure d'une source (usage manuel).

PROBLEME RESOLU - on ne peut pas ecrire le parse_detail() d'un connecteur
sans avoir vu la structure HTML reelle de sa page de detail, et CN-05
interdit d'enregistrer cette page sur disque pour l'etudier.

SOLUTION - ce module n'affiche JAMAIS le contenu : il rend un SQUELETTE
STRUCTUREL. Pour chaque noeud, on imprime son tag, son id, ses classes,
et - a la place du texte - uniquement sa LONGUEUR. Les href/src/onclick
sont reduits a leur FORME (relatif / meme-domaine / AUTRE-DOMAINE), avec
les identifiants numeriques masques. C'est suffisant pour ecrire un
selecteur CSS, et cela ne contient litteralement aucune donnee divulguee.

Le resultat peut donc etre recopie dans le docstring du connecteur, comme
le font deja tous les connecteurs existants ("structure confirmee en
conditions reelles").

REGLES OPERATIONNELLES
- Ne jamais rediriger la sortie vers un fichier (">", "| tee"), et ne pas
  l'executer dans un terminal dont la journalisation est active. Le
  squelette est anodin, mais la discipline doit rester uniforme (CN-05).
- Ce module n'ecrit rien en base : il ne pollue pas le registre de crawl.
- Il ne suit jamais un lien que url_detail() n'aurait pas autorise, et
  refuse en dur de suivre les liens de cmd_organization (ils pointent
  vers le site officiel de la victime : hors perimetre, et contraire a la
  collecte passive CN-09/CN-10).

Usage :
    python -m app.connectors.reconnaissance --source payload --phase listing
    python -m app.connectors.reconnaissance --source payload --phase detail --index 0
    python -m app.connectors.reconnaissance --source payload --phase formes
    python -m app.connectors.reconnaissance --source blackwater --phase dates
    python -m app.connectors.reconnaissance --source safepay --phase detail --profondeur 14
    python -m app.connectors.reconnaissance --source safepay --phase dates --detail 3
    python -m app.connectors.reconnaissance --source blackwater --phase pages --max 3
    python -m app.connectors.reconnaissance --source everest --phase correspondance \\
        --entree /news/cca-bank --selecteurs "Cameroun,CNI,RCCM"

La phase "dates" est la seule a imprimer du texte de la page : UNIQUEMENT la
chaine de date de chaque entree, et ce qu'en tire parser_date(). Une date de
publication est une metadonnee autorisee (CN-03) ; aucun autre champ n'est
affiche. Elle sert a ecrire les DATE_FORMATS des connecteurs.

La phase "correspondance" rejoue sur UNE entree toute la chaine d'analyse du
pipeline et dit pourquoi elle a compte tant de selecteurs. Elle imprime des
termes du CATALOGUE (jamais un segment de la page), des compteurs, des
positions, des longueurs et des dates. Elle LIT la base (catalogue, reglages,
registre, expositions) sans jamais y ecrire.
"""

import argparse
import logging
import re
from urllib.parse import parse_qsl, urlparse

from bs4 import BeautifulSoup

from app.connectors import connecteur_par_nom

logger = logging.getLogger(__name__)


# Sources dont les liens par entree ne doivent JAMAIS etre suivis, meme en
# reconnaissance manuelle.
SOURCES_LIENS_INTERDITS = {
    "cmd_organization": "le lien est le site officiel de la victime (hors perimetre, collecte passive)",
    "orion_leaks": "le lien pointe vers les donnees divulguees (CN-04)",
}

# Libelles trahissant un lien de telechargement plutot qu'une page d'annonce.
MOTS_TELECHARGEMENT = ("download", "mirror", "torrent", "magnet", "get file", "dump")

# Hebergeurs de donnees connus : un lien de detail qui pointe la n'est pas
# une page de publication.
HEBERGEURS_DONNEES = ("mega.", "anonfiles", "gofile", "mediafire", "dropbox",
                      "pixeldrain", "send.", "transfer.")

MASQUE_NOMBRES = re.compile(r"\d+")


def _forme_url(valeur, netloc_source):
    """
    Reduit une URL a sa FORME. Ne restitue jamais une URL exploitable :
    les identifiants numeriques sont masques et les domaines tiers ne sont
    pas nommes.
    """
    if not valeur:
        return None

    valeur = valeur.strip()

    if "window.open" in valeur:
        interne = re.search(r"""window\.open\(\s*['"]([^'"]+)['"]""", valeur)
        cible = _forme_url(interne.group(1), netloc_source) if interne else "?"
        return f"js:window.open -> {cible}"

    if valeur.startswith(("javascript:", "#", "mailto:")):
        return "inerte"

    analyse = urlparse(valeur)
    chemin = MASQUE_NOMBRES.sub("<num>", analyse.path or "/") + _forme_requete(analyse.query)

    if not analyse.netloc:
        return f"relatif:{chemin}"

    if netloc_source and analyse.netloc == netloc_source:
        return f"absolu:meme-domaine {chemin}"

    if any(h in analyse.netloc.lower() for h in HEBERGEURS_DONNEES):
        return "absolu:AUTRE-DOMAINE (HEBERGEUR DE DONNEES)"

    return "absolu:AUTRE-DOMAINE"


def _forme_requete(requete):
    """
    Chaine de requete reduite a sa FORME : noms de parametres conserves
    (c'est eux qui revelent une pagination, "?page=2"), valeurs masquees.
    Une valeur numerique devient <num>, toute autre valeur sa seule
    longueur : un parametre de recherche peut contenir un nom d'entite.
    """
    if not requete:
        return ""
    parties = []
    for nom, valeur in parse_qsl(requete, keep_blank_values=True):
        if valeur.isdigit():
            parties.append(f"{nom}=<num>")
        elif valeur:
            parties.append(f"{nom}=<texte:{len(valeur)}>")
        else:
            parties.append(nom)
    return "?" + "&".join(parties)


def _longueur_texte_propre(noeud):
    """Longueur du texte porte DIRECTEMENT par le noeud (pas ses enfants)."""
    return sum(len(chaine.strip()) for chaine in noeud.find_all(string=True, recursive=False))


def _signature(noeud, netloc_source):
    """Description structurelle d'un noeud, sans aucun contenu."""
    parties = [noeud.name]

    if noeud.get("id"):
        parties.append("#" + MASQUE_NOMBRES.sub("<num>", noeud.get("id")))

    classes = noeud.get("class") or []
    if classes:
        parties.append("." + ".".join(classes))

    attributs = []
    for attribut in ("href", "src", "onclick"):
        forme = _forme_url(noeud.get(attribut), netloc_source)
        if forme:
            attributs.append(f"{attribut}={forme}")
    if attributs:
        parties.append("[" + " ".join(attributs) + "]")

    longueur = _longueur_texte_propre(noeud)
    if longueur:
        parties.append(f"[text:{longueur}]")

    return " ".join(parties)


def resumer_structure(html, profondeur_max=6, max_groupes=10, netloc_source=""):
    """
    Rend le squelette structurel d'un document : tags, id, classes, formes
    d'URL et longueurs de texte. Aucun contenu textuel n'est restitue.

    Les enfants de meme signature sont regroupes (xN) et un seul
    representant est explore : c'est exactement ce qu'il faut pour
    reconnaitre une grille de cards.
    """
    soup = BeautifulSoup(html, "html.parser")
    racine = soup.body or soup
    lignes = []

    def explorer(noeud, profondeur):
        if profondeur > profondeur_max:
            return

        groupes = {}
        for enfant in noeud.find_all(recursive=False):
            if enfant.name in ("script", "style", "noscript"):
                continue
            signature = _signature(enfant, netloc_source)
            if signature not in groupes:
                groupes[signature] = [0, enfant]
            groupes[signature][0] += 1

        for signature, (nombre, representant) in list(groupes.items())[:max_groupes]:
            suffixe = f"  (x{nombre})" if nombre > 1 else ""
            lignes.append("  " * profondeur + signature + suffixe)
            explorer(representant, profondeur + 1)

    explorer(racine, 0)
    return "\n".join(lignes)


def _recuperer(connecteur, url, tentatives=1):
    """
    Requete rate-limitee (FR-06), en renvoyant la reponse complete. Passe
    par BaseConnector.requete() : memes delais et memes reessais que la
    collecte, la reconnaissance n'a pas de regime de faveur.
    """
    # L'envoi est journalise par requete() elle-meme, APRES le delai FR-06 :
    # un log pose ici, avant l'attente, laissait croire a une requete
    # immediate.
    return connecteur.requete(url, tentatives=tentatives)


def _url_de_la_page(connecteur, page):
    """
    URL de la page de listing numero 'page', en suivant la pagination du
    connecteur (une requete par page precedente, delai FR-06 compris).
    """
    url = connecteur.TARGET_URL
    for courante in range(1, page):
        raw = _recuperer(connecteur, url).text
        try:
            url = connecteur.url_page_suivante(raw, courante)
        finally:
            del raw  # CN-05
        if not url:
            raise SystemExit(f"La source ne compte que {courante} page(s).")
    return url


def _verdict_liceite(connecteur, reponse, url_detail, libelle_lien):
    """
    Repond a la question qui decide si une source peut passer en
    SUPPORTE_DETAIL : cette page est-elle une page d'annonce exploitable,
    ou un telechargement / un site tiers ?
    """
    netloc_source = urlparse(connecteur.TARGET_URL or "").netloc
    netloc_cible = urlparse(url_detail).netloc or netloc_source
    type_contenu = (reponse.headers.get("Content-Type") or "").split(";")[0].strip()
    texte_visible = BeautifulSoup(reponse.text, "html.parser").get_text(" ", strip=True)

    controles = [
        ("Content-Type est du HTML",
         type_contenu.startswith("text/html"),
         f"Content-Type = {type_contenu or 'inconnu'}"),
        ("Meme domaine que la source surveillee",
         netloc_cible == netloc_source,
         "domaine identique" if netloc_cible == netloc_source else "DOMAINE TIERS"),
        ("Le libelle du lien n'evoque pas un telechargement",
         not any(mot in (libelle_lien or "").lower() for mot in MOTS_TELECHARGEMENT),
         f"libelle = {(libelle_lien or '-')[:40]!r}"),
        ("La page contient du texte narratif (> 500 car.)",
         len(texte_visible) > 500,
         f"{len(texte_visible)} caracteres de texte visible"),
    ]

    print()
    print("VERDICT DE LICEITE")
    print("-" * 64)
    for intitule, resultat, detail in controles:
        print(f"  [{'OK ' if resultat else 'NON'}] {intitule:<46} {detail}")

    if all(r for _, r, _ in controles):
        print("\n  => Page d'annonce exploitable : SUPPORTE_DETAIL peut etre active.")
    else:
        print("\n  => NE PAS activer SUPPORTE_DETAIL : la source reste en listing-only.")


def phase_listing(connecteur, profondeur=6):
    """Squelette de la page de listing + detection heuristique d'une pagination."""
    netloc_source = urlparse(connecteur.TARGET_URL or "").netloc
    reponse = _recuperer(connecteur, connecteur.TARGET_URL)

    print(f"\nHTTP {reponse.status_code} | {reponse.headers.get('Content-Type', '?')} "
          f"| {len(reponse.text)} caracteres")

    entrees = connecteur.parse(reponse.text).get("entries", [])
    print(f"parse() actuel : {len(entrees)} entree(s) extraite(s) de cette page")

    print("\nSQUELETTE STRUCTUREL")
    print("-" * 64)
    print(resumer_structure(reponse.text, profondeur_max=profondeur, netloc_source=netloc_source))

    print("\nCANDIDATS PAGINATION")
    print("-" * 64)
    soup = BeautifulSoup(reponse.text, "html.parser")
    candidats = soup.select(
        "a[rel=next], .pagination a, nav a, a[href*='page'], "
        "a[id*='pager'], a[class*='next'], a[class*='older']"
    )
    if not candidats:
        print("  aucun candidat detecte : la source liste probablement tout en une page")
    for lien in candidats[:10]:
        print(f"  {_signature(lien, netloc_source)}  libelle={lien.get_text(strip=True)[:30]!r}")


def phase_formes(connecteur):
    """N'analyse QUE la nature des liens par entree, sans rien visiter."""
    netloc_source = urlparse(connecteur.TARGET_URL or "").netloc
    reponse = _recuperer(connecteur, connecteur.TARGET_URL)
    entrees = connecteur.parse(reponse.text).get("entries", [])

    print(f"\nFORME DES LIENS PAR ENTREE ({len(entrees)} entree(s))")
    print("-" * 64)
    for entree in entrees[:10]:
        lien = entree.get("lien_detail")
        print(f"  {_forme_url(lien, netloc_source) or 'aucun lien'}")

    print()
    print(f"  SUPPORTE_DETAIL actuel : {connecteur.SUPPORTE_DETAIL}")
    print(f"  url_detail() de la 1re entree : "
          f"{connecteur.url_detail(entrees[0]) if entrees else '-'}")


# Libelle de champ affiche par un site : capitales suivies de deux-points
# ("DISCOVERY DATE:", "AUDIT ID:"). Seul le libelle est retenu, jamais la
# valeur qui le suit.
LIBELLE_CHAMP = re.compile(r"^\s*([A-Z][A-Z0-9 _/-]{1,40}?)\s*:")


def _libelles_de_champs(html):
    """Libelles de champs de la page et leur nombre d'occurrences."""
    compte = {}
    for ligne in BeautifulSoup(html, "html.parser").get_text("\n").splitlines():
        trouve = LIBELLE_CHAMP.match(ligne)
        if trouve:
            libelle = trouve.group(1).strip()
            compte[libelle] = compte.get(libelle, 0) + 1
    return sorted(compte.items(), key=lambda kv: -kv[1])


def phase_dates(connecteur, limite=15, pages_detail=0, page=1):
    """
    Chaines de date brutes des entrees du listing, et leur interpretation.

    N'imprime RIEN d'autre que la date : ni nom d'entite, ni description.
    Seule exception, les LIBELLES des champs de la page (sans leur valeur),
    pour comprendre ou se trouve la date d'une annonce qui n'en montre pas.

    page : page de listing a examiner (pagination du connecteur suivie,
    une requete par page, delai FR-06 compris).
    """
    from app.connectors.dates import CLES_DATE, parser_date

    reponse = _recuperer(connecteur, _url_de_la_page(connecteur, page))
    entrees = connecteur.parse(reponse.text).get("entries", [])
    libelles = _libelles_de_champs(reponse.text)

    print()
    print(f"PAGE {page} : {len(entrees)} entree(s) dans le listing ; "
          f"{min(limite, len(entrees))} affichee(s).")
    print(f"DATE_FORMATS actuels : {connecteur.DATE_FORMATS or '(aucun, formats communs seulement)'}")
    print("-" * 64)

    # Meme borne qu'en collecte pour les annonces non datees (cf.
    # BaseConnector._poser_dates_plafond). Calculee sur cette seule page :
    # une annonce non datee en tete de page N serait, en collecte, bornee
    # par la derniere annonce datee de la page N-1.
    if connecteur.LISTING_CHRONOLOGIQUE:
        connecteur._poser_dates_plafond(entrees)

    reconnues = 0
    for index, entree in enumerate(entrees[:limite]):
        cle, brute = next(
            ((c, entree.get(c)) for c in CLES_DATE if entree.get(c)), (None, None)
        )
        if brute is None:
            plafond = entree.get("date_plafond")
            suite = (
                f" -> plafond {plafond:%Y-%m-%d} (date de l'annonce datee precedente)"
                if plafond else ""
            )
            print(f"  [{index:>2}] aucune date dans le listing{suite}")
            continue

        interpretee = parser_date(brute, connecteur.DATE_FORMATS, source=connecteur.SOURCE_NAME)
        reconnues += interpretee is not None
        verdict = interpretee.isoformat(sep=" ") if interpretee else "NON RECONNUE"
        print(f"  [{index:>2}] {cle:17} {str(brute)[:50]!r:54} -> {verdict}")

    print("-" * 64)
    print(f"  {reconnues} date(s) reconnue(s) sur {min(limite, len(entrees))}.")

    if libelles:
        print()
        print("LIBELLES DE CHAMPS DE LA PAGE (valeurs non affichees)")
        print("-" * 64)
        for libelle, nombre in libelles:
            print(f"  {libelle!r:44} x{nombre}")

    if not connecteur.SUPPORTE_DETAIL:
        return
    if not pages_detail:
        print("  Ce connecteur lit aussi ses pages de detail : relancer avec --detail 3")
        print("  pour y verifier les dates (une requete par page, delai FR-06 compris).")
        return

    # Pages de detail : meme regle que la collecte, url_detail() decide seule
    # de ce qui est visitable, et seule la date est affichee.
    print()
    print(f"DATES DES PAGES DE DETAIL ({pages_detail} au plus)")
    print("-" * 64)
    visitees = 0
    for index, entree in enumerate(entrees):
        if visitees >= pages_detail:
            break
        url = connecteur.url_detail(entree)
        if not url:
            continue
        visitees += 1
        raw = _recuperer(connecteur, url).text
        try:
            brute = (connecteur.parse_detail(raw, entree) or {}).get("date_publication")
        finally:
            del raw  # CN-05
        interpretee = parser_date(brute, connecteur.DATE_FORMATS, source=connecteur.SOURCE_NAME)
        verdict = interpretee.isoformat(sep=" ") if interpretee else ("aucune" if brute is None else "NON RECONNUE")
        print(f"  [{index:>2}] {str(brute)[:50]!r:54} -> {verdict}")


def phase_pages(connecteur, maximum=3):
    """
    Suit la pagination telle que l'implemente le connecteur
    (url_page_suivante) et resume chaque page : forme de l'URL, nombre
    d'annonces, plage de dates. Aucun autre contenu n'est imprime.
    Sert a valider un connecteur pagine avant de l'activer en collecte.
    """
    if not connecteur.SUPPORTE_PAGINATION:
        print("\nCe connecteur ne declare pas de pagination (SUPPORTE_PAGINATION = False) :")
        print("seule la page 1 est lue en collecte. Voir --phase listing, CANDIDATS PAGINATION.")
        return

    netloc_source = urlparse(connecteur.TARGET_URL or "").netloc
    url = connecteur.TARGET_URL
    stats, erreurs = {"details_ok": 0, "details_echec": 0}, {}
    print()
    for page in range(1, maximum + 1):
        raw = _recuperer(connecteur, url).text
        try:
            entrees = connecteur.parse(raw).get("entries", [])
            suivante = connecteur.url_page_suivante(raw, page)
        finally:
            del raw  # CN-05

        print(f"  page {page} : {_forme_url(url, netloc_source)}")
        if connecteur.DATE_SUR_DETAIL:
            # Meme sonde qu'en collecte : la derniere annonce de la page.
            for e in entrees:
                e["identifiant_entree"] = connecteur.identifiant_entree(e)
                e["niveau_detail"] = "listing"
            sonde = connecteur._entree_a_sonder(entrees, set())
            date = connecteur.dater_par_sonde(sonde, stats, erreurs) if sonde else None
            lue = f"{date:%d/%m/%Y}" if date else "illisible"
            print(f"           {len(entrees)} annonce(s), derniere annonce datee "
                  f"par sa page de detail : {lue}")
        else:
            dates = connecteur.dates_lisibles(entrees)
            plage = (
                f"{min(dates):%d/%m/%Y} -> {max(dates):%d/%m/%Y}" if dates
                else "aucune date lisible"
            )
            ordre = ""
            if len(dates) > 1:
                ordre = (", de la plus recente a la plus ancienne"
                         if dates == sorted(dates, reverse=True) else ", ORDRE NON CHRONOLOGIQUE")
            print(f"           {len(entrees)} annonce(s), {len(dates)} datee(s), {plage}{ordre}")

        if not suivante:
            print("  -> fin de la pagination (url_page_suivante renvoie None)")
            return
        url = suivante
    print(f"  -> arret apres {maximum} page(s) (--max)")


def phase_detail(connecteur, index, profondeur=6):
    """Squelette de la page de detail d'UNE entree, avec verdict de liceite."""
    if connecteur.SOURCE_NAME in SOURCES_LIENS_INTERDITS:
        raise SystemExit(
            f"REFUS : les liens de {connecteur.SOURCE_NAME} ne doivent jamais etre "
            f"suivis - {SOURCES_LIENS_INTERDITS[connecteur.SOURCE_NAME]}."
        )

    netloc_source = urlparse(connecteur.TARGET_URL or "").netloc
    reponse_listing = _recuperer(connecteur, connecteur.TARGET_URL)
    entrees = connecteur.parse(reponse_listing.text).get("entries", [])

    if index >= len(entrees):
        raise SystemExit(f"Index {index} hors limites : {len(entrees)} entree(s).")

    entree = entrees[index]
    lien = entree.get("lien_detail")
    if not lien:
        raise SystemExit("Cette entree n'expose aucun lien de detail.")

    url = connecteur.url_detail(entree)
    if not url:
        # url_detail() n'est pas encore implemente : on reconstruit l'URL pour
        # la QUALIFIER, ce qui est precisement le but de la reconnaissance.
        base = (connecteur.TARGET_URL or "").rstrip("/")
        url = lien if urlparse(lien).netloc else base + "/" + lien.lstrip("/")
        print(f"\nATTENTION : url_detail() renvoie None pour ce connecteur.")
        print(f"URL reconstruite pour qualification : forme "
              f"{_forme_url(url, netloc_source)}")

    reponse = _recuperer(connecteur, url)

    print(f"\nHTTP {reponse.status_code} | {reponse.headers.get('Content-Type', '?')} "
          f"| {len(reponse.text)} caracteres")

    print("\nSQUELETTE STRUCTUREL DE LA PAGE DE DETAIL")
    print("-" * 64)
    print(resumer_structure(reponse.text, profondeur_max=profondeur, netloc_source=netloc_source))

    _verdict_liceite(connecteur, reponse, url, entree.get("nom_entite_detecte"))


# ----------------------------------------------------------------------
# Phase "correspondance" : pourquoi une entree a-t-elle compte tant de
# selecteurs ?
# ----------------------------------------------------------------------

# Seules valeurs JSON affichees telles quelles : des dates de publication,
# metadonnee autorisee (CN-03). Toute autre valeur est reduite a son type
# et a sa longueur.
CLES_JSON_DATE = ("date", "created_at", "updated_at", "published_at", "publication_date")

# Une cle JSON qui n'a pas la forme d'un nom de champ peut etre une DONNEE
# (un nom de fichier servant de cle, par exemple) : elle est masquee.
CLE_JSON_LISIBLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
MAX_CLES_JSON = 40

# Au-dela, les dates d'un meme chemin JSON sont resumees par leur plage.
MAX_DATES_DETAILLEES = 10


def _cle_json(cle):
    cle = str(cle)
    return cle if CLE_JSON_LISIBLE.match(cle) else f"<cle:{len(cle)}>"


def _decrire_json(valeur, cle=None):
    """Type et taille d'une valeur JSON, sans la valeur (dates exceptees)."""
    if isinstance(valeur, dict):
        return f"objet ({len(valeur)} cle(s))"
    if isinstance(valeur, list):
        textes = [v for v in valeur if isinstance(v, str)]
        total = f", texte total {sum(len(t) for t in textes)}" if textes else ""
        return f"liste ({len(valeur)} element(s){total})"
    if isinstance(valeur, str):
        return f"date {valeur[:40]!r}" if cle in CLES_JSON_DATE else f"texte:{len(valeur)}"
    if valeur is None:
        return "null"
    if isinstance(valeur, bool):
        return "booleen"
    # Nombre : valeur non affichee (un montant revendique, par exemple).
    return type(valeur).__name__


def resumer_json(donnees, profondeur_max=6):
    """
    Squelette d'une structure JSON : cles, types et longueurs, jamais les
    valeurs (dates exceptees). Pendant de resumer_structure() pour les sites
    qui livrent leur contenu en JSON (everest, Inertia) ; comme lui, une
    liste n'est exploree qu'a travers son premier element.
    """
    lignes = []

    def explorer(valeur, profondeur):
        if profondeur > profondeur_max:
            return
        marge = "  " * profondeur
        if isinstance(valeur, dict):
            elements = list(valeur.items())
            for cle, enfant in elements[:MAX_CLES_JSON]:
                lignes.append(f"{marge}{_cle_json(cle)}: {_decrire_json(enfant, cle)}")
                explorer(enfant, profondeur + 1)
            if len(elements) > MAX_CLES_JSON:
                lignes.append(f"{marge}... {len(elements) - MAX_CLES_JSON} cle(s) de plus")
        elif isinstance(valeur, list) and valeur:
            lignes.append(f"{marge}[0]: {_decrire_json(valeur[0])}")
            explorer(valeur[0], profondeur + 1)

    explorer(donnees, 0)
    return "\n".join(lignes)


def _dates_json(donnees) -> dict:
    """Dates du JSON groupees par chemin generique ("props.posts[].date")."""
    groupes = {}

    def explorer(valeur, chemin):
        if isinstance(valeur, dict):
            for cle, enfant in valeur.items():
                sous_chemin = f"{chemin}.{_cle_json(cle)}" if chemin else _cle_json(cle)
                if cle in CLES_JSON_DATE and isinstance(enfant, str):
                    groupes.setdefault(sous_chemin, []).append(enfant)
                else:
                    explorer(enfant, sous_chemin)
        elif isinstance(valeur, list):
            for enfant in valeur:
                explorer(enfant, f"{chemin}[]")

    explorer(donnees, "")
    return groupes


def _trouver_entree(connecteur, identifiant, index, page):
    """Entree du listing a diagnostiquer, preparee comme en collecte."""
    reponse = _recuperer(connecteur, _url_de_la_page(connecteur, page))
    try:
        entrees = connecteur.parse(reponse.text).get("entries", [])
    finally:
        del reponse  # CN-05

    for entree in entrees:
        entree["identifiant_entree"] = (
            entree.get("identifiant_entree") or connecteur.identifiant_entree(entree)
        )
        entree["niveau_detail"] = "listing"

    if identifiant:
        cible = identifiant.strip()
        if not cible.startswith("h:"):
            cible = connecteur._chemin_interne(cible) or cible
        for entree in entrees:
            if entree["identifiant_entree"] == cible:
                return entree
        raise SystemExit(
            f"Entree {cible!r} introuvable parmi les {len(entrees)} entree(s) de la page "
            f"{page}. L'identifiant est la colonne Reference du signalement."
        )

    if index >= len(entrees):
        raise SystemExit(f"Index {index} hors limites : {len(entrees)} entree(s).")
    return entrees[index]


def _visiter_detail(connecteur, entree) -> dict:
    """
    Visite la page de detail comme en collecte et fusionne son contenu dans
    l'entree. Renvoie ce que le diagnostic doit savoir, dont le contenu
    DECODE de la page (compteurs uniquement, jamais imprime).
    """
    import html
    import json

    from app.connectors.dates import CLES_DATE

    visite = {"url": None, "erreur": None, "texte_detail": "", "dates_detail": {},
              "page": "", "json": None}
    if not connecteur.SUPPORTE_DETAIL or not connecteur.url_detail(entree):
        return visite

    visite["url"] = connecteur.url_detail(entree)
    raw = _recuperer(connecteur, visite["url"]).text
    try:
        extraire = getattr(connecteur, "_extraire_json_inertia", None)
        if extraire is not None:
            try:
                visite["json"] = extraire(raw)
                visite["page"] = json.dumps(visite["json"], ensure_ascii=False)
            except Exception:
                pass
        if not visite["page"]:
            visite["page"] = html.unescape(raw)
        try:
            enrichi = connecteur.parse_detail(raw, entree) or {}
        except Exception as erreur:
            visite["erreur"] = connecteur._libelle_erreur(erreur)
            return visite
    finally:
        del raw  # CN-05

    visite["texte_detail"] = enrichi.get("texte_brut") or ""
    visite["dates_detail"] = {c: enrichi.get(c) for c in CLES_DATE if enrichi.get(c)}
    connecteur._fusionner_detail(entree, enrichi)
    return visite


def _compter(texte, terme):
    """(occurrences en casse exacte, occurrences en une autre casse)."""
    exactes = texte.count(terme)
    return exactes, max(0, texte.lower().count(terme.lower()) - exactes)


def phase_correspondance(connecteur, identifiant=None, index=0, page=1, termes=()):
    """
    Rejoue en memoire, sur UNE entree, toute la chaine d'analyse du pipeline
    (fusion listing + detail, normalisation, fenetre de dates, matching,
    faux positifs, criticite) et dit pourquoi elle a produit tant de
    selecteurs.

    N'imprime que des termes du catalogue, des compteurs, des positions,
    des longueurs et des dates : jamais le texte de la page (CN-04/CN-05).
    N'ecrit rien en base : catalogue, reglages, registre et expositions
    sont seulement lus.
    """
    from rapidfuzz import fuzz
    from sqlalchemy.orm import joinedload

    from app.connectors.base_connector import LIMITE_TEXTE_BRUT
    from app.connectors.dates import CLES_DATE, parser_date
    from app.db import get_session, init_db
    from app.matching.criticite import calculer_criticite
    from app.matching.engine import (
        SEUIL_LONGUEUR_MOT_ENTIER, _pattern_mot_entier, match_text_against_catalogue,
    )
    from app.matching.exclusion import (
        motif_exclusion_configuree, motif_exclusion_entite, motif_rejet_structurel,
    )
    from app.models import (
        EntreeCollectee, Exposition, Selecteur, Source, SourceReference, StatutDetailEntree,
    )
    from app.pipeline import _normaliser_entry, _seuils_du_run

    init_db()
    causes = []

    def lire(valeur):
        return parser_date(valeur, connecteur.DATE_FORMATS, source=connecteur.SOURCE_NAME,
                           journaliser=False)

    # --- Entree, telle que la collecte la voit ---------------------------
    entree = _trouver_entree(connecteur, identifiant, index, page)
    texte_listing = entree.get("texte_brut") or ""
    dates_listing = {c: entree.get(c) for c in CLES_DATE if entree.get(c)}

    visite = _visiter_detail(connecteur, entree)
    texte_complet = connecteur.texte_fusionne(texte_listing, visite["texte_detail"])
    normalisee = _normaliser_entry(entree, connecteur)
    texte_analyse = normalisee["texte_brut"]
    seuils = _seuils_du_run()

    print()
    print("ENTREE")
    print("-" * 64)
    print(f"  identifiant      : {normalisee['identifiant_entree']}")
    print(f"  nom d'entite     : {normalisee['nom_entite']}")
    if visite["url"] is None:
        etat_detail = "non visitee (le connecteur n'a pas de page de detail pour cette entree)"
        causes.append("Page de detail non visitee : seul le texte du listing est analyse.")
    elif visite["erreur"]:
        etat_detail = f"ECHEC de parse_detail : {visite['erreur']}"
        causes.append(
            f"[E/F] parse_detail echoue ({visite['erreur']}) : en collecte, l'entree part en "
            f"echec de detail et n'est pas analysee ; au bout de trois echecs, seul le titre "
            f"du listing l'est."
        )
    else:
        etat_detail = "visitee et lue"
    print(f"  page de detail   : {etat_detail}")
    print(f"  texte listing    : {len(texte_listing)} car.")
    print(f"  texte detail     : {len(visite['texte_detail'])} car.")
    print(f"  texte complet    : {len(texte_complet)} car.")
    coupe = len(texte_complet) - len(texte_analyse)
    print(f"  texte analyse    : {len(texte_analyse)} car."
          + (f" (COUPE a {LIMITE_TEXTE_BRUT} : {coupe} car. jamais analyses)" if coupe > 0 else ""))

    # --- Dates et fenetre d'analyse --------------------------------------
    print()
    print("DATES")
    print("-" * 64)
    for origine, dates in (("listing", dates_listing), ("detail", visite["dates_detail"])):
        for cle, brute in dates.items():
            lue = lire(brute)
            print(f"  {origine:8} {cle:17} {str(brute)[:40]!r:44} -> "
                  f"{lue.isoformat(sep=' ') if lue else 'NON RECONNUE'}")
    cle_retenue = next((c for c in CLES_DATE if entree.get(c)), None)
    date_reference = normalisee["date_publication"] or normalisee.get("date_plafond")
    print(f"  retenue          : {cle_retenue or 'aucune'} (ordre {', '.join(CLES_DATE)})"
          f" -> {date_reference.isoformat(sep=' ') if date_reference else 'aucune date'}")
    print(f"  debut de periode : {seuils['date_limite']:%Y-%m-%d %H:%M} "
          f"({seuils['periode_jours']} jours)")

    hors_periode = date_reference is not None and date_reference < seuils["date_limite"]
    print(f"  verdict          : {'HORS PERIODE - ecartee AVANT le matching' if hors_periode else 'dans la periode'}")
    if hors_periode:
        date_listing = lire(next(iter(dates_listing.values()), None))
        message = "[A] HORS PERIODE : en collecte, l'entree enrichie est ecartee avant le matching."
        if date_listing is not None and date_listing >= seuils["date_limite"]:
            message += (" Le listing SEUL etait dans la periode : c'est la date de la page de "
                        "detail qui l'en fait sortir.")
        causes.append(message)

    if visite["json"] is not None:
        for chemin, valeurs in _dates_json(visite["json"]).items():
            lues = [lire(v) for v in valeurs]
            if len(valeurs) <= MAX_DATES_DETAILLEES:
                for i, (brute, lue) in enumerate(zip(valeurs, lues)):
                    print(f"  json     {chemin} #{i} {brute[:30]!r} -> "
                          f"{lue.isoformat(sep=' ') if lue else 'NON RECONNUE'}")
            else:
                valides = [d for d in lues if d]
                plage = f"de {min(valides):%Y-%m-%d} a {max(valides):%Y-%m-%d}" if valides else "illisibles"
                print(f"  json     {chemin} : {len(valeurs)} dates, {plage}")

    session = get_session()
    try:
        # Lue ici et non plus au moment du registre : les regles d'exclusion
        # peuvent porter sur UNE source, il faut donc la connaitre avant de
        # rejouer le filtrage des faux positifs.
        source = session.query(Source).filter_by(nom=connecteur.SOURCE_NAME).first()
        source_id = source.id if source is not None else None

        # --- Matching, faux positifs, criticite ---------------------------
        catalogue = session.query(Selecteur).options(joinedload(Selecteur.categorie)).all()
        actifs = [s for s in catalogue if s.actif]
        noms_categories = {s.categorie_id: s.categorie.nom for s in catalogue}

        trouves = match_text_against_catalogue(texte_analyse, actifs)
        # Au-dela de la coupure : exact et casse seulement, cela suffit a
        # dire qu'un selecteur s'y trouve.
        au_dela = (
            match_text_against_catalogue(texte_complet, actifs, enable_fuzzy=False)
            if coupe > 0 else []
        )
        motif_liste = motif_exclusion_configuree(texte_analyse, session, source_id)
        motif_entite = motif_exclusion_entite(normalisee["nom_entite"], session, source_id)

        par_valeur = {}
        retenus = []
        for m in trouves:
            info = par_valeur.setdefault(m.selecteur_valeur, {
                "categorie": m.selecteur_categorie, "poids": m.selecteur_poids,
                "niveaux": {}, "motifs": {}, "retenues": 0, "apres": None,
            })
            info["niveaux"][m.type_correspondance] = info["niveaux"].get(m.type_correspondance, 0) + 1
            motif = motif_rejet_structurel(texte_analyse, m)
            if motif:
                info["motifs"][motif] = info["motifs"].get(motif, 0) + 1
            else:
                info["retenues"] += 1
                retenus.append(m)
        for m in au_dela:
            if m.selecteur_valeur in par_valeur and par_valeur[m.selecteur_valeur]["apres"] is None:
                continue
            info = par_valeur.setdefault(m.selecteur_valeur, {
                "categorie": m.selecteur_categorie, "poids": m.selecteur_poids,
                "niveaux": {}, "motifs": {}, "retenues": 0, "apres": m.position,
            })
            info["apres"] = min(info["apres"], m.position)

        if motif_liste is not None:
            retenus = []
        detail = calculer_criticite(retenus)

        print()
        print(f"SELECTEURS DU CATALOGUE TROUVES ({len(actifs)} actifs ; xN = poids)")
        print("-" * 64)
        if not par_valeur:
            print("  aucun")
        for valeur, info in par_valeur.items():
            categorie = noms_categories.get(info["categorie"], "?")[:18]
            if info["poids"] > 1:
                categorie += f" x{info['poids']}"
            niveaux = ", ".join(f"{n} x{c}" for n, c in info["niveaux"].items()) or "-"
            if info["apres"] is not None:
                verdict = f"APRES LA COUPURE (1re position {info['apres']})"
            elif info["retenues"]:
                verdict = "RETENU" + (" (mais texte exclu, voir plus bas)" if motif_liste else "")
            else:
                verdict = "REJETE " + "; ".join(f"x{n} : {motif}" for motif, n in info["motifs"].items())
            print(f"  {valeur[:26]!r:28} {categorie:23} {niveaux:24} {verdict}")

        if motif_liste is not None:
            print(f"\n  TEXTE ENTIEREMENT EXCLU par la liste d'exclusion (motif {motif_liste!r})")
            causes.append(f"Texte exclu par la liste d'exclusion des analystes (motif {motif_liste!r}).")

        # La regle ENTITE ne retire aucun selecteur : comme dans le pipeline,
        # elle ecarte l'entree APRES coup. La criticite affichee plus bas
        # reste donc celle qu'aurait produite l'analyse.
        if motif_entite is not None:
            print(f"\n  NOM D'ENTITE EXCLU par la liste d'exclusion "
                  f"({normalisee['nom_entite']!r}, motif {motif_entite!r})")
            causes.append(
                f"Nom d'entite exclu par la liste d'exclusion des analystes "
                f"(motif {motif_entite!r}) : l'entree est ecartee quelle que soit sa criticite."
            )

        apres = [v for v, i in par_valeur.items() if i["apres"] is not None]
        if apres:
            causes.append(
                f"[B] {len(apres)} selecteur(s) presents seulement apres la coupure a "
                f"{LIMITE_TEXTE_BRUT} car. : {', '.join(apres)}."
            )
        rejetes_pays = [
            v for v, i in par_valeur.items()
            if i["apres"] is None and not i["retenues"] and any("liste de pays" in m for m in i["motifs"])
        ]
        if rejetes_pays:
            causes.append(
                f"[C] Rejete(s) par la regle \"liste de pays\" : {', '.join(rejetes_pays)} "
                f"(pays reperes indiques dans le tableau)."
            )

        print()
        print("CRITICITE QUE PRODUIRAIT L'ANALYSE ACTUELLE")
        print("-" * 64)
        print(f"  {detail.resume()} - selecteurs retenus : {', '.join(detail.selecteurs) or 'aucun'}")
        print(f"  minimum d'enregistrement : {seuils['criticite_minimum']}")

        # --- Termes signales par l'operateur ------------------------------
        if termes:
            print()
            print("TERMES DEMANDES (--selecteurs)")
            print("-" * 64)
        for terme in termes:
            court = len(terme) <= SEUIL_LONGUEUR_MOT_ENTIER
            au_catalogue = [s for s in catalogue if s.valeur == terme]
            if any(s.actif for s in au_catalogue):
                etat = "actif (" + ", ".join(s.categorie.nom for s in au_catalogue if s.actif) + ")"
            elif au_catalogue:
                etat = "INACTIF"
            else:
                etat = "ABSENT du catalogue"
                causes.append(f"{terme!r} n'est pas un selecteur du catalogue (valeur exacte).")
            if au_catalogue and not any(s.actif for s in au_catalogue):
                causes.append(f"{terme!r} est au catalogue mais desactive.")

            regle = " - court : MAJUSCULES exactes et mot isole" if court else ""
            print(f"  {terme!r}{regle} - catalogue : {etat}")
            for libelle, texte in (("page decodee", visite["page"]),
                                   ("texte extrait", texte_complet),
                                   ("texte analyse", texte_analyse)):
                if not texte:
                    continue
                exactes, autre_casse = _compter(texte, terme)
                ligne = f"      {libelle:14}: {exactes} en casse exacte, {autre_casse} en autre casse"
                if court and exactes:
                    isolees = len(_pattern_mot_entier(terme).findall(texte))
                    ligne += f", dont {exactes - isolees} collee(s) a une lettre, un chiffre ou un tiret"
                print(ligne)

            page_ex = _compter(visite["page"], terme)[0] if visite["page"] else 0
            ext_ex, ext_autre = _compter(texte_complet, terme)
            if page_ex > ext_ex:
                causes.append(
                    f"[E] {page_ex - ext_ex} occurrence(s) de {terme!r} (casse exacte) sont dans "
                    f"la page mais pas dans le texte extrait : un champ que parse_detail ne lit "
                    f"pas les porte (voir le squelette JSON)."
                )
            if court and ext_ex + ext_autre:
                isolees = len(_pattern_mot_entier(terme).findall(texte_complet))
                if not isolees:
                    causes.append(
                        f"[D] {terme!r} n'apparait jamais en majuscules exactes et isole : "
                        f"regle voulue pour les acronymes courts."
                    )

        if visite["json"] is not None:
            print()
            print("SQUELETTE JSON DE LA PAGE DE DETAIL (valeurs non affichees)")
            print("-" * 64)
            print(resumer_json(visite["json"].get("props", visite["json"])))

        # --- Registre du crawl et expositions (lecture seule) -------------
        print()
        print("REGISTRE ET EXPOSITIONS (lecture seule)")
        print("-" * 64)
        ligne = None
        liees = []
        if source is not None:
            ligne = session.query(EntreeCollectee).filter_by(
                source_id=source.id, identifiant_entree=normalisee["identifiant_entree"],
            ).first()
            liees = [
                sr.exposition for sr in session.query(SourceReference).filter_by(
                    source_id=source.id, reference_source=normalisee["reference_source"],
                )
            ]

        if ligne is None:
            print("  registre         : entree absente (jamais vue en collecte, ou purgee)")
        else:
            print(f"  registre         : {ligne.statut_detail.value}, "
                  f"{ligne.nb_echecs_detail} echec(s) de detail, "
                  f"a produit une exposition : {'oui' if ligne.a_produit_exposition else 'non'}")
            traite = (
                f"detail traite le {ligne.date_detail_traite:%Y-%m-%d}"
                if ligne.date_detail_traite else "detail jamais traite"
            )
            print(f"                     vue le {ligne.date_premiere_vue:%Y-%m-%d}, {traite}")
            if ligne.statut_detail == StatutDetailEntree.A_TRAITER:
                causes.append(
                    "[F] Page de detail pas encore servie par le budget : l'entree attend sa "
                    "lecture, son titre seul ne produit pas d'exposition."
                )
            elif ligne.statut_detail == StatutDetailEntree.ECHEC:
                causes.append(
                    f"[F] Entree abandonnee apres {ligne.nb_echecs_detail} echecs de detail "
                    f"(erreur dans la page Audit) : seul le titre a ete analyse."
                )

        nom = normalisee["nom_entite"] or ""
        proches = [
            e for e in session.query(Exposition).all()
            if e in liees or (nom and fuzz.ratio(nom.lower(), e.nom_entite.lower()) >= 80)
        ]
        for exposition in proches[:10]:
            lien = " <- signalement de cette entree" if exposition in liees else ""
            print(f"  exposition       : {exposition.nom_entite!r} criticite {exposition.criticite} "
                  f"({exposition.niveau_criticite.value}), {exposition.statut.value}, "
                  f"1re detection {exposition.date_premiere_detection:%Y-%m-%d}, "
                  f"{len(exposition.sources)} signalement(s){lien}")
        if not proches:
            print("  exposition       : aucune au nom proche")

        for exposition in liees:
            if not hors_periode and detail.score > exposition.criticite:
                causes.append(
                    f"L'analyse actuelle donnerait une criticite de {detail.score}, contre "
                    f"{exposition.criticite} enregistree : completer l'exposition, scheduler "
                    f"arrete (python3 -m app.maintenance.recuperer_textes --source "
                    f"{connecteur.SOURCE_NAME} --tous --confirmer). Une remise en file ne suffit "
                    f"pas si l'annonce sort de la periode avant le prochain cycle."
                )
                break
    finally:
        session.close()
        visite["page"] = None  # CN-05 : le contenu decode ne survit pas au diagnostic

    print()
    print("VERDICT")
    print("-" * 64)
    for cause in dict.fromkeys(causes):
        print(f"  - {cause}")
    if not causes:
        print(f"  Aucune cause detectee : la chaine actuelle donne {detail.resume()} "
              f"pour cette entree.")


def _analyser_arguments():
    parseur = argparse.ArgumentParser(
        description="Reconnaissance structurelle d'une source (sortie console uniquement)."
    )
    parseur.add_argument("--source", required=True, help="SOURCE_NAME du connecteur")
    parseur.add_argument("--phase", default="listing",
                         choices=("listing", "detail", "formes", "dates", "pages", "correspondance"))
    parseur.add_argument("--max", type=int, default=3,
                         help="Phase pages : nombre maximum de pages a suivre")
    parseur.add_argument("--index", type=int, default=0,
                         help="Entree du listing dont on inspecte le detail")
    parseur.add_argument("--entree",
                         help="Phase correspondance : identifiant de l'entree (colonne "
                              "Reference du signalement, ex. /news/cca-bank), sinon --index")
    parseur.add_argument("--selecteurs", default="",
                         help="Phase correspondance : termes a compter, separes par des "
                              "virgules (ex. \"Cameroun,CNI,RCCM\")")
    parseur.add_argument("--page", type=int, default=1,
                         help="Phases dates et correspondance : page de listing a examiner")
    parseur.add_argument("--detail", type=int, default=0,
                         help="Phase dates : nombre de pages de detail a lire en plus du listing")
    parseur.add_argument("--profondeur", type=int, default=6,
                         help="Profondeur du squelette (augmenter si le contenu "
                              "est niche dans de nombreux conteneurs)")
    return parseur.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    arguments = _analyser_arguments()

    # Pas de db_session : la reconnaissance n'ecrit rien en base.
    connecteur = connecteur_par_nom(arguments.source)()

    print("=" * 64)
    print(f"RECONNAISSANCE : {connecteur.SOURCE_NAME} (phase {arguments.phase})")
    print("Sortie console uniquement - ne pas rediriger vers un fichier (CN-05).")
    print("=" * 64)

    if arguments.phase == "listing":
        phase_listing(connecteur, arguments.profondeur)
    elif arguments.phase == "formes":
        phase_formes(connecteur)
    elif arguments.phase == "pages":
        phase_pages(connecteur, arguments.max)
    elif arguments.phase == "dates":
        phase_dates(connecteur, pages_detail=arguments.detail, page=arguments.page)
    elif arguments.phase == "correspondance":
        phase_correspondance(
            connecteur, identifiant=arguments.entree, index=arguments.index,
            page=arguments.page,
            termes=[t.strip() for t in arguments.selecteurs.split(",") if t.strip()],
        )
    else:
        phase_detail(connecteur, arguments.index, arguments.profondeur)
