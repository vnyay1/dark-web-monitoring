# Sentinel — Surveillance Dark Web (ANTIC)

Système de détection et d'indexation des indicateurs de fuites de données relatives à des entités camerounaises, sur le Dark Web et les sources clandestines (ransomware leak sites, forums, paste services, canaux Telegram).

Projet de stage — ANTIC (Agence Nationale des Technologies de l'Information) — École Marocaine des Sciences de l'Ingénieur.

---

## Principe directeur

Le système indexe **l'existence** d'une fuite de données — jamais les données elles-mêmes.

- **CN-03** : seules les métadonnées autorisées sont stockées (entité, catégorie, source, date, score de confiance).
- **CN-04** : aucun nom de personne, email, mot de passe, hash ou extrait de donnée divulguée n'est jamais conservé.
- **CN-05** : toute analyse de contenu se fait uniquement en mémoire (RAM), jamais écrite sur disque.

Cette contrainte est non négociable et prévaut sur toute exigence fonctionnelle du cahier des charges.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    VM isolée (Kali Linux)                 │
│                                                             │
│  Scheduler (APScheduler, toutes les 6h)                   │
│         │                                                   │
│         ▼                                                   │
│  Connecteurs (7 sources réelles) ──► app/tor (Tor centralisé)│
│         │                                                   │
│         ▼  texte en mémoire uniquement (CN-05)              │
│  Matching Engine ─► Filtrage faux positifs ─► Scoring        │
│         │            ─► Catégorisation ─► Déduplication      │
│         ▼                                                   │
│  SQLAlchemy / SQLite                                        │
│         │                                                   │
│         ├──► Alerting (email / SMS / WhatsApp / interface)  │
│         └──► Interface web Flask (7 blueprints, 4 rôles)     │
└─────────────────────────────────────────────────────────┘
```

---

## Stack technique

| Domaine | Outils |
|---|---|
| Langage | Python 3.11+ |
| Collecte | `requests`, `stem` (Tor), `BeautifulSoup4` |
| Planification | `APScheduler` |
| Matching / NLP | `re`, `RapidFuzz`, `spaCy` |
| Persistance | `SQLAlchemy`, `SQLite`, `Alembic` |
| Interface web | `Flask`, `Flask-Login`, `Jinja2` |
| Rapports | `WeasyPrint` (PDF), export `json` / `csv` |
| Réseau anonyme | Tor (proxy SOCKS, VM isolée) |

Dépendances complètes : [`requirements.txt`](./requirements.txt)

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
│   ├── connectors/              # connecteurs de sources (FR-02, FR-03)
│   │   ├── base_connector.py     # interface commune, rate limiting, audit
│   │   ├── payload_connector.py
│   │   ├── orionleaks_connector.py
│   │   ├── dataexposurelogs_connector.py
│   │   ├── blackwater_connector.py
│   │   ├── safepay_connector.py
│   │   ├── cmdorganization_connector.py
│   │   └── thehackernews_connector.py
│   │
│   ├── matching/                # moteur de correspondance (FR-08 à FR-13)
│   │   ├── engine.py             # matching exact / insensible / fuzzy
│   │   ├── scoring.py            # score de confiance (FR-10)
│   │   ├── exclusion.py          # filtrage faux positifs (FR-11)
│   │   ├── categorisation.py     # catégorisation automatique (FR-13)
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
│   │
│   └── web/                      # interface Flask (blueprints)
│       ├── auth.py                # authentification (FR-24)
│       ├── permissions.py         # contrôle de privilèges (4 rôles)
│       ├── dashboard.py           # tableau de bord (FR-19)
│       ├── expositions.py         # liste, filtres, statuts (FR-20/FR-21)
│       ├── alerts.py              # affichage des alertes
│       ├── reports.py             # génération de rapports
│       ├── users.py               # gestion des comptes et rôles
│       ├── settings.py            # configuration système
│       ├── audit.py               # journal d'audit (super-admin)
│       ├── compliance.py          # export / purge de conformité (super-admin)
│       └── templates/
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
| 7 | TheHackerNews | Actualité cybersécurité | Clairnet |

Chaque connecteur hérite de `BaseConnector` (`fetch()` + `parse()`), ce qui permet d'ajouter une nouvelle source sans modifier le reste de l'application (FR-02). Objectif à terme : extension progressive à 20 connecteurs.

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
Interface disponible sur `http://127.0.0.1:5000`.

### Collecte automatique (FR-07)

Processus indépendant, à lancer séparément (toutes les 6h) :
```bash
python3 -m app.scheduler
```

### Collecte manuelle (test / debug)

```bash
python3 -m app.pipeline
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