# Audit de sécurité — Sentinel

Audit applicatif du 17 septembre 2026. Treize failles corrigées, dont trois de sévérité élevée.
Aucune injection SQL, aucun XSS et aucun secret exposé n'ont été trouvés.

**Contexte de déploiement retenu** : l'interface est servie en local sur la VM de collecte
(`http://127.0.0.1:5000`), sans accès réseau tiers. Cela abaisse la sévérité de tout ce qui relève
du transport (TLS, cookie `Secure`, HSTS) et relève celle de ce qui vient des **sources
collectées** — des serveurs administrés par des opérateurs de rançongiciel, seul attaquant externe
réellement en face de ce système.

---

## Synthèse

| #  | Faille                                                   | Sévérité | Localisation                             |
|----|----------------------------------------------------------|----------|------------------------------------------|
| 1  | Serveur de développement Flask avec `debug=True`          | Élevée   | `run.py:10`                              |
| 2  | Téléchargement Tor sans borne de taille                   | Élevée   | `app/tor/__init__.py:197`                |
| 3  | Injection de formule CSV via une donnée scrapée           | Élevée   | `app/reports/export.py:63-75`            |
| 4  | Mutations d'alertes sans contrôle de rôle                 | Moyenne  | `app/web/api/alerts.py:52-83`            |
| 5  | Aucun frein à la force brute, aucun audit des connexions  | Moyenne  | `app/web/api/auth.py:15-43`              |
| 6  | Session sans expiration, cookie non paramétrable          | Moyenne  | `app/web/__init__.py:33-40`              |
| 7  | En-têtes de sécurité HTTP absents                         | Moyenne  | `app/web/__init__.py`                    |
| 8  | Détails système renvoyés au client (`str(erreur)`)        | Moyenne  | `app/web/api/scheduler.py:116,143`       |
| 9  | URL `.onion` complète journalisée                         | Moyenne  | `app/tor/__init__.py:202`                |
| 10 | Entrées numériques non bornées → erreur 500               | Basse    | `expositions.py:117`, `reports.py:26`    |
| 11 | Sessions SQLAlchemy sans `try/finally`                    | Basse    | `app/reports/export.py:43-77`            |
| 12 | Politique de mot de passe faible (8 car., sans chiffre)   | Basse    | `app/securite.py:12-37`                  |
| 13 | Valeurs de configuration sans borne supérieure            | Basse    | `app/config_system.py:73-96`             |

Les trois failles élevées ont un point commun : elles sont atteignables depuis les sources
collectées. C'est la seule surface d'attaque réellement exposée d'un système dont l'interface ne
quitte pas la VM.

---

## Ce que l'audit a écarté

Ces points ont été vérifiés et sont sains — les signaler aurait été un faux positif.

- **Injection SQL** — aucune. Tout passe par l'ORM avec paramètres liés ; ni `text()`, ni
  concaténation, ni tri piloté par l'utilisateur. Le `f"%{recherche}%"` de `expositions.py:125`
  alimente la *valeur* d'un `ilike`, pas du SQL.
- **Secrets** — `.env` n'a jamais été versionné (vérifié sur tout l'historique Git, pas seulement
  sur l'état courant), aucun secret en dur, `TOR_CONTROL_PASSWORD` n'apparaît dans aucun journal.
- **Exécution de code** — aucun `eval`, `exec`, `pickle`, `os.system`, `shell=True` ni `yaml.load`
  dans `app/`. Les deux `subprocess` de `scheduler.py` passent une liste d'arguments fixe.
- **Mots de passe** — `generate_password_hash` / `check_password_hash` de Werkzeug (PBKDF2-SHA256),
  `getpass` en ligne de commande, message d'échec identique que le compte existe ou non.
- **CSRF** — déjà couvert avant l'audit : en-tête `X-Requested-With` exigé sur toute méthode
  mutante, posé par l'unique helper `fetch` du front, avec `SameSite=Lax` en renfort. Aucune route
  mutante hors de `/api`.
- **XSS** — zéro `dangerouslySetInnerHTML` ou `innerHTML` dans `frontend/src`, zéro `|safe` ou
  `autoescape false` dans les gabarits Jinja. Session en cookie HttpOnly, jamais en `localStorage`.
