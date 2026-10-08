"""
Kerberos SSO. Only the ticket validation itself (gssapi + keytab, Linux only)
is faked; the HTTP exchange, realm check, AD lookup and session are real.
"""

import base64

import pytest
from sqlalchemy import select

from app.auth import kerberos
from app.auth.ldap_client import DirectoryUnavailable, LDAPUser
from app.config import settings
from app.models import AuditEvent, AuthSession
from app.routers import auth as auth_router

ALICE = LDAPUser("alice", "Alice", "alice@company.com", "S-1-5-21-1-2-3-1101", ["S-1-5-21-1-2-3-2201"])


def negotiate(token: bytes) -> dict:
    return {"Authorization": "Negotiate " + base64.b64encode(token).decode()}


@pytest.fixture
def sso(monkeypatch):
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "kerberos_keytab", "/secrets/http.keytab")
    monkeypatch.setattr(settings, "ldap_domain", "company.com")
    monkeypatch.setattr(settings, "kerberos_realm", "")
    tickets = {b"ticket-alice": ("alice@COMPANY.COM", b"mutual"), b"ticket-evil": ("alice@EVIL.ORG", None)}

    def acceptor(token):
        if token not in tickets:
            raise RuntimeError("GSSError: invalid token")
        return tickets[token]

    monkeypatch.setattr(kerberos, "acceptor", acceptor)
    monkeypatch.setattr(auth_router, "lookup_user", lambda name: ALICE if name == "alice" else None)


def test_auth_config_tells_the_ui_what_to_try(client, sso):
    assert client.get("/auth/config").json() == {"app_name": settings.app_name, "sso_enabled": True, "dev_mode": False}


def test_challenge_then_ticket_signs_in(client, db, sso):
    r = client.get("/auth/sso")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Negotiate"

    r = client.get("/auth/sso", headers=negotiate(b"ticket-alice"))
    assert r.status_code == 200 and r.json()["username"] == "alice"
    assert r.headers["www-authenticate"] == "Negotiate " + base64.b64encode(b"mutual").decode()
    assert client.get("/auth/me").json()["username"] == "alice"

    session = db.scalar(select(AuthSession))
    assert session.method == "sso"
    assert {"S-1-5-21-1-2-3-1101", "S-1-5-21-1-2-3-2201", "S-1-5-21-1-2-3-513", "S-1-1-0"} <= set(session.token_sids)


@pytest.mark.parametrize("token", [b"ticket-evil", b"garbage", b"NTLMSSP\x00\x01\x00\x00\x00"])
def test_bad_tickets_fail_without_a_second_challenge(client, db, sso, token):
    r = client.get("/auth/sso", headers=negotiate(token))
    # 403, not 401: another challenge would make the browser loop; the form takes over.
    assert r.status_code == 403 and "www-authenticate" not in r.headers
    assert db.scalar(select(AuthSession)) is None
    assert db.scalar(select(AuditEvent.action)) == "sign_in_failed"


def test_sso_user_unknown_to_ad_is_refused(client, sso, monkeypatch):
    monkeypatch.setattr(auth_router, "lookup_user", lambda name: None)
    assert client.get("/auth/sso", headers=negotiate(b"ticket-alice")).status_code == 403


def test_ad_down_is_a_503_not_a_wrong_password(client, sso, monkeypatch):
    def down(*_):
        raise DirectoryUnavailable("unreachable")

    monkeypatch.setattr(auth_router, "lookup_user", down)
    assert client.get("/auth/sso", headers=negotiate(b"ticket-alice")).status_code == 503
    monkeypatch.setattr(auth_router, "authenticate_ldap", down)
    assert client.post("/auth/login", json={"username": "alice", "password": "pw"}).status_code == 503


def test_password_form_is_the_fallback(client, sso, monkeypatch):
    monkeypatch.setattr(auth_router, "authenticate_ldap", lambda u, p: ALICE if p == "right" else None)
    assert client.post("/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    r = client.post("/auth/login", json={"username": "ALICE ", "password": "right"})
    assert r.status_code == 200 and r.json()["username"] == "alice"


def test_sso_off_when_no_keytab(client):
    assert client.get("/auth/sso").status_code == 404


# ── BUG-029: the sign-in form must not lock AD accounts ───────────────────────

@pytest.fixture
def ldap_form(client, monkeypatch):
    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setattr(settings, "ldap_domain", "company.com")
    monkeypatch.setattr(settings, "login_max_failures", 3)
    calls = []

    def authenticate(username, password):
        calls.append(username)
        return ALICE if (username, password) == ("alice", "right") else None

    monkeypatch.setattr(auth_router, "authenticate_ldap", authenticate)
    return calls


def test_repeated_wrong_passwords_stop_reaching_ad(client, db, ldap_form):
    for _ in range(3):
        assert client.post("/auth/login", json={"username": "alice", "password": "x"}).status_code == 401
    r = client.post("/auth/login", json={"username": "ALICE", "password": "right"})
    assert r.status_code == 429 and "Too many failed sign-ins" in r.json()["detail"]
    assert int(r.headers["retry-after"]) > 0
    assert len(ldap_form) == 3  # AD only saw the first three
    assert db.scalar(select(AuditEvent).where(AuditEvent.detail["reason"].as_string() == "throttled")) is not None
    # Other accounts are unaffected.
    assert client.post("/auth/login", json={"username": "bob", "password": "x"}).status_code == 401


def test_throttle_window_expires(client, ldap_form, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.auth import throttle

    long_ago = datetime.now(timezone.utc) - timedelta(minutes=settings.login_window_minutes + 1)
    for _ in range(3):
        throttle.record_failure("alice", now=long_ago)
    assert client.post("/auth/login", json={"username": "alice", "password": "right"}).status_code == 200


@pytest.mark.parametrize("typed", ["alice", r"COMPANY\alice", "alice@company.com", " Alice@COMPANY.COM "])
def test_domain_forms_of_the_username_are_accepted(client, ldap_form, typed):
    r = client.post("/auth/login", json={"username": typed, "password": "right"})
    assert r.status_code == 200 and ldap_form == ["alice"]
