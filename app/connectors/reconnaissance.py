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

La phase "dates" est la seule a imprimer du texte de la page : UNIQUEMENT la
chaine de date de chaque entree, et ce qu'en tire parser_date(). Une date de
publication est une metadonnee autorisee (CN-03) ; aucun autre champ n'est
affiche. Elle sert a ecrire les DATE_FORMATS des connecteurs.
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


def _recuperer(connecteur, url, max_retries=1, **kwargs):
    """
    Requete rate-limitee (FR-06), en renvoyant la reponse complete. Passe
    par BaseConnector.requete() : memes delais et memes reessais que la
    collecte, la reconnaissance n'a pas de regime de faveur.
    """
    # L'envoi est journalise par requete() elle-meme, APRES le delai FR-06 :
    # un log pose ici, avant l'attente, laissait croire a une requete
    # immediate.
    return connecteur.requete(url, tentatives=max_retries, **kwargs)


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

    url = connecteur.TARGET_URL
    for courante in range(1, page):
        raw = _recuperer(connecteur, url).text
        try:
            url = connecteur.url_page_suivante(raw, courante)
        finally:
            del raw  # CN-05
        if not url:
            raise SystemExit(f"La source ne compte que {courante} page(s).")

    reponse = _recuperer(connecteur, url)
    entrees = connecteur.parse(reponse.text).get("entries", [])
    libelles = _libelles_de_champs(reponse.text)

    print()
    print(f"PAGE {page} : {len(entrees)} entree(s) dans le listing ; "
          f"{min(limite, len(entrees))} affichee(s).")
    print(f"DATE_FORMATS actuels : {connecteur.DATE_FORMATS or '(aucun, formats communs seulement)'}")
    print("-" * 64)

    reconnues = 0
    for index, entree in enumerate(entrees[:limite]):
        cle, brute = next(
            ((c, entree.get(c)) for c in CLES_DATE if entree.get(c)), (None, None)
        )
        if brute is None:
            print(f"  [{index:>2}] aucune date dans le listing")
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

    reponse = _recuperer(connecteur, url, max_retries=1)

    print(f"\nHTTP {reponse.status_code} | {reponse.headers.get('Content-Type', '?')} "
          f"| {len(reponse.text)} caracteres")

    print("\nSQUELETTE STRUCTUREL DE LA PAGE DE DETAIL")
    print("-" * 64)
    print(resumer_structure(reponse.text, profondeur_max=profondeur, netloc_source=netloc_source))

    _verdict_liceite(connecteur, reponse, url, entree.get("nom_entite_detecte"))


def _analyser_arguments():
    parseur = argparse.ArgumentParser(
        description="Reconnaissance structurelle d'une source (sortie console uniquement)."
    )
    parseur.add_argument("--source", required=True, help="SOURCE_NAME du connecteur")
    parseur.add_argument("--phase", default="listing",
                         choices=("listing", "detail", "formes", "dates", "pages"))
    parseur.add_argument("--max", type=int, default=3,
                         help="Phase pages : nombre maximum de pages a suivre")
    parseur.add_argument("--index", type=int, default=0,
                         help="Entree du listing dont on inspecte le detail")
    parseur.add_argument("--page", type=int, default=1,
                         help="Phase dates : page de listing a examiner")
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
    else:
        phase_detail(connecteur, arguments.index, arguments.profondeur)