- **SSRF** — les `TARGET_URL` sont codées en dur dans les connecteurs, non éditables depuis l'UI.
- **RBAC** — `@role_requis` bien présent côté serveur sur les routes sensibles ; le masquage React
  n'est jamais la seule barrière. Seule exception trouvée : la faille 4.

---

## Failles élevées

### 1. Console Werkzeug et traces d'exécution — `run.py:10`

`debug=True` était la commande documentée pour lancer l'application. Elle active la console
Werkzeug, qui permet d'exécuter du code Python dans le processus, et affiche à chaque erreur 500
une trace contenant les variables locales — donc des fragments de page collectée. C'est une
violation directe de **CN-05**.

Code vulnérable :

```python
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
```

Code corrigé :

```python
import os

from app.web import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True activerait la console Werkzeug (execution de code arbitraire
    # dans le processus de l'application) et afficherait, a chaque erreur 500,
    # une trace contenant les variables locales - donc des fragments de page
    # collectee, ce qu'interdit CN-05. Jamais actif par defaut : il faut poser
    # FLASK_DEBUG explicitement, le temps d'une session de mise au point.
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "oui")
    app.run(debug=debug, host="127.0.0.1", port=5000)
```

**Explication** — le débogage reste possible, mais il faut le demander explicitement ; le mode par
défaut est sûr. À noter que `requirements.txt` ne contient aucun serveur WSGI : hors développement,
il faudrait passer par `waitress` ou `gunicorn` plutôt que par le serveur intégré de Flask.

### 2. Téléchargement Tor sans borne — `app/tor/__init__.py:197`

La réponse était chargée entièrement en mémoire par `response.text`, sans limite. Les serveurs
interrogés étant tenus par des opérateurs de rançongiciel, rien ne les empêchait de répondre
plusieurs gigaoctets et de faire tomber le processus de collecte — un déni de service à coût nul
pour eux. La troncature existante à 20 000 caractères intervient *après* le téléchargement complet
et ne protégeait donc rien.

Code vulnérable :

```python
response = requests.get(url, proxies=proxies, headers=request_headers, timeout=timeout)
response.raise_for_status()
return response
```

Code corrigé — constante, exception dédiée et lecture par blocs :

```python
class ReponseTropVolumineuse(Exception):
    """
    Corps de reponse depassant TAILLE_MAX_REPONSE.

    Traitee comme un echec de collecte ordinaire par le pipeline : elle est
    journalisee dans JournalAudit par le connecteur, sans entree dediee dans
    le flux d'evenements de la console de supervision.
    """


# 10 Mo : trois ordres de grandeur au-dessus d'une page de listing de site de
# fuite (quelques dizaines de Ko), donc aucune collecte legitime n'est
# tronquee, et le processus ne peut plus etre sature par une reponse geante.
TAILLE_MAX_REPONSE = 10 * 1024 * 1024


def _lire_avec_limite(response: requests.Response) -> requests.Response:
    """
    Lit le corps de la reponse par blocs, en s'arretant net au-dela de
    TAILLE_MAX_REPONSE.
    """
    annonce = response.headers.get("Content-Length")
    if annonce and annonce.isdigit() and int(annonce) > TAILLE_MAX_REPONSE:
        response.close()
        raise ReponseTropVolumineuse(
            f"Content-Length annonce ({annonce} octets) au-dela de la limite "
            f"de {TAILLE_MAX_REPONSE} octets."
        )

    morceaux = []
    total = 0
    for morceau in response.iter_content(chunk_size=65536):
        total += len(morceau)
        if total > TAILLE_MAX_REPONSE:
            response.close()
            raise ReponseTropVolumineuse(
                f"Corps de reponse au-dela de la limite de "
                f"{TAILLE_MAX_REPONSE} octets."
            )
        morceaux.append(morceau)

    # _content / _content_consumed : ce que requests renseigne lui-meme quand
    # il lit une reponse non streamee. `.text` decode ensuite normalement.
    response._content = b"".join(morceaux)
    response._content_consumed = True
    return response
```

et, dans `get_via_tor()` :

