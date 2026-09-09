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

- **CN-03**: only approved metadata is stored (entity, category, source, date, confidence score).
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
# Run the web app (Flask, dev server on :5000)
python3 run.py

# Run the collection scheduler (separate long-running process, every 6h)
python3 -m app.scheduler

# Run one manual collection pass across all connectors (debug/test)
python3 -m app.pipeline

# Database migrations (Alembic)
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

Pipeline: **Scheduler (APScheduler, 6h) → Connectors → Tor module → Matching Engine → Scoring →
False-positive filtering → Categorization → Deduplication → SQLAlchemy/SQLite → Alerting +
Flask web UI**.

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

`executer_tous_les_connecteurs()` in `app/pipeline.py` hardcodes the list of active connectors — a new
connector must be added there to actually run (the README's list of 7 will be stale once you add
`everest_connector.py` or others; check `pipeline.py` for the ground truth).

### Matching (`app/matching/`)

`engine.py` matches selector catalogue entries against extracted text via three tiers: exact,
case-insensitive, and fuzzy (RapidFuzz). Selectors of length ≤6 chars (`SEUIL_LONGUEUR_MOT_ENTIER`,
e.g. institutional acronyms like "ART", "MINFI") are treated specially: they require a strict word
boundary (lookaround regex, not `\b`, because `\b` treats hyphens as boundaries) and are matched
**only** in their exact uppercase form — case-insensitive and fuzzy matching are disabled for them —
to avoid false positives like the English word "art" or legal "Art." references. Longer selectors get
full substring/case-insensitive/fuzzy matching. This distinction is load-bearing; don't "simplify" it
away.

Downstream of `engine.py`, the pipeline applies, in order: `exclusion.py` (false-positive filtering,
FR-11), `scoring.py` (confidence score, FR-10 — results below `SEUIL_ENREGISTREMENT_MINIMUM = 0.15` in
`pipeline.py` are dropped entirely), `categorisation.py` (leak category, FR-13), and
`deduplication.py::enregistrer_exposition()` (multi-source dedup + persistence, FR-12) which decides
whether a match creates a new `Exposition` or updates an existing one's score/detection date.

### Models (`app/models/__init__.py`)

Single file, SQLAlchemy declarative. Key entities: `Exposition` (the leak indicator itself, with
`statut` lifecycle: new → under_review → confirmed/false_positive → notified → closed),
`SourceReference` (link from an Exposition to the source it was seen on — stores only a URL/id, never
content), `Source` (a monitored source's health/config), `Selecteur` (the catalogue of entity
names/keywords to match against, categorized), `JournalAudit` (append-only), `User` +
`RoleUtilisateur` + `HistoriqueRole` (auth/RBAC), `Alerte` (multi-channel alert delivery state),
`ConfigurationSysteme` (admin-editable runtime settings, key/value). All datetimes are stored as
naive UTC (`utc_now()`) deliberately — SQLite drops tzinfo on read, so mixing naive/aware comparisons
breaks; don't introduce timezone-aware `datetime.now()` calls elsewhere in this codebase.

### Web (`app/web/`)

Flask app factory in `app/web/__init__.py` registers one blueprint per feature area (auth, dashboard,
expositions, alerts, reports, users, settings, audit, compliance, scheduler). RBAC is centralized in
`app/web/permissions.py`: four roles (`user` < `supervisor` < `admin` < `super_admin`) form a strict
hierarchy (`HIERARCHIE_ROLES`), and routes are protected with `@role_requis(RoleUtilisateur.X)` applied
*after* `@login_required`. A user can never deactivate themselves or act on an equal-or-higher-ranked
account (super_admin is unrestricted). When adding a new protected route, follow this same
`@login_required` + `@role_requis(...)` pattern rather than checking `current_user.role` ad hoc.

### Alerting (`app/alerting/`)

`rules.py` selects a channel by threshold × priority, `dispatcher.py` orchestrates dispatch,
`senders.py` implements the actual email/SMS/WhatsApp/interface sends. Triggered from
`app/pipeline.py` via `declencher_alertes()` on new detections or significant score increases.

### Reports (`app/reports/`)

`monthly_report.py` and `export.py` generate PDF (WeasyPrint) and JSON/CSV exports. Note the pinned
`pydyf==0.11.0` dependency in `requirements.txt` — required for compatibility with
`weasyprint==62.3`; a newer `pydyf` breaks PDF generation.

## Operational security context

This app is designed to run collection inside an isolated VM, never on a machine used for other
activity, and collection is meant to be strictly passive. These are deployment/process concerns
(see README "Sécurité opérationnelle") rather than something enforced in code, but they explain why
the Tor module and rate-limiting exist and should not be relaxed.
