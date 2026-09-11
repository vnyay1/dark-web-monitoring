# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Sentinel — a dark web / clandestine-source monitoring system built for ANTIC (Cameroon's national IT
agency) as an internship project. It detects when Cameroonian entities (government, banks, telecoms,
universities, companies) appear in ransomware leak sites, forums, or paste services, and indexes the
**existence** of a leak — never the leaked data itself. The README (in French) is the canonical spec
reference (FR-xx = functional requirements, CN-xx = non-negotiable constraints); read it for full
context on requirements numbering used throughout code comments and commit messages.

### Non-negotiable constraints (override any feature request)

- **CN-03**: only approved metadata is stored (entity, category, source, date, criticality).
- **CN-04**: never persist personal names, emails, passwords, hashes, or excerpts of leaked data, in
  any model field.
- **CN-05**: all content analysis happens in memory only — raw page content is never written to disk.
  `BaseConnector.collect()` explicitly `del raw_content` after parsing for this reason.
- **CN-09/CN-10**: passive collection only, minimum 30s delay between requests to the same source
  (`BaseConnector.MIN_DELAY_SECONDS`, FR-06).

When touching connectors, models, or the pipeline, preserve these constraints even if not explicitly
asked — they take priority over functional convenience.

## Commands

```bash
# Run the web app (Flask serves the compiled React SPA from frontend/dist)
python3 run.py

# Frontend development (dev machine only - never on the collection VM)
cd frontend && npm install && npm run dev    # :5173, proxies /api to Flask
cd frontend && npm run build                 # regenerates frontend/dist (commit it)

# Run the collection scheduler (separate process, once a day at a random hour)
python3 -m app.scheduler
python3 -m app.scheduler --sans-collecte-initiale   # start idle, no immediate run

# Run one manual collection pass (debug/test)
python3 -m app.pipeline
python3 -m app.pipeline --source payload

# Retire a source and the data that exists only through it (dry-run unless --confirmer)
python3 -m app.maintenance.retirer_source --lister

# Database migrations (Alembic) - run BEFORE starting anything after a git pull
alembic upgrade head
alembic revision --autogenerate -m "description"

# Seed the initial selector catalogue (entities/keywords to match against)
python3 -m app.matching.seed_selecteurs

# Create a user account (CLI prompt)
python3 -m app.create_user
```