```python
    # CN-03 : l'URL complete d'un site de fuite ne doit jamais atterrir dans
    # un journal. base_connector fait deja cet effort de son cote ; le faire
    # ici aussi evite que le domaine .onion ressorte par la porte de derriere
    # a chaque echec reseau.
    chemin = urlparse(url).path or "/"

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url,
                proxies=proxies,
                headers=request_headers,
                timeout=timeout,
                stream=True,
            )
            response.raise_for_status()
            return _lire_avec_limite(response)
        except ReponseTropVolumineuse as e:
            # Inutile de renouveler le circuit et de reessayer : la reponse
            # serait la meme, en plus couteux. On abandonne cette cible.
            logger.warning(f"[tor] Reponse rejetee pour {chemin} : {e}")
            raise
        except requests.exceptions.RequestException as e:
            derniere_exception = e
            logger.warning(f"[tor] Tentative {attempt}/{max_retries} echouee pour {chemin} : {e}")
            if attempt < max_retries:
                renew_tor_circuit()
                time.sleep(retry_delay_seconds)
```

**Explication** — le `Content-Length` est vérifié d'abord, ce qui rejette une réponse géante *avant*
de la télécharger ; le comptage par blocs rattrape le cas où l'en-tête ment ou est absent. La
fonction renvoie toujours une `Response` normale, donc `base_connector.fetch()` continue de lire
`.text` sans modification. `ReponseTropVolumineuse` est attrapée par le `except Exception` existant
de `base_connector.requete()` et traitée comme un échec de collecte ordinaire.

Le même correctif traite la **faille 9** : `logger.warning` écrivait l'URL complète, domaine
`.onion` inclus, à chaque échec réseau, alors que `base_connector.py:213` prend soin de ne
journaliser que le chemin (CN-03). Ajouter `from urllib.parse import urlparse` en tête de fichier.

### 3. Injection de formule CSV — `app/reports/export.py`

Le champ `nom_entite` provient du HTML scrapé sur le site de fuite : c'est une chaîne choisie par
l'attaquant. Écrite telle quelle dans l'export CSV, une « victime » nommée `=cmd|'/c calc'!A1`
s'exécute à l'ouverture du fichier dans Excel ou LibreOffice — sur le poste de l'analyste, hors de
la VM isolée. C'est le seul chemin trouvé par lequel une source hostile atteint un poste de travail.

Code vulnérable :

```python
for e in expositions:
    ligne = _exposition_vers_dict(e)
    ligne["statut"] = libelles.libelle(libelles.STATUT, ligne["statut"])
    ligne["niveau_criticite"] = libelles.libelle(libelles.NIVEAU, ligne["niveau_criticite"])
    writer.writerow(ligne)
```

Code corrigé :

```python
# Un tableur (Excel, LibreOffice, Google Sheets) interprete comme FORMULE
# toute cellule commencant par l'un de ces caracteres. Or nom_entite provient
# du HTML scrape : c'est une chaine choisie par l'operateur du site de fuite.
CARACTERES_FORMULE = ("=", "+", "-", "@", "\t", "\r")


def _neutraliser_formule(valeur):
    """
    Prefixe d'une apostrophe une valeur que le tableur prendrait pour une
    formule. L'apostrophe n'est pas affichee dans la cellule : la lecture
    reste identique, seule l'evaluation est desamorcee.
    """
    if isinstance(valeur, str) and valeur.startswith(CARACTERES_FORMULE):
        return "'" + valeur
    return valeur
```

puis, dans la boucle d'écriture :

```python
        for e in expositions:
            ligne = _exposition_vers_dict(e)
            ligne["statut"] = libelles.libelle(libelles.STATUT, ligne["statut"])
            ligne["niveau_criticite"] = libelles.libelle(libelles.NIVEAU, ligne["niveau_criticite"])

            # Assainissement applique a TOUTES les colonnes, pas seulement a
            # nom_entite : les libelles de categories et de sources sont eux
            # aussi saisis a la main, et le champ le plus expose aujourd'hui
            # n'est pas forcement celui de demain.
            writer.writerow({c: _neutraliser_formule(v) for c, v in ligne.items()})
```

**Explication** — l'apostrophe de tête est un marqueur « texte littéral » universel dans les
tableurs : elle n'apparaît pas dans la cellule affichée, mais empêche l'évaluation. L'assainissement
porte sur toutes les colonnes et non sur `nom_entite` seul. Les deux fonctions d'export sont au
passage passées en `try/finally` (**faille 11**) : une exception pendant la lecture des relations
laissait autrement la connexion ouverte.

