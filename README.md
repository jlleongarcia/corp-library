# Corp Library

[![CI](https://github.com/jlleongarcia/corp-library/actions/workflows/ci.yml/badge.svg)](https://github.com/jlleongarcia/corp-library/actions/workflows/ci.yml)

Internal web app that helps the department find documents on the shared folders and decide where new
ones belong. It indexes the department shares on the Windows file server, respects the existing
Windows permissions, and (from phase 3) adds a local AI assistant that never sends data off-premises.

- **Roadmap and decisions:** [docs/ROADMAP.md](docs/ROADMAP.md)
- **Deploying and running it:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## Current state: phase 1 (search)

Everyone signs in with their Windows account (Kerberos single sign-on, or the sign-in form) and can:

- **Search** names, folders and document text (Word, Excel, PowerPoint, PDF with OCR for scans,
  OpenDocument, text), in English or Spanish, with or without accents, with highlighted snippets and
  filters by share, type and date
- **Browse** the shares folder by folder
- Open a **document page**: metadata, PDF/image preview, download, and **copy network path** to open
  it in place from Explorer

Each person only sees what Windows lets them open: results are filtered by their AD groups against the
file server's permissions, and every download re-checks the file's live permissions. Searches, views
and downloads go to an audit log. Admins see no more documents than anyone else.

The admin console (from phase 0) shows:

| Report | What it answers |
| --- | --- |
| Overview | How much is there, of what type, and how old |
| Permissions | Who can access which folder (effective access, groups expanded), and where permissions deviate |
| Duplicates | Identical files and the space their extra copies take |
| Stale files | Folders full of files nobody has touched in N years |
| Hygiene | Paths too long for Windows, over-nested folders, empty folders |

Every report exports to CSV (opens directly in Excel). The admin console also shows the search index
status and the audit log.

## Layout

```
backend/            FastAPI API + background worker (same image)
  app/acl/          Windows security descriptor parser and access evaluation
  app/auth/         sessions, Kerberos SSO, LDAP sign-in, dev identities
  app/services/     scanner, sources, LDAP directory, indexer + extraction, search, library
                    (browse/documents), access filter, audit, dedupe, reports, job queue
  alembic/          database migrations
  scripts/          dev.py (local stack without Docker), pytest_postgres.py
  tests/            pytest suite (SQLite by default, PostgreSQL via scripts/pytest_postgres.py)
frontend/           React + Vite + Tailwind UI (search, browse, admin console), served by nginx
deploy/backup.sh    nightly pg_dump
docker-compose.yml  db, api, worker, web, backup (app images pulled from ghcr.io)
.github/workflows/  CI: tests on every push; image publishing to ghcr.io is off until PUBLISH_IMAGES=true
```

## Development

Deployment uses Docker; local development doesn't need it. Requirements: [uv](https://docs.astral.sh/uv/)
(it installs Python 3.12 by itself) and Node 20 for the frontend.

**1. Configure.** Copy `.env.example` to `.env` in the repo root and set at least:

```ini
# Any username signs in, no password, no Active Directory needed
DEV_MODE=true
# Fake AD groups for dev users (optional, see "Testing permissions locally")
DEV_GROUPS=alice:finance,hr;bob:hr
# Usernames that get the admin console
ADMIN_USERS=admin
# Must stay empty in dev mode
LDAP_SERVER=
KERBEROS_KEYTAB=
# No nightly scans on your PC
SCAN_HOUR=-1
```

DEV_MODE refuses to run unless LDAP is off and the database is local, so it can't be switched on in
production by mistake.

**2. Run the backend** (API + worker + a local PostgreSQL, nothing else to install):

```bash
cd backend
uv sync                      # creates .venv from uv.lock
uv run scripts/dev.py        # API on http://127.0.0.1:8000; Ctrl+C stops everything
```

PostgreSQL listens on `127.0.0.1:54329` (database `corplib_dev`, user `postgres`, no password; change the
port with `DEV_PG_PORT`). Its data and log (`postgres.log`) live in `backend/.devdata/` and survive restarts;
stop the script and delete that folder to start fresh.

**3. Run the frontend** in a second terminal:

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173, proxies /api to the backend
```

Sign in as `admin` (no password), add a local folder as a share (e.g.
`C:\Users\you\Documents\test-share`) and scan it. The worker then indexes it; search it from the
home page. OCR of scanned PDFs needs [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) with
the Spanish data on your `PATH`; without it those PDFs are found by name only.

**Testing permissions locally.** Local folders have no usable Windows ACLs, so in DEV_MODE everyone can
read everything, unless a folder contains a `.corplib-acl.json`. That file replaces the inherited
permissions for the folder and everything below it, like "disable inheritance" in Explorer:

```json
{"read": ["finance"], "deny": ["alice"], "list": ["everyone"]}
```

`read` lets those users or groups open files and list folders, `deny` takes that away, and `list` lets
them list this folder only, without opening its files. Names are usernames or groups from
`DEV_GROUPS`. Sign in as different users to compare what each one finds. Rescan after editing these
files. Downloads re-check them immediately, as they would the real file server.

**Tests:**

```bash
cd backend
uv run pytest                          # fast, on SQLite
uv run scripts/pytest_postgres.py      # same suite on a real PostgreSQL
```

**Dependencies:** `uv add <package>` (or `uv add --dev <package>`) updates `pyproject.toml` and
`uv.lock`. The Docker image installs exactly what `uv.lock` pins.
