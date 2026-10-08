"""
Run the backend locally without Docker:

    uv run scripts/dev.py

Starts a local PostgreSQL (data kept in backend/.devdata/), applies the
migrations, then runs the API on http://127.0.0.1:8000 (auto-reload) and the
worker. Settings come from the repo-root .env; use DEV_MODE=true to sign in
without Active Directory (any username, no password; DEV_GROUPS gives fake
groups). Ctrl+C stops everything.

PostgreSQL binaries come from the `pgserver` package (dev dependency), but the
server is managed here: it runs detached from the console so Ctrl+C can't kill
it mid-transaction, and its log lives outside the data folder (Windows crash
recovery can't open a data-folder file that's held open as the log).
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pgserver
import psycopg

BACKEND = Path(__file__).resolve().parents[1]
DEVDATA = BACKEND / ".devdata"
PG_DATA = DEVDATA / "postgres"
PG_LOG = DEVDATA / "postgres.log"
PG_BIN = Path(pgserver.__file__).parent / "pginstall" / "bin"
PG_PORT = int(os.environ.get("DEV_PG_PORT", "54329"))
PG_USER = "postgres"
DB_NAME = "corplib_dev"

# Detach PostgreSQL from this console: no Ctrl+C delivery, no console window.
DETACHED = (
    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
)


def pg(tool: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run([str(PG_BIN / tool), *args], **kwargs)


def postgres_running() -> bool:
    return pg("pg_ctl", "status", "-D", str(PG_DATA), capture_output=True).returncode == 0


def start_postgres() -> None:
    if not (PG_DATA / "PG_VERSION").exists():
        print(f"Creating a new database cluster in {PG_DATA} ...")
        PG_DATA.mkdir(parents=True, exist_ok=True)
        pg("initdb", "-D", str(PG_DATA), "-U", PG_USER, "--auth=trust", "--encoding=UTF8",
           check=True, capture_output=True)
    (PG_DATA / "log").unlink(missing_ok=True)  # pgserver's old in-folder log; see module docstring

    if postgres_running():
        print("PostgreSQL already running; stopping it to restart on the expected port ...")
        stop_postgres()
    else:
        # A crash leaves postmaster.pid behind, still marked "ready"; pg_ctl -w would
        # read it and report success before the new server is actually up.
        (PG_DATA / "postmaster.pid").unlink(missing_ok=True)

    print(f"Starting PostgreSQL on 127.0.0.1:{PG_PORT} (log: {PG_LOG}) ...")
    # -t 120: after an unclean shutdown, crash recovery can take a while.
    # No pipes: the server would inherit them and keep them open, so waiting for
    # pg_ctl's output would never finish. Its messages go to the log instead.
    result = pg(
        "pg_ctl", "start", "-D", str(PG_DATA), "-l", str(PG_LOG), "-w", "-t", "120",
        "-o", f"-h 127.0.0.1 -p {PG_PORT}",
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=DETACHED,
    )
    if result.returncode != 0:
        print(f"PostgreSQL failed to start. Last lines of {PG_LOG}:")
        print("".join(PG_LOG.read_text(errors="replace").splitlines(keepends=True)[-20:]))
        sys.exit(1)
    wait_until_ready()


ADMIN_DSN = f"host=127.0.0.1 port={PG_PORT} user={PG_USER} dbname=postgres connect_timeout=2"


def wait_until_ready(timeout: float = 120) -> None:
    """Don't trust pg_ctl alone: wait until the server accepts a real connection."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            psycopg.connect(ADMIN_DSN).close()
            return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                print(f"PostgreSQL didn't accept connections within {timeout:.0f}s; see {PG_LOG}")
                sys.exit(1)
            time.sleep(0.5)


def stop_postgres() -> None:
    pg("pg_ctl", "stop", "-D", str(PG_DATA), "-m", "fast", "-w",
       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_database() -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{DB_NAME}"')


def main() -> int:
    sys.path.insert(0, str(BACKEND))
    from app.config import ROOT_ENV, settings  # reads the repo-root .env

    if not ROOT_ENV.exists():
        print(f"Note: {ROOT_ENV} not found; using defaults. Copy .env.example and set DEV_MODE=true.")
    if not settings.dev_mode and not settings.ldap_server:
        print("Warning: DEV_MODE is off and LDAP isn't configured, so nobody can sign in.")
    if settings.dev_mode and settings.ldap_server:
        print("Error: DEV_MODE=true needs LDAP_SERVER empty (the API would refuse to start).")
        return 1

    DEVDATA.mkdir(exist_ok=True)
    start_postgres()
    procs: list[subprocess.Popen] = []
    try:
        ensure_database()
        url = f"postgresql+psycopg://{PG_USER}@127.0.0.1:{PG_PORT}/{DB_NAME}"
        # The environment wins over .env, so this points the app at the local database.
        # The UI is served over plain http on localhost, so the session cookie can't be Secure.
        env = dict(os.environ, DATABASE_URL=url, PYTHONUNBUFFERED="1", COOKIE_SECURE="false")
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
        print(f"DB:   {url.replace('+psycopg', '')}")
        print("UI:   cd frontend && npm run dev  ->  http://localhost:5173")
        print("Ctrl+C to stop.\n")
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        # The API and worker get Ctrl+C from the console too; give them time to exit.
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.terminate()
        print("Stopping PostgreSQL ...")
        stop_postgres()
        print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