---

## Failles moyennes

### 4. Mutations d'alertes sans contrôle de rôle — `app/web/api/alerts.py`

Deux routes POST ne portaient que `@login_required`. Le compte le moins privilégié pouvait marquer
**toutes** les alertes comme lues d'un seul appel, c'est-à-dire faire disparaître une détection de
ce qui reste à traiter par l'équipe.

Code vulnérable :

```python
@api_bp.route("/alertes/tout-marquer-lu", methods=["POST"])
@login_required
def tout_marquer_lu():
```

Code corrigé :

```python
    # Marquer une alerte lue est un acte de TRAITEMENT, au meme titre que le
    # changement de statut d'une exposition (expositions.py, SUPERVISOR) :
    # une alerte lue disparait de ce qui reste a traiter. Le laisser au role
    # `user` permettait au compte le moins privilegie de masquer une
    # detection a toute l'equipe - d'un seul appel pour tout-marquer-lu.
    @api_bp.route("/alertes/<alerte_id>/marquer-lue", methods=["POST"])
    @login_required
    @role_requis(RoleUtilisateur.SUPERVISOR)
    def marquer_lue(alerte_id):
```

Même ajout sur `tout_marquer_lu`, plus l'import :

```python
from app.models import Alerte, CanalAlerte, RoleUtilisateur
from app.web.permissions import role_requis
```

**Explication** — `SUPERVISOR` est le niveau déjà exigé par `changer_statut` dans `expositions.py`,
qui est l'action équivalente sur le cycle de vie métier. La lecture `GET /alertes` reste ouverte à
tout compte authentifié, conformément au modèle existant.

### 5. Force brute et absence d'audit des connexions — `app/web/api/auth.py`

L'écran de connexion était la seule porte du système sans aucun frein : un script pouvait essayer
des mots de passe indéfiniment, sans trace et sans ralentissement. Par ailleurs `JournalAudit` ne
contenait que des événements de collecte — aucune connexion n'était tracée, ce qui laissait
**FR-17** incomplet et rendait toute investigation impossible.

Nouveau module `app/web/limitation.py` (extrait) :

```python
SEUIL_ECHECS = 5
DUREE_BLOCAGE = timedelta(minutes=15)

_tentatives = {}
_verrou = threading.Lock()


def est_bloque(nom_utilisateur: str, ip: str) -> int:
    """
    Retourne le nombre de secondes de blocage restantes, ou 0 si la
    tentative est autorisee.
    """
    maintenant = utc_now()
    with _verrou:
        _purger(maintenant)
        echecs, dernier_echec = _tentatives.get(_cle(nom_utilisateur, ip), (0, None))

        if echecs < SEUIL_ECHECS or dernier_echec is None:
            return 0

        restant = DUREE_BLOCAGE - (maintenant - dernier_echec)
        return max(0, int(restant.total_seconds()))
```

Route de connexion corrigée (extraits) :

```python
        ip = request.remote_addr

        # Frein anti-force brute AVANT toute verification : sans lui, le seul
        # cout d'un essai etait celui du hachage PBKDF2.
        secondes_restantes = limitation.est_bloque(nom, ip)
        if secondes_restantes:
            return jsonify({
                "succes": False,
                "message": (
                    f"Trop de tentatives echouees. Reessayez dans "
                    f"{secondes_restantes // 60 + 1} minute(s)."
                ),
            }), 429

        session = get_session()
        try:
            user = session.query(User).filter_by(nom_utilisateur=nom, actif=True).first()

            if not user or not check_password_hash(user.mot_de_passe_hash, mot_de_passe):
                limitation.enregistrer_echec(nom, ip)
                _journaliser_connexion(False, nom)
                return jsonify({
                    "succes": False,
                    "message": "Identifiants incorrects.",
                }), 401
            ...
        finally:
            session.close()

        limitation.reinitialiser(nom, ip)
        login_user(utilisateur)

        # Sans session permanente, PERMANENT_SESSION_LIFETIME ne s'applique
        # pas : le cookie vivrait jusqu'a la fermeture du navigateur.
        session_flask.permanent = True

        _journaliser_connexion(True, charge_utile["nom_utilisateur"])
```

Journalisation (FR-17) :

