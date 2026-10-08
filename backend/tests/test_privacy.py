"""BUG-033: what the privacy notice states must be what the app does."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import worker
from app.config import settings
from app.models import AuditEvent, AuthSession, User

from .conftest import sign_in


def test_privacy_facts_are_public_and_say_what_is_missing(client, monkeypatch):
    r = client.get("/privacy")  # no session: the notice must be readable before signing in
    assert r.status_code == 200
    assert r.json()["missing"] == [
        "PRIVACY_CONTROLLER", "PRIVACY_CONTROLLER_ID", "PRIVACY_CONTROLLER_ADDRESS", "PRIVACY_CONTACT",
        "PRIVACY_DPO", "PRIVACY_RECORD_URL",  # both mandatory for a public body
    ]
    assert r.json()["authority_name"].endswith("(AEPD)")  # unless a regional authority is set
    monkeypatch.setattr(settings, "privacy_controller", "Dirección General de Ejemplo")
    monkeypatch.setattr(settings, "privacy_controller_id", "S0000000A")
    monkeypatch.setattr(settings, "privacy_controller_address", "Calle Mayor 1, Madrid")
    monkeypatch.setattr(settings, "privacy_contact", "privacidad@ejemplo.es")
    monkeypatch.setattr(settings, "privacy_dpo", "dpd@ejemplo.es")
    monkeypatch.setattr(settings, "privacy_record_url", "https://transparencia.ejemplo.es/rat#corp-library")
    info = client.get("/privacy").json()
    assert info["missing"] == [] and info["controller"] == "Dirección General de Ejemplo"
    assert info["audit_retention_days"] == settings.audit_retention_days


def test_reading_the_audit_log_is_itself_recorded(client, db):
    sign_in(client, "admin")
    client.get("/admin/reports/audit", params={"username": "alice"})
    client.get("/admin/reports/audit", params={"username": "alice", "offset": 200})  # next page: not again
    [read] = db.scalars(select(AuditEvent).where(AuditEvent.action == "audit_read")).all()
    assert read.username == "admin" and read.detail["about_user"] == "alice"


def test_unused_accounts_are_deleted_after_the_retention_period(client, db):
    sign_in(client, "alice")
    sign_in(client, "bob")
    long_ago = datetime.now(timezone.utc) - timedelta(days=settings.audit_retention_days + 1)
    for user in db.scalars(select(User)):
        user.last_login = long_ago
    db.execute(AuthSession.__table__.delete().where(
        AuthSession.user_id == db.scalar(select(User.id).where(User.username == "alice"))))
    db.commit()
    worker.housekeeping(db)
    # bob still has a live session: kept until it ends.
    assert db.scalars(select(User.username)).all() == ["bob"]
