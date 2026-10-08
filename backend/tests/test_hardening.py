"""Regression tests for the fixes recorded in docs/DEBUGGING.md."""

import ssl
from datetime import datetime, timezone

import pytest

from sqlalchemy import select

from app import worker
from app.acl.descriptor import sid_to_bytes
from app.auth import ldap_client
from app.auth.sessions import COOKIE
from app.config import Settings, dev_mode_problem, settings
from app.models import AuthSession, Share
from app.services import scanner, sources

from .conftest import sign_in

ALICE_SID_BYTES = bytes([1, 5, 0, 0, 0, 0, 0, 5, 21, 0, 0, 0]) + (1000).to_bytes(4, "little") * 3 + (1101).to_bytes(4, "little")
DOMAIN_USERS = "S-1-5-21-1000-1000-1000-513"
FINANCE = "S-1-5-21-1000-1000-1000-2201"


# ── BUG-002: forged sign-ins ─────────────────────────────────────────────────
# Sessions are random tokens looked up in the database: there is no signing key
# to leak, and the database only holds their hashes.

def test_unknown_or_forged_session_cookie_is_rejected(client):
    client.cookies.set(COOKIE, "made-up-token")
    assert client.get("/auth/me").status_code == 401


def test_session_token_is_stored_hashed_and_logout_revokes_it(client, db):
    sign_in(client, "alice")
    token = client.cookies.get(COOKIE)
    row = db.scalar(select(AuthSession))
    assert token and row.token_hash != token and len(row.token_hash) == 64

    assert client.post("/auth/logout").status_code == 204
    assert db.scalar(select(AuthSession)) is None
    client.cookies.set(COOKIE, token)  # replaying the old cookie
    assert client.get("/auth/me").status_code == 401