There is no configured test runner, linter, or formatter in this repo (`tests/` contains only an
empty `__init__.py`, and there's no pytest/flake8/ruff config) — don't assume `pytest` or `ruff` will
work; verify changes by running the relevant module directly (many have a `__main__` block, e.g.
`app/pipeline.py`, `app/alerting/test_alerting_manual.py`) or via the Flask dev server.

Required `.env` variables (no defaults — `app/config.py` reads them via `os.getenv` without fallback,
so missing vars raise at import time): `DATABASE_URL`, `FLASK_SECRET_KEY`, `TOR_SOCKS_PROXY`,
`TOR_CONTROL_PORT`, `TOR_CONTROL_PASSWORD`.

## Architecture

Pipeline: **Scheduler (APScheduler, once daily at a random hour) → Connectors (incremental
two-phase crawl) → Tor module → Date window → Matching Engine → False-positive filtering →
Criticality → Categories (from the matched selectors) → Deduplication → SQLAlchemy/SQLite → Alerting + JSON API +
React SPA**.

### Connectors (`app/connectors/`)

Every source connector subclasses `BaseConnector` (`app/connectors/base_connector.py`) and implements
`fetch()` (retrieve raw content) + `parse()` (extract text). `BaseConnector.collect()` orchestrates
both, enforces the FR-06 rate limit, and appends a `JournalAudit` row on every call (success or
failure) — this journal is append-only by design (no update/delete exposed for that table). Adding a
new source means adding one connector class; nothing else in the app needs to change. Connectors
return `{"entries": [...], "texte_global": ..., "nb_entries": int}`; `app/pipeline.py` processes each
`entry` individually rather than the whole page, since one entry = one potential victim = one
potential `Exposition`. `.onion` connectors fetch through `app/tor/__init__.py::get_via_tor()`, which
centralizes the Tor SOCKS proxy and both reactive (on failure) and proactive (every 10–120s, random)
circuit renewal — connectors should never talk to Tor directly.

The active connector list lives in `app/connectors/__init__.py::connecteurs_actifs()` — a new
connector must be added there to actually run. Its imports are deliberately inside the function
(connectors import `app.connectors`, so a module-level import would cycle).

`collect()` runs two phases: a bounded listing crawl, then detail pages for NEW entries only, within a
per-run budget. Paginated sources (`SUPPORTE_PAGINATION` + `url_page_suivante()`) stop at the first of:
all dated entries of a page older than the admin period (`hors_periode` — the pipeline passes
`date_limite` to `collect()`), a page with no readable date (`dates_illisibles`, a safety stop if a site
changes its date format), pages holding only already-known entries (`page_connue`), or the page cap
(min of the connector's `MAX_PAGES_LISTING` and the admin setting `pages_listing_max`). Sources without
dates (payload, cmd_organization) are never paginated. safepay dates its posts only on detail pages
(`DATE_SUR_DETAIL`): each listing page is dated by PROBING the detail page of its last NEW entry, a
visit the detail phase then reuses. Every pagination link goes through `_page_suivante_validee()`
(same host, same path as the listing, page = current + 1). Validate a connector's pagination with
`python3 -m app.connectors.reconnaissance --source <X> --phase pages --max 3`. Entries the budget didn't serve are left unmarked in `EntreeCollectee`
(`app/crawl/registre.py`) and picked up next cycle — the crawl is resumable. `url_detail()` is the
single place deciding a link is visitable; it returns `None` by default, so a source stays
listing-only until explicitly opted in (CN-04).

Publication dates arrive as site-specific strings under inconsistent keys (`date_publication`,
`discovery_date`, `date`). `_normaliser_entry()` in `pipeline.py` funnels them through
`app/connectors/dates.py::parser_date()` using each connector's `DATE_FORMATS`. An unparseable date
yields `None` and the entry is analysed ANYWAY — three sources (payload, safepay, cmd_organization)
publish no date at all, and dropping them would mean no longer watching them. On a listing verified as
newest-first (`LISTING_CHRONOLOGIQUE`, data_exposure_logs), an undated entry gets a `date_plafond`: the
date of the dated entry above it. It is an upper bound used only by the date window, never stored as
a publication date.

### Matching (`app/matching/`)

`engine.py` matches selector catalogue entries against extracted text via three tiers: exact,
case-insensitive, and fuzzy (RapidFuzz). Selectors of length ≤6 chars (`SEUIL_LONGUEUR_MOT_ENTIER`,
e.g. institutional acronyms like "ART", "MINFI") are treated specially: they require a strict word
boundary (lookaround regex, not `\b`, because `\b` treats hyphens as boundaries) and are matched
**only** in their exact uppercase form — case-insensitive and fuzzy matching are disabled for them —
to avoid false positives like the English word "art" or legal "Art." references. Longer selectors get
full substring/case-insensitive/fuzzy matching. This distinction is load-bearing; don't "simplify" it
away.

Downstream of `engine.py`, the pipeline applies, in order: the date window (entries older than
`periode_collecte_jours` are skipped), `exclusion.py` (false-positive filtering, FR-11),
`criticite.py` (FR-10, which also collects the matched selectors' categories), and
`deduplication.py::enregistrer_exposition()` (multi-source dedup + persistence, FR-12).

**Categories (FR-13) are the matched selectors' categories.** Keyword-based "leak nature"
categorisation was removed. `Categorie` is an admin-managed table (create/rename/delete from the UI);
an exposition carries the categories of every selector that triggered it (many-to-many
`exposition_categories`), unioned on redetection like criticality. Deleting a used category REQUIRES
a replacement: its selectors and expositions are transferred. The "place name inside a country list"
false-positive rule in `exclusion.py` follows the `Categorie.lieu_generique` flag, never a category
name (names are editable). `app/maintenance/recategoriser.py` back-fills categories for older
expositions from their entity name.

**Criticality replaced the old confidence score.** It is simply the number of DISTINCT catalogue
selectors found in one entry, mapped to four levels (`NiveauCriticite`) whose thresholds the admin
sets in `ConfigurationSysteme`. The engine emits one `MatchResult` per OCCURRENCE, so
`calculer_criticite()` deduplicates on `selecteur_valeur` — an entry repeating one name must not look
as serious as one naming three different entities. The matched selector VALUES are logged and shown in
the live console but never persisted: CN-03 lists what may be stored, and a selector list is not on it.

Criticality only ever increases on an existing exposition (`deduplication.py`): a later sighting that
sees fewer selectors must not downgrade an exposition already qualified as critical.

### Schema ownership (`app/db.py`, `migrations/`)

**Alembic owns the schema.** `init_db()` does NOT create tables: it only checks the database is at
the Alembic head and raises `BaseNonAJour` otherwise. It used to call `Base.metadata.create_all()`,
and any entry point run between a `git pull` and `alembic upgrade head` would create the new tables
from the models, making the next migration fail on "table already exists" (this happened on the VM
with `etat_scheduler`). Never reintroduce `create_all()`. `migrations/env.py` takes the URL from
`DATABASE_URL` so Alembic always migrates the application's database, not the one hardcoded in
`alembic.ini`. Migrations are hand-written (see the note in revision `d6fb8279afd3`).

### Models (`app/models/__init__.py`)

Single file, SQLAlchemy declarative. Key entities: `Exposition` (the leak indicator itself, with
`statut` lifecycle: new → under_review → confirmed/false_positive → notified → closed),
`SourceReference` (link from an Exposition to the source it was seen on — stores only a URL/id, never
content), `Source` (a monitored source's health/config), `Selecteur` (the catalogue of entity
names/keywords to match against, each linked to a `Categorie`), `JournalAudit` (append-only), `User` +
`RoleUtilisateur` + `HistoriqueRole` (auth/RBAC), `Alerte` (multi-channel alert delivery state),
`ConfigurationSysteme` (admin-editable runtime settings, key/value — each key declares its TYPE, so
`app/config_system.py::valider_valeur()` can accept both integers and named levels),
`EntreeCollectee` (incremental-crawl work queue, never an index of victims), `EtatScheduler` (single
row: the scheduler's single-instance lock and dashboard) and `EvenementCollecte` (the live activity
feed). All datetimes are stored as
naive UTC (`utc_now()`) deliberately — SQLite drops tzinfo on read, so mixing naive/aware comparisons
breaks; don't introduce timezone-aware `datetime.now()` calls elsewhere in this codebase.

### Web (`app/web/`) and frontend (`frontend/`)

The UI is a **React SPA** (`frontend/`, Vite). Flask no longer renders pages: it exposes a JSON API
(`app/web/api/`, one module per area, all under `/api`) plus downloads (reports, exports), and serves
the compiled SPA from `frontend/dist` — which is committed, so the collection VM needs no Node. The
only surviving Jinja template is `rapport_mensuel.html`, a WeasyPrint print document.

Two API-layer rules matter when adding endpoints:
1. Every mutating request must carry `X-Requested-With: XMLHttpRequest` (`api/__init__.py`). This is
   the CSRF defence — a cross-site form cannot set a custom header. The frontend's `api/client.js`
   adds it to every call.
2. Errors under `/api/*` must be JSON. Flask-Login's default is a 302 to a login page, which `fetch()`
   follows silently and receives HTML from; `enregistrer_api()` installs a 401-JSON handler instead.

`login_manager.login_view` is deliberately unset for that reason.

RBAC is centralized in `app/web/permissions.py`: four roles (`user` < `supervisor` < `admin` < `super_admin`) form a strict
hierarchy (`HIERARCHIE_ROLES`), and routes are protected with `@role_requis(RoleUtilisateur.X)` applied
*after* `@login_required`. A user can never deactivate themselves or act on an equal-or-higher-ranked
account (super_admin is unrestricted). When adding a new protected route, follow this same
`@login_required` + `@role_requis(...)` pattern rather than checking `current_user.role` ad hoc.

### Alerting (`app/alerting/`)

`rules.py` selects channels by criticality level × sector priority, `dispatcher.py` orchestrates
dispatch, `senders.py` implements the actual email/SMS/WhatsApp/interface sends. "Sector priority"
(FR-26) is read from the exposition's categories (`Categorie.prioritaire`, admin-editable) or a
`.gov.cm` entity name — there is no sector field on `Exposition` any more (it was never filled). Triggered from
`app/pipeline.py` via `declencher_alertes()` on new detections, or on an existing exposition whose
criticality rose by at least `hausse_criticite_confirmation`. INTERFACE receives every alert; the
intrusive channels are reserved for the high levels.

### Scheduler and supervision (`app/scheduler.py`, `app/supervision.py`)

The scheduler is a SEPARATE process from Flask — never import it into the web app. It runs one
collection per day at a random hour inside the configured window, rescheduling itself at the end of
each cycle.

`app/supervision.py` is the only access point to `EtatScheduler` and `EvenementCollecte`, and carries
the single-instance lock. The lock is taken with ONE conditional UPDATE, not a read-then-write: two
processes starting together would both pass a read check. It expires after 90s without a heartbeat,
otherwise a `kill -9` would block the system permanently. Living in the database, it blocks a second
start from the web UI and from the command line alike.

The pipeline publishes progress events (`DEBUT_SOURCE`, `NOUVELLE_EXPOSITION`, `FIN_SOURCE`) consumed
by the supervision console, which polls with a cursor (`/api/scheduler/evenements?depuis=<id>`) and,
on (re)mount, reloads the current or last cycle (`?historique=cycle`) - events live in the database,
so leaving the page loses nothing. The displayed elapsed time is the CYCLE duration
(`debut_collecte`/`fin_collecte`), frozen while idle, not the process age.

**The web server never talks to Tor.** `app/tor` records the last exit IP it observed (on every
circuit renewal) in process memory, without DB access; the scheduler's `job_synchroniser_tor`
publishes it to `EtatScheduler` and emits `CIRCUIT_RENOUVELE` on change, and serves the UI's
"verify now" request through a flag, like the immediate-collection request. That job is separate
from `job_verifier_demande` on purpose: the latter runs a manual collection inline and stays busy
for its whole duration. **Collection failures deliberately do not produce an event feed entry
beyond a neutral closing line** — they are already in `JournalAudit` with the detail auditing needs,
and repeating them would drown the progress feed.

### Reports (`app/reports/`)

`monthly_report.py` and `export.py` generate PDF (WeasyPrint) and JSON/CSV exports. Note the pinned
`pydyf==0.11.0` dependency in `requirements.txt` — required for compatibility with
`weasyprint==62.3`; a newer `pydyf` breaks PDF generation.

## Operational security context

This app is designed to run collection inside an isolated VM, never on a machine used for other
activity, and collection is meant to be strictly passive. These are deployment/process concerns
(see README "Sécurité opérationnelle") rather than something enforced in code, but they explain why
the Tor module and rate-limiting exist and should not be relaxed.