```python
def _journaliser_connexion(reussie: bool, nom: str) -> None:
    """
    FR-17 - Trace durable des acces. Seul le nom de COMPTE est ecrit : il
    figure deja dans la table users et n'est pas une donnee personnelle au
    sens de CN-04. Le mot de passe saisi, lui, n'est jamais journalise, meme
    tronque, meme en cas d'echec.
    """
    session = get_session()
    try:
        session.add(JournalAudit(
            source_id=None,  # nullable : evenement d'authentification, pas de collecte
            resultat=ResultatAudit.SUCCES if reussie else ResultatAudit.ECHEC,
            details=(
                f"Connexion reussie : {nom}" if reussie
                else f"Echec de connexion pour : {nom or '(nom vide)'}"
            ),
        ))
        session.commit()
    except Exception:
        # Un journal indisponible ne doit pas empecher de se connecter, mais
        # ne doit pas non plus passer inapercu cote serveur.
        session.rollback()
        logger.exception("[auth] Impossible de journaliser la tentative de connexion.")
    finally:
        session.close()
```

**Explication** — le compteur vit en mémoire du processus : le serveur web est un processus unique,
un dictionnaire suffit, et cela évite d'écrire en base à chaque échec. Un redémarrage remet les
compteurs à zéro — c'est un frein contre l'automatisation, pas un verrou de comptabilité ; la trace
durable vit dans `JournalAudit`. La clé est le couple (compte, IP) : un poste partagé ne bloque pas
tous ses comptes d'un coup, et un attaquant ne peut pas bloquer le compte d'un tiers depuis
l'extérieur. **Aucune migration nécessaire** : `JournalAudit.source_id` est déjà `nullable=True`.
Aucune dépendance ajoutée, conformément à la règle du dépôt sur `requirements.txt`.

### 6 & 7. Session et en-têtes de sécurité — `app/web/__init__.py`

Une session restait valable indéfiniment, le cookie ne pouvait pas être marqué `Secure` sans
modifier le code, et aucun en-tête de sécurité n'était posé.

```python
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Pilote par .env : le deploiement actuel est en HTTP sur la VM, ou
    # marquer le cookie Secure couperait la connexion (cf. app/config.py).
    app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
    app.config["PERMANENT_SESSION_LIFETIME"] = DUREE_SESSION  # timedelta(hours=8)
```

Dans `app/config.py` :

```python
    # Marque le cookie de session "Secure" (jamais transmis en clair). Le
    # deploiement actuel est en HTTP sur la VM : l'activer par defaut
    # empecherait toute connexion. C'est donc la SEULE variable a porter une
    # valeur par defaut, parce qu'elle durcit sans etre indispensable au
    # demarrage - a passer a true des qu'un reverse proxy TLS est en place.
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in (
        "1", "true", "oui",
    )
```

En-têtes posés sur toute réponse :

```python
def _entetes_securite() -> dict:
    script_src = " ".join(["'self'"] + _empreintes_scripts_inline())

    return {
        "Content-Security-Policy": (
            "default-src 'self'; "
            f"script-src {script_src}; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
```

```python
    # Calcule une fois au demarrage : lire index.html a chaque reponse
    # couterait un acces disque par requete.
    entetes_securite = _entetes_securite()

    @app.after_request
    def poser_entetes_securite(reponse):
        # setdefault : une route qui aurait une raison de definir son propre
        # en-tete garde la main.
        for entete, valeur in entetes_securite.items():
            reponse.headers.setdefault(entete, valeur)
        return reponse
```

**Le point délicat de la CSP.** `index.html` contient un script inline légitime — le bootstrap de
thème, qui doit s'exécuter avant le premier affichage pour ne pas montrer la page dans le mauvais
thème. Trois options se présentaient : ajouter `'unsafe-inline'` à `script-src` (ce qui aurait vidé
la CSP de son intérêt principal), figer une empreinte SHA-256 dans le code (qu'un `npm run build`
invaliderait silencieusement, cassant le thème sans que rien ne le signale), ou calculer
l'empreinte au démarrage à partir du build réel. C'est la troisième qui a été retenue :