def test_session_cookie_is_httponly_and_secure_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    r = client.post("/auth/login", json={"username": "alice"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_state_changing_requests_need_the_csrf_header(client):
    sign_in(client, "admin")
    r = client.post("/admin/shares", json={"name": "X", "path": "x"}, headers={"X-Requested-With": ""})
    assert r.status_code == 403


# ── BUG-003 / BUG-010: LDAP ──────────────────────────────────────────────────

def test_ldaps_always_validates_the_certificate(monkeypatch):
    monkeypatch.setattr(settings, "ldap_server", "dc01.company.com")
    monkeypatch.setattr(settings, "ldap_use_ssl", True)
    monkeypatch.setattr(settings, "ldap_ca_cert_file", "")
    server = ldap_client.make_server()
    assert server.tls.validate == ssl.CERT_REQUIRED
    assert server.tls.valid_names == ["dc01.company.com"]


class FakeConnection:
    """
    Stands in for ldap3.Connection: the bind succeeds, the account search returns
    `results`, and the tokenGroups read (a base-scope search) returns `groups`.
    """

    results: list = []
    groups: list[str] = [DOMAIN_USERS, FINANCE]
    last_filter = None

    def __init__(self, server, user, password, **kwargs):
        self.response = None

    def search(self, search_base, search_filter, search_scope=None, **kwargs):
        if search_scope == ldap_client.BASE:
            raw = [sid_to_bytes(s) for s in self.groups]
            self.response = [{"type": "searchResEntry", "dn": search_base, "raw_attributes": {"tokenGroups": raw}}]
            return
        FakeConnection.last_filter = search_filter
        self.response = self.results

    def unbind(self):
        pass


def _entry(sam):
    return {
        "type": "searchResEntry",
        "dn": f"CN={sam},DC=company,DC=com",
        "attributes": {"sAMAccountName": sam, "displayName": sam.title(), "mail": ""},
        "raw_attributes": {"objectSid": [ALICE_SID_BYTES]},
    }


@pytest.fixture
def fake_ldap(monkeypatch):
    monkeypatch.setattr(ldap_client, "Connection", FakeConnection)
    monkeypatch.setattr(ldap_client, "make_server", lambda: None)
    FakeConnection.results = []
    FakeConnection.groups = [DOMAIN_USERS, FINANCE]
    return FakeConnection


def test_login_identity_is_the_account_ad_returns(fake_ldap):
    fake_ldap.results = [{"type": "searchResRef", "uri": ["ldap://ForestDnsZones"]}, _entry("JDoe")]
    user = ldap_client.authenticate_ldap("jdoe", "pw")
    assert user.username == "jdoe" and user.sid == "S-1-5-21-1000-1000-1000-1101"
    assert user.group_sids == [DOMAIN_USERS, FINANCE]  # tokenGroups: nested groups included


def test_unreadable_token_groups_fail_the_sign_in(fake_ldap):
    # Signing someone in with fewer groups than they have would silently hide
    # their documents: AD not answering is an error, not "no groups".
    fake_ldap.results = [_entry("jdoe")]
    fake_ldap.groups = []
    with pytest.raises(ldap_client.DirectoryUnavailable):
        ldap_client.authenticate_ldap("jdoe", "pw")


def test_disabled_account_is_not_found(fake_ldap):
    entry = _entry("jdoe")
    entry["attributes"]["userAccountControl"] = 514  # NORMAL_ACCOUNT | ACCOUNTDISABLE
    fake_ldap.results = [entry]
    assert ldap_client.authenticate_ldap("jdoe", "pw") is None


def test_login_with_no_or_ambiguous_account_fails_closed(fake_ldap):
    assert ldap_client.authenticate_ldap("jdoe", "pw") is None
    fake_ldap.results = [_entry("a"), _entry("b")]
    assert ldap_client.authenticate_ldap("jdoe", "pw") is None


def test_username_is_escaped_in_the_ldap_filter(fake_ldap):
    ldap_client.authenticate_ldap("x)(sAMAccountName=*", "pw")
    assert fake_ldap.last_filter == r"(sAMAccountName=x\29\28sAMAccountName=\2a)"


# ── BUG-017: DEV_MODE can't run in production ─────────────────────────────────

@pytest.mark.parametrize("overrides", [
    {"ldap_server": "dc01.company.com"},
    {"kerberos_keytab": "/secrets/http.keytab"},
    {"database_url": "postgresql+psycopg://corplib:pw@db:5432/corplib"},  # the production stack
])
def test_dev_mode_is_refused_outside_a_developer_pc(overrides):
    base = {"database_url": "postgresql+psycopg://postgres@127.0.0.1:54329/corplib_dev", "ldap_server": ""}
    assert dev_mode_problem(Settings(dev_mode=True, **base)) is None
    assert dev_mode_problem(Settings(dev_mode=True, **(base | overrides))) is not None


def test_dev_login_refused_if_ldap_appears(client, monkeypatch):
    monkeypatch.setattr(settings, "ldap_server", "dc01.company.com")
    assert client.post("/auth/login", json={"username": "admin"}).status_code == 500


# ── BUG-014: ignore list is case-insensitive ──────────────────────────────────

def test_scan_ignore_list_ignores_case():
    assert scanner._ignored("THUMBS.DB") and scanner._ignored("Desktop.INI") and scanner._ignored("~$Report.docx")
    assert not scanner._ignored("thumbs.db.txt")


# ── BUG-004: SMB credentials survive reconnects ──────────────────────────────

def test_smb_credentials_become_the_client_default(monkeypatch):
    import smbclient

    monkeypatch.setattr(settings, "smb_username", "svc-scan@company.com")
    monkeypatch.setattr(settings, "smb_password", "secret")
    try:
        sources.configure_smb_client()
        cfg = smbclient.ClientConfig()
        assert (cfg.username, cfg.password) == ("svc-scan@company.com", "secret")
    finally:
        smbclient.ClientConfig(username=None, password=None)


# ── BUG-008: nightly schedule ────────────────────────────────────────────────

def _at(day, hour, minute=0):
    return datetime(2020, 1, day, hour, minute, tzinfo=timezone.utc)


def test_nightly_scan_catches_up_after_a_long_job(db, monkeypatch):
    monkeypatch.setattr(settings, "scan_hour", 2)
    db.add(Share(name="Finance", path="x"))
    db.commit()
    calls = []
    real = worker.jobs.enqueue_full_pipeline
    monkeypatch.setattr(worker.jobs, "enqueue_full_pipeline",
                        lambda db, requested_by=None: calls.append(1) or real(db, requested_by))

    # Busy from 01:30 to 05:30: still queued when the worker frees up.
    slot = worker.maybe_schedule(db, None, now=_at(1, 5, 30))
    assert calls == [1] and slot == _at(1, 2)
    # Same night again, or after a restart that forgot `slot`: not queued twice.
    assert worker.maybe_schedule(db, slot, now=_at(1, 5, 35)) == slot
    worker.maybe_schedule(db, None, now=_at(1, 6))
    assert calls == [1]
    # Too late (worker busy all morning): wait for the next night.
    assert worker.maybe_schedule(db, None, now=_at(2, 7)) is None
    # Before SCAN_HOUR, the previous night's slot is long past.
    assert worker.maybe_schedule(db, None, now=_at(3, 1)) is None
    assert calls == [1]
