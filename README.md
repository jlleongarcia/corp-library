# Corp Library

Internal web app that helps the department find documents on the shared folders and decide where new
ones belong. It indexes the department shares on the Windows file server, respects the existing
Windows permissions, and (from phase 3) adds a local AI assistant that never sends data off-premises.

- **Roadmap and decisions:** [docs/ROADMAP.md](docs/ROADMAP.md)
- **Deploying and running it:** [docs/OPERATIONS.md](docs/OPERATIONS.md)

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
  tests/            pytest suite (SQLite by default, PostgreSQL via scripts/pytest_postgres.py)
frontend/           React + Vite + Tailwind admin console, served by nginx
deploy/backup.sh    nightly pg_dump
docker-compose.yml  db, api, worker, web, backup
```

## Development

```bash
# Backend (Python 3.12)
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # .venv/bin on Linux
.venv/Scripts/python -m pytest                      # fast, on SQLite
.venv/Scripts/python scripts/pytest_postgres.py     # same suite on a real PostgreSQL

# Frontend (Node 20)
cd frontend
npm install
npm run dev        # http://localhost:3000, proxies /api to 127.0.0.1:8000
```

For a local run without Active Directory, set `DEV_MODE=true` (any username + `DEV_PASSWORD` logs in;
users listed in `ADMIN_USERS` are admins) and add a local folder as a share. Local folders have no
Windows ACLs, so the permission reports stay empty until you scan a real share.