```python
def _empreintes_scripts_inline() -> list:
    index = RACINE_BUILD / "index.html"
    if not index.is_file():
        return []

    html = index.read_text(encoding="utf-8")
    empreintes = []
    for corps in re.findall(r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>", html, re.DOTALL):
        condense = hashlib.sha256(corps.encode("utf-8")).digest()
        empreintes.append(f"'sha256-{base64.b64encode(condense).decode()}'")
    return empreintes
```

Imports à ajouter : `base64`, `hashlib`, `re`, et `from datetime import timedelta`.

**Explication des deux assouplissements** — `'unsafe-inline'` sur `style-src` est nécessaire : React
et Recharts posent des attributs `style=` en ligne, et le gabarit d'impression a un bloc `<style>` ;
il n'existe pas d'équivalent des empreintes pour les attributs de style. `data:` sur `img-src` sert
aux graphiques. `script-src`, lui, reste strict.

### 8. Détails système renvoyés au client — `app/web/api/scheduler.py`

Code vulnérable :

```python
        except Exception as erreur:
            return jsonify({
                "succes": False,
                "message": f"Impossible de lancer le scheduler : {erreur}",
            }), 500
```

Code corrigé :

```python
        except Exception:
            # Le message d'exception de Popen porte le chemin de
            # l'interpreteur et la ligne de commande complete : utile dans le
            # journal serveur, pas dans une reponse HTTP.
            logger.exception("[scheduler] Echec du lancement du processus.")
            return jsonify({
                "succes": False,
                "message": (
                    "Impossible de lancer le scheduler. Consultez le journal "
                    "du serveur pour le detail."
                ),
            }), 500
```

Même traitement sur la route d'arrêt, où `erreur_signal = str(erreur)` devient un simple booléen
`arret_echoue`. Le module n'avait pas de `logger` : ajouter `import logging` et
`logger = logging.getLogger(__name__)`.

**Explication** — le `pid` et le `hostname` restent affichés dans le message d'arrêt : ce sont les
informations dont l'administrateur a besoin pour terminer le processus à la main. Seul le message
d'exception brut disparaît.

---

## Failles basses

### 10. Entrées numériques non bornées

`periode` était validé par `isdigit()` seul, ce qui acceptait une chaîne de 300 chiffres que
`timedelta` refuse par un `OverflowError` → 500. `annee` n'était pas validé du tout, alors que
`datetime.replace(year=...)` lève un `ValueError` hors de la plage 1–9999.

```python
            periode = request.args.get("periode", "").strip()
            # isdigit() seul acceptait une chaine de 300 chiffres, que
            # timedelta refuse par un OverflowError -> 500. 3650 jours (10
            # ans) depassent largement l'historique que le systeme peut
            # detenir.
            if periode.isdigit() and 1 <= len(periode) <= 4:
                jours = min(int(periode), 3650)
                query = query.filter(
                    Exposition.date_premiere_detection >= utc_now() - timedelta(days=jours)
                )
```

```python
        # Sans borne, datetime.replace(year=...) leve un ValueError non
        # rattrape (annee=0, annee negative, au-dela de 9999) et l'utilisateur
        # recoit une 500 la ou une saisie invalide merite une 400.
        if not 2000 <= annee <= 2100:
            return jsonify({
                "succes": False,
                "message": "Annee invalide (2000 a 2100).",
            }), 400
```

### 12. Politique de mot de passe — `app/securite.py`

Minimum porté de 8 à 12 caractères, avec exigence d'un chiffre :

```python
LONGUEUR_MINIMALE = 12

    if not re.search(r"[0-9]", mot_de_passe):
        return False, "Le mot de passe doit contenir au moins un chiffre."
```

**Explication** — à classe de caractères égale, 8 caractères restent à portée d'une attaque hors
ligne si la base venait à être copiée. La politique ne s'applique qu'à la création : les comptes
existants ne sont pas invalidés.

### 13. Bornes de configuration — `app/config_system.py`

Seule la négativité était refusée. Un seuil de criticité fixé à 100 000 désactivait silencieusement
toute alerte, et `pages_listing_max=100000` transformait un cycle de collecte en parcours
interminable de la source.

```python
BORNES_MAXIMALES = {
    "seuil_criticite_moyenne": 100,
    "seuil_criticite_elevee": 100,
    "seuil_criticite_critique": 100,
    "criticite_minimum_enregistrement": 100,
    "hausse_criticite_confirmation": 100,
    "periode_collecte_jours": 3650,
    "pages_listing_max": 500,
    "collecte_heure_min": 23,
    "collecte_heure_max": 23,
}
```

