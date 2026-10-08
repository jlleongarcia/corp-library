import os

# Settings are read at import time, so configure the environment first.
os.environ.update({
    "DATABASE_URL": "sqlite://",
    "DEV_MODE": "true",
    "DEV_GROUPS": "",
    "ADMIN_USERS": "admin",
    "LDAP_SERVER": "",
    "KERBEROS_KEYTAB": "",
    "COOKIE_SECURE": "false",  # the test client talks plain http
    "OCR_ENABLED": "false",  # tests that need OCR fake it
    "SCAN_HOUR": "-1",
    "DEDUPE_MIN_SIZE": "1",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import get_db, make_engine  # noqa: E402
from app.main import app  # noqa: E402

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def migrate(engine) -> None:
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "alembic"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _fresh_process_state():
    # Module-level caches outlive a test's database; ids are reused by the next one.
    from app.auth import sessions

    sessions._refresh_failed_at.clear()
    yield


@pytest.fixture
def engine(tmp_path):
    # SQLite by default; set TEST_DATABASE_URL to run the suite against PostgreSQL.
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        eng = make_engine(url)
        with eng.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    else:
        eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as session:
        yield session


@pytest.fixture
def client(engine):
    Session = sessionmaker(bind=engine, autoflush=False)

    def _get_db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    # Like the frontend: every request carries the CSRF header.
    with TestClient(app, headers={"X-Requested-With": "XMLHttpRequest"}) as c:
        yield c
    app.dependency_overrides.clear()


def sign_in(client, username: str) -> dict:
    """DEV_MODE sign-in; the session cookie stays in the client."""
    r = client.post("/auth/login", json={"username": username})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def admin(client):
    return sign_in(client, "admin")
