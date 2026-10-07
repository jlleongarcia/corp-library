"""
Run the backend locally without Docker:

    uv run scripts/dev.py

Starts an embedded PostgreSQL (data kept in backend/.devdata/), applies the
migrations, then runs the API on http://127.0.0.1:8000 (auto-reload) and the
worker. Settings come from the repo-root .env; use DEV_MODE=true to log in
without Active Directory. Ctrl+C stops everything.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pgserver

BACKEND = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND / ".devdata" / "postgres"
DB_NAME = "corplib_dev"


def main() -> int:
    sys.path.insert(0, str(BACKEND))
    from app.config import ROOT_ENV, settings  # reads the repo-root .env

    if not ROOT_ENV.exists():
        print(f"Note: {ROOT_ENV} not found; using defaults. Copy .env.example and set DEV_MODE=true.")
    if not settings.dev_mode and not settings.ldap_server:
        print("Warning: DEV_MODE is off and LDAP isn't configured, so nobody can log in.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Starting PostgreSQL ({DATA_DIR}) ...")
    server = pgserver.get_server(DATA_DIR, cleanup_mode="stop")
    if not server.psql(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}';").strip().endswith("1"):
        server.psql(f"CREATE DATABASE {DB_NAME};")
    url = server.get_uri().rsplit("/", 1)[0].replace("postgresql://", "postgresql+psycopg://", 1) + f"/{DB_NAME}"

    # The environment wins over .env, so this points the app at the local database.
    env = dict(os.environ, DATABASE_URL=url, PYTHONUNBUFFERED="1")
    py = sys.executable
    subprocess.run([py, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)

    procs = [
        subprocess.Popen(
            [py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000",
             "--reload", "--reload-dir", "app"],
            cwd=BACKEND, env=env,
        ),
        subprocess.Popen([py, "-m", "app.worker"], cwd=BACKEND, env=env),
    ]
    print("\nAPI:  http://127.0.0.1:8000  (docs at /docs)")
    print("UI:   cd frontend && npm run dev  ->  http://localhost:5173")
    print("Ctrl+C to stop.\n")

    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        server.cleanup()
        # Stop PostgreSQL explicitly: pgserver keeps it running if it thinks
        # another handle (e.g. a previous interrupted run) still uses it.
        pg_ctl = Path(pgserver.__file__).parent / "pginstall" / "bin" / "pg_ctl"
        subprocess.run([str(pg_ctl), "stop", "-D", str(DATA_DIR), "-m", "fast"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