```python
        maximum = BORNES_MAXIMALES.get(cle)
        if maximum is not None and entier > maximum:
            raise ValueError(f"Cette valeur ne peut pas depasser {maximum}.")

        # Coherence croisee : une fenetre de collecte inversee ne leve aucune
        # erreur a l'enregistrement, mais fait echouer le tirage de l'heure
        # au moment de la planification, loin d'ici.
        if cle == "collecte_heure_min" and entier > int(get_config("collecte_heure_max")):
            raise ValueError("L'heure de debut ne peut pas etre posterieure a l'heure de fin.")
        if cle == "collecte_heure_max" and entier < int(get_config("collecte_heure_min")):
            raise ValueError("L'heure de fin ne peut pas etre anterieure a l'heure de debut.")
```

---

## Vérification

Tous les tests ont été exécutés sur une **copie** de la base (`DATABASE_URL` pointant vers le
dossier temporaire), jamais sur `dark_web_monitoring.db` : la base du projet est restée intacte,
sans aucune ligne d'audit ni compte de test.

| Contrôle | Résultat |
|---|---|
| Compilation de `app/` et `run.py` | OK |
| Démarrage de l'application, 45 routes montées | OK |
| `Debug mode: off` dans le log serveur, aucune mention de debugger | OK |
| Les 4 en-têtes de sécurité présents sur `/` en HTTP réel | OK |
| Empreinte CSP = empreinte du script inline réellement servi | identiques |
| POST sans `X-Requested-With` | 403 |
| 6 tentatives de connexion successives | 401 ×5 puis 429 |
| Connexions tracées dans `JournalAudit` | succès et échecs |
| POST alertes avec un compte `user` | 403 (lecture : 200) |
| `periode` = 300 chiffres | 200, plus de 500 |
| `pages_listing_max=100000` / `collecte_heure_min=30` | refusés avec message |
| Neutralisation CSV d'une valeur `=cmd|'/c calc'!A1` | préfixée `'` |
| Limite Tor : `Content-Length` annoncé à 50 Mo | rejeté avant téléchargement |
| Limite Tor : corps de 10 Mo+ sans `Content-Length` | rejeté en cours de lecture |
| Limite Tor : page normale | `.text` inchangé |

**Reste à vérifier sur la VM Kali, Tor actif** — la chaîne de collecte réelle n'a pas pu être
testée depuis le poste de développement :

```bash
python3 -m app.pipeline --source payload
```

Vérifier qu'aucune URL `.onion` complète n'apparaît dans les logs et que la collecte aboutit
normalement.

**Reste à vérifier dans un navigateur** — l'extension navigateur n'était pas connectée pendant
l'audit, donc la CSP n'a pas pu être observée à l'exécution. L'empreinte a été vérifiée
programmatiquement (elle correspond exactement au script servi), mais il faut parcourir les écrans
console ouverte, en particulier les graphiques Recharts, pour confirmer qu'aucune règle ne bloque
l'interface.

---

## Ce qui reste à trancher

Points relevés mais non corrigés, car ils touchent l'ergonomie ou le déploiement plutôt que le code.

- **Mot de confirmation de la purge** (`app/web/api/compliance.py:29-35`, Basse) — la route GET
  renvoie `mot_de_confirmation` en clair. Le rôle `SUPER_ADMIN` est déjà exigé, donc ce n'est pas un
  contournement de contrôle d'accès, mais cela vide de son sens le garde-fou anti-clic accidentel :
  un script authentifié peut lire le mot puis l'envoyer aussitôt. Le retirer de la réponse touche
  l'écran de conformité côté React, d'où la mise en attente.
- **Serveur WSGI de production** — `requirements.txt` n'en contient aucun. Hors développement,
  `waitress` (le plus simple sous Windows) devrait remplacer le serveur intégré de Flask.
- **`SESSION_COOKIE_SECURE`** — à passer à `true` dans `.env` dès qu'un reverse proxy HTTPS sera
  placé devant Flask.
- **Dépendances front** — `react` 18.3.1, `vite` 5.4.8, `recharts` 2.12.7 n'ont pas été confrontées
  à une base CVE. Lancer `npm audit` dans `frontend/`.
