# Sentinel — Surveillance Dark Web (ANTIC)

Système de détection et d'indexation des indicateurs de fuites de données relatives à des entités camerounaises, sur le Dark Web et les sources clandestines (ransomware leak sites, forums, paste services, canaux Telegram).

Projet de stage — ANTIC (Agence Nationale des Technologies de l'Information) — École Marocaine des Sciences de l'Ingénieur.

---

## Principe directeur

Le système indexe **l'existence** d'une fuite de données — jamais les données elles-mêmes.

- **CN-03** : seules les métadonnées autorisées sont stockées (entité, catégorie, source, date, criticité).
- **CN-04** : aucun nom de personne, email, mot de passe, hash ou extrait de donnée divulguée n'est jamais conservé.
- **CN-05** : toute analyse de contenu se fait uniquement en mémoire (RAM), jamais écrite sur disque.

Cette contrainte est non négociable et prévaut sur toute exigence fonctionnelle du cahier des charges.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    VM isolée (Kali Linux)                    │
│                                                              │
│  Scheduler (APScheduler, 1×/jour à heure aléatoire)          │
│         │  verrou d'instance unique en base                  │
│         ▼                                                    │
│  Connecteurs (8 sources réelles) ──► app/tor (Tor centralisé)│
│         │  crawl incrémental : listing puis pages de détail  │
│         ▼  texte en mémoire uniquement (CN-05)               │
│  Fenêtre temporelle ─► Matching ─► Filtrage faux positifs    │
│         │            ─► Criticité ─► Catégories              │
│         │            ─► Déduplication multi-source           │
│         ▼                                                    │
│  SQLAlchemy / SQLite                                         │
│         │                                                    │
│         ├──► Alerting (email / SMS / WhatsApp / interface)   │ 
│         ├──► API JSON Flask (4 rôles)                        │
│         └──► Interface React (SPA, servie par Flask)         │
└──────────────────────────────────────────────────────────────┘
```

---

## Stack technique

| Domaine | Outils |
|---|---|
| Langage | Python 3.11+ |
| Collecte | `requests`, `stem` (Tor), `BeautifulSoup4` |
| Planification | `APScheduler` |
| Matching | `re`, `RapidFuzz` |
| Persistance | `SQLAlchemy`, `SQLite`, `Alembic` |
| Interface web | API JSON `Flask` + `Flask-Login`, interface `React` (Vite, compilée dans `frontend/dist`) |
| Rapports | `WeasyPrint` (PDF, gabarit `Jinja2`), export `json` / `csv` |
| Réseau anonyme | Tor (proxy SOCKS, VM isolée) |

Dépendances directes, versions épinglées : [`requirements.txt`](./requirements.txt)

Note : `pydyf` est épinglé à la version `0.11.0` (compatibilité stricte avec `weasyprint==62.3`, une version plus récente casse la génération PDF).

---

## Structure du projet

```
dark-web-monitoring/
├── .env.example              # modèle de configuration (secrets)
├── requirements.txt
├── run.py                    # point d'entrée serveur web Flask
├── app/
│   ├── config.py              # configuration chargée depuis .env
│   ├── db.py                  # session SQLAlchemy
│   ├── pipeline.py             # orchestrateur collecte → analyse → alerte
│   ├── scheduler.py            # planification automatique (FR-07)
│   ├── create_user.py          # script CLI de création de compte
│   │
│   ├── models/                 # modèles SQLAlchemy (Exposition, Source,
│   │                            # Selecteur, User, Alerte, JournalAudit...)
│   │
│   ├── tor/                    # module Tor centralisé (FR-01)
│   │   └── __init__.py          # get_via_tor(), renouvellement de circuit
│   │
│   ├── crawl/                   # registre du crawl incrémental
│   │   └── registre.py           # entrées déjà analysées, reprise de cycle
│   │
│   ├── supervision.py            # état partagé du scheduler + fil d'événements
│   ├── securite.py               # politique de mots de passe (FR-24)
│   │
│   ├── connectors/              # connecteurs de sources (FR-02, FR-03)
│   │   ├── base_connector.py     # interface commune, rate limiting, audit
│   │   ├── dates.py              # normalisation des dates de publication
│   │   ├── reconnaissance.py     # analyse structurelle d'une source
│   │   ├── everest_connector.py
│   │   ├── payload_connector.py
│   │   ├── orionleaks_connector.py
│   │   ├── dataexposurelogs_connector.py
│   │   ├── blackwater_connector.py
│   │   ├── safepay_connector.py
│   │   ├── cmdorganization_connector.py
│   │
│   ├── matching/                # moteur de correspondance (FR-08 à FR-13)
│   │   ├── engine.py             # matching exact / insensible / fuzzy
│   │   ├── criticite.py          # criticité = nb de sélecteurs distincts (FR-10)
│   │   ├── exclusion.py          # filtrage faux positifs (FR-11)
│   │   ├── deduplication.py      # déduplication multi-source (FR-12)
│   │   └── seed_selecteurs.py    # peuplement initial du catalogue (FR-08)
│   │
│   ├── alerting/                 # alertes multi-canal (FR-25/FR-26)
│   │   ├── rules.py               # sélection de canal (seuil × priorité)
│   │   ├── dispatcher.py          # orchestration de l'envoi
│   │   └── senders.py             # implémentations email/SMS/WhatsApp
│   │
│   ├── reports/                  # rapports et export (FR-27/FR-28)
│   │   ├── monthly_report.py
│   │   └── export.py
│   │
│   ├── config_system.py          # configuration dynamique (seuils, etc.)
│   ├── libelles.py               # libellés français des statuts et niveaux
│   │
│   ├── maintenance/              # outils ponctuels (simulation par défaut)
│   │   ├── recategoriser.py       # catégories des expositions anciennes
│   │   └── retirer_source.py      # retrait d'une source et de ses données
│   │
│   └── web/                      # couche serveur
│       ├── auth.py                # socle Flask-Login (FR-24)
│       ├── permissions.py         # contrôle de privilèges (4 rôles)
│       ├── reports.py             # téléchargements PDF / JSON / CSV
│       ├── compliance.py          # export de conformité (super-admin)
│       ├── api/                   # API JSON consommée par l'interface
│       │   ├── auth.py  dashboard.py  expositions.py  alerts.py
│       │   ├── scheduler.py  settings.py  users.py  audit.py
│       │   └── compliance.py  reports.py
│       └── templates/
│           └── rapport_mensuel.html   # document d'impression WeasyPrint
│
├── frontend/                     # interface React (Vite)
│   ├── src/
│   │   ├── api/                   # client HTTP, session, hooks
│   │   ├── components/            # mise en page, briques, graphiques
│   │   ├── pages/                 # 12 écrans
│   │   └── theme/                 # jetons de design et styles de base
│   └── dist/                      # build versionné (aucun Node requis sur la VM)
│
├── migrations/                   # migrations Alembic
└── docs/
    └── uml/                       # diagrammes PlantUML (use case, classes,
                                    # composants, séquence)
```

---

## Sources surveillées

| # | Source | Type | Accès |
|---|---|---|---|
| 1 | Payload | Ransomware leak site | Tor |
| 2 | Orion Leaks (Data Leaks & Exposure) | Ransomware leak site | Tor |
| 3 | Data Exposure Logs | Ransomware leak site | Tor |
| 4 | BlackWater | Ransomware leak site | Tor |
| 5 | SafePay | Ransomware leak site | Tor |
| 6 | CMD Organization | Forum / annuaire de victimes | Tor |
| 7 | Everest | Ransomware leak site | Tor |

Chaque connecteur hérite de `BaseConnector` (`fetch()` + `parse()`), ce qui permet d'ajouter une nouvelle source sans modifier le reste de l'application (FR-02). Objectif à terme : extension progressive à 20 connecteurs.

The Hacker News (clairnet) a été retiré de la surveillance. Pour retirer une source et les données qui
n'existent que par elle (signalements, expositions sans autre source, file de crawl), après export
JSON et en conservant le journal d'audit :
```bash
python3 -m app.maintenance.retirer_source --lister                   # inventaire, sources orphelines
python3 -m app.maintenance.retirer_source <nom>                      # simulation
python3 -m app.maintenance.retirer_source <nom> --confirmer          # exécution
```

---

## Gestion des privilèges

Quatre rôles, avec héritage hiérarchique des permissions :

| Rôle | Permissions |
|---|---|
| **user** | Consultation (dashboard, expositions, alertes) |
| **supervisor** | + modification du statut d'une exposition, génération de rapports/export |
| **admin** | + gestion des comptes (hors super-admin), configuration du catalogue de sélecteurs, modification de rôle (hors super-admin) |
| **super-admin** | + gestion des comptes admin, journal d'audit complet, seuils d'alerte critiques, export/purge de conformité, historique des changements de rôle |

Un utilisateur ne peut jamais se désactiver lui-même, ni désactiver/modifier un compte de rang égal ou supérieur au sien (sauf super-admin, non restreint).

---

## Installation

### Prérequis

- Python 3.11+
- Tor (`sudo apt install tor torsocks`)
- Node 18+ **uniquement pour développer l'interface** (le build est versionné)
- Une VM isolée dédiée à la collecte (voir *Sécurité opérationnelle* ci-dessous)

### Mise en place

```bash
git clone <url-du-depot-prive>
cd dark-web-monitoring

python3 -m venv venv
source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt

cp .env.example .env       # puis renseigner les valeurs reelles
```

### Variables d'environnement (`.env`)

```
TOR_CONTROL_PASSWORD=...
TOR_SOCKS_PROXY=socks5h://127.0.0.1:9050
TOR_CONTROL_PORT=9051
FLASK_SECRET_KEY=...
DATABASE_URL=sqlite:///dark_web_monitoring.db
```

### Base de données

Le schéma est géré **uniquement par Alembic** : l'application ne crée aucune table et refuse de
démarrer sur une base qui n'est pas à jour. Après chaque `git pull`, lancer la migration **avant**
tout autre programme.

```bash
alembic upgrade head
python3 -m app.matching.seed_selecteurs
python3 -m app.create_user
```

---

## Utilisation

### Serveur web (interface analyste)

```bash
python3 run.py
```
Interface disponible sur `http://127.0.0.1:5000` — Flask sert l'application
React compilée (`frontend/dist`), versionnée dans le dépôt : **aucun Node n'est
requis sur la VM de collecte**.

### Développement de l'interface

Uniquement sur un poste de développement, jamais sur la VM de collecte :
```bash
cd frontend
npm install
npm run dev     # http://localhost:5173, relaie /api vers Flask
npm run build   # régénère frontend/dist, à commiter
```

### Collecte automatique (FR-07)

Une collecte par jour, à une heure **tirée au hasard** dans la plage réglée
par l'administrateur (`collecte_heure_min` / `collecte_heure_max`) : un passage
à heure fixe dessinerait côté sources un schéma prévisible.

Le processus est indépendant du serveur web. Il peut être lancé depuis
l'interface (page *Collecte*, réservée aux administrateurs) ou en ligne de
commande :
```bash
python3 -m app.scheduler
python3 -m app.scheduler --sans-collecte-initiale   # démarrer en veille
```

**Un seul scheduler peut tourner à la fois.** Le verrou vit en base : une
seconde instance est refusée qu'elle vienne de l'interface ou du terminal, et
le verrou expire de lui-même si le processus disparaît sans arrêt propre.

### Collecte manuelle (test / debug)

```bash
python3 -m app.pipeline                        # toutes les sources
python3 -m app.pipeline --source payload       # une seule source
```

---

## Sécurité opérationnelle

- **CN-07** : toute collecte s'exécute dans une VM isolée, jamais sur un poste utilisé pour d'autres activités.
- **CN-08** : aucun compte personnel n'est utilisé durant la collecte (compte Telegram dédié pour FR-05).
- **CN-09 / CN-10** : collecte strictement passive, respect d'un délai minimum de 30 secondes entre deux requêtes sur une même source (`FR-06`).
- **CN-11** : toute information concernant une organisation camerounaise réelle est communiquée exclusivement à l'encadrement.
- Les liens pointant directement vers des données divulguées (Mega.nz, endpoints de téléchargement, etc.) ne sont jamais conservés — seule leur existence est enregistrée.

---

## État d'avancement

Toutes les exigences **Must** du cahier des charges sont couvertes (FR-01, FR-02, FR-03, FR-06, FR-08 à FR-11, FR-13, FR-15, FR-16, FR-19 à FR-21, FR-24, FR-25, FR-27).

**Restant à faire :**
- FR-05 : connecteur Telegram (compte dédié à créer)
- FR-14 : proposition de sélecteurs par NER (étude de faisabilité réalisée)
- FR-23 : visualisation géographique/sectorielle (optionnelle)
- Extension du nombre de connecteurs (7 → 20)

---

## Licence et confidentialité

Projet interne à l'ANTIC. Dépôt privé. Toute information relative à des organisations camerounaises réelles reste strictement confidentielle et n'est communiquée qu'à l'encadrement (CN-11).