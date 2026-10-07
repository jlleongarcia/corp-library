# Corp Library

Internal web app that helps the department find documents on the shared folders and decide where new
ones belong. It indexes the department shares on the Windows file server, respects the existing
Windows permissions, and (from phase 3) adds a local AI assistant that never sends data off-premises.

- **Roadmap and decisions:** [docs/ROADMAP.md](docs/ROADMAP.md)
- **Deploying and running it:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## Current state: phase 0 (discovery)

The worker scans the shares read-only over SMB and the admin console shows:

| Report | What it answers |
| --- | --- |
| Overview | How much is there, of what type, and how old |
| Permissions | Who can access which folder (effective access, groups expanded), and where permissions deviate |
| Duplicates | Identical files and the space their extra copies take |
| Stale files | Folders full of files nobody has touched in N years |
| Hygiene | Paths too long for Windows, over-nested folders, empty folders |

Every report exports to CSV (opens directly in Excel). End-user search arrives in phase 1.

## Layout

```
backend/            FastAPI API + background worker (same image)
  app/acl/          Windows security descriptor parser and access evaluation
  app/services/     scanner, SMB/local sources, LDAP directory, dedupe, reports, job queue
  alembic/          database migrations
  scripts/          dev.py (local stack without Docker), pytest_postgres.py
  tests/            pytest suite (SQLite by default, PostgreSQL via scripts/pytest_postgres.py)
frontend/           React + Vite + Tailwind admin console, served by nginx
deploy/backup.sh    nightly pg_dump
docker-compose.yml  db, api, worker, web, backup
```

## Development

Deployment uses Docker; local development doesn't need it. Requirements: [uv](https://docs.astral.sh/uv/)
(it installs Python 3.12 by itself) and Node 20 for the frontend.

**1. Configure.** Copy `.env.example` to `.env` in the repo root and set at least:

```ini
# Any username + DEV_PASSWORD logs in; no Active Directory needed
DEV_MODE=true
DEV_PASSWORD=dev
# Usernames that get the admin console
ADMIN_USERS=admin
# Must stay empty in dev mode
LDAP_SERVER=
# No nightly scans on your PC
SCAN_HOUR=-1
```

**2. Run the backend** (API + worker + a local PostgreSQL, nothing else to install):

```bash
cd backend
uv sync                      # creates .venv from uv.lock
uv run scripts/dev.py        # API on http://127.0.0.1:8000; Ctrl+C stops everything
```

The database lives in `backend/.devdata/` and survives restarts; delete that folder to start fresh.

**3. Run the frontend** in a second terminal:

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173, proxies /api to the backend
```

Sign in as `admin` / `dev`, add a local folder as a share (e.g. `C:\Users\you\Documents\test-share`)
and scan it. Local folders have no Windows ACLs, so the permission reports stay empty until you scan
a real share.

**Tests:**

```bash
cd backend
uv run pytest                          # fast, on SQLite
uv run scripts/pytest_postgres.py      # same suite on a real PostgreSQL
```

**Dependencies:** `uv add <package>` (or `uv add --dev <package>`) updates `pyproject.toml` and
`uv.lock`. The Docker image installs exactly what `uv.lock` pins.
