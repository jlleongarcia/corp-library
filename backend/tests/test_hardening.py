"""Regression tests for the fixes recorded in docs/DEBUGGING.md."""

import ssl
from datetime import datetime, timezone

import pytest

from app import worker
from app.auth import ldap_client
from app.config import Settings, secret_key_problem, settings
from app.models import Share
from app.services import sources

ALICE_SID_BYTES = bytes([1, 5, 0, 0, 0, 0, 0, 5, 21, 0, 0, 0]) + (1000).to_bytes(4, "little") * 3 + (1101).to_bytes(4, "little")


# ── BUG-002: SECRET_KEY ──────────────────────────────────────────────────────

@pytest.mark.parametrize("secret", ["", "change-me", Settings.model_fields["secret_key"].default, "short-but-not-placeholder"])
def test_weak_secret_keys_are_rejected(secret):
    assert secret_key_problem(Settings(secret_key=secret)) is not None


def test_long_random_secret_key_is_accepted():
    assert secret_key_problem(Settings(secret_key="a" * 64)) is None


# ── BUG-003 / BUG-010: LDAP ──────────────────────────────────────────────────

def test_ldaps_always_validates_the_certificate(monkeypatch):
    monkeypatch.setattr(settings, "ldap_server", "dc01.company.com")
    monkeypatch.setattr(settings, "ldap_use_ssl", True)
    monkeypatch.setattr(settings, "ldap_ca_cert_file", "")
    server = ldap_client.make_server()
    assert server.tls.validate == ssl.CERT_REQUIRED
    assert server.tls.valid_names == ["dc01.company.com"]


class FakeConnection:
    """Stands in for ldap3.Connection: the bind succeeds, the search returns `results`."""

    results: list = []
    last_filter = None

    def __init__(self, server, user, password, **kwargs):
        self.response = None

    def search(self, search_base, search_filter, **kwargs):
        FakeConnection.last_filter = search_filter
        self.response = self.results

    def unbind(self):
        pass


def _entry(sam):
    return {
        "type": "searchResEntry",
        "attributes": {"sAMAccountName": sam, "displayName": sam.title(), "mail": ""},
        "raw_attributes": {"objectSid": [ALICE_SID_BYTES]},
    }


@pytest.fixture
def fake_ldap(monkeypatch):
    monkeypatch.setattr(ldap_client, "Connection", FakeConnection)
    monkeypatch.setattr(ldap_client, "make_server", lambda: None)
    FakeConnection.results = []
    return FakeConnection


def test_login_identity_is_the_account_ad_returns(fake_ldap):
    fake_ldap.results = [{"type": "searchResRef", "uri": ["ldap://ForestDnsZones"]}, _entry("JDoe")]
    user = ldap_client.authenticate_ldap("jdoe", "pw")
    assert user.username == "jdoe" and user.sid == "S-1-5-21-1000-1000-1000-1101"


def test_login_with_no_or_ambiguous_account_fails_closed(fake_ldap):
    assert ldap_client.authenticate_ldap("jdoe", "pw") is None
    fake_ldap.results = [_entry("a"), _entry("b")]
    assert ldap_client.authenticate_ldap("jdoe", "pw") is None


def test_username_is_escaped_in_the_ldap_filter(fake_ldap):
    ldap_client.authenticate_ldap("x)(sAMAccountName=*", "pw")
    assert fake_ldap.last_filter == r"(sAMAccountName=x\29\28sAMAccountName=\2a)"


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
