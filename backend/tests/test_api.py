from sqlalchemy.orm import sessionmaker

from app.models import GroupMember, Principal, Share
from app.services import jobs
from app.services.dedupe import run_dedupe
from app.services.directory import resolve_principals
from app.services.scanner import scan_share
from app.services.sources import LocalSource

from .test_scanner import FINANCE, HR, FlakySource, sd_provider, tree  # noqa: F401  (fixture)

ALICE = "S-1-5-21-1000-2000-3000-1101"
BOB = "S-1-5-21-1000-2000-3000-1102"


class FakeDirectory:
    entries = {
        FINANCE: {"name": "DEPT-Finance", "display_name": "DEPT-Finance", "kind": "group", "dn": "CN=Fin"},
        HR: {"name": "DEPT-HR", "display_name": "DEPT-HR", "kind": "group", "dn": "CN=HR"},
        ALICE: {"name": "alice", "display_name": "Alice", "kind": "user", "dn": "CN=Alice"},
        BOB: {"name": "bob", "display_name": "Bob", "kind": "user", "dn": "CN=Bob"},
    }
    members = {"CN=Fin": [ALICE, BOB], "CN=HR": [BOB]}

    def lookup_sid(self, sid):
        return self.entries.get(sid)

    def group_user_members(self, dn):
        return [{"sid": s, **self.entries[s]} for s in self.members[dn]]


class BrokenDirectory(FakeDirectory):
    """The domain controller stops answering, as during a network blip."""

    def lookup_sid(self, sid):
        raise ConnectionError("LDAP server unreachable")

    def group_user_members(self, dn):
        raise ConnectionError("LDAP server unreachable")


def test_login_and_admin_guard(client):
    assert client.get("/admin/shares").status_code == 401
    r = client.post("/auth/login", json={"username": "someone"})
    assert r.status_code == 200 and r.json()["is_admin"] is False
    assert client.get("/admin/shares").status_code == 403


def test_share_crud_and_scan_request(client, admin, tree):
    r = client.post("/admin/shares", json={"name": "Finance", "path": str(tree)})
    assert r.status_code == 201
    share_id = r.json()["id"]
    assert client.post("/admin/shares", json={"name": "Finance", "path": "x"}).status_code == 409

    r = client.post("/admin/scans", json={"share_id": share_id})
    assert r.status_code == 202 and r.json()[0]["kind"] == "scan"
    # Requesting again doesn't queue a duplicate.
    r2 = client.post("/admin/scans", json={})
    assert r2.json()[0]["id"] == r.json()[0]["id"]

    assert client.put(f"/admin/shares/{share_id}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/admin/shares/{share_id}").status_code == 204


def test_job_queue(db):
    job = jobs.enqueue(db, jobs.DEDUPE)
    assert jobs.enqueue(db, jobs.DEDUPE).id == job.id
    claimed = jobs.claim_next(db)
    assert claimed.id == job.id and claimed.status == "running"
    assert jobs.claim_next(db) is None
    assert jobs.fail_interrupted(db) == 1
    db.refresh(job)
    assert job.status == "failed"


def _scanned(engine, tree):  # noqa: F811
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        share = Share(name="Finance", path=str(tree))
        db.add(share)
        db.commit()
        src = LocalSource(str(tree), sd_provider)
        scan_share(db, share, src)
        run_dedupe(db, {share.id: src})
        resolve_principals(db, FakeDirectory())
        return share.id


def test_reports(client, admin, engine, tree):  # noqa: F811
    _scanned(engine, tree)

    s = client.get("/admin/reports/summary").json()
    assert s["shares"][0]["files"] == 5 and s["shares"][0]["last_scan_status"] == "success"
    assert {e["extension"] for e in s["by_extension"]} == {"xlsx", "pdf", "txt"}
    assert sum(b["files"] for b in s["by_age"]) == 5

    d = client.get("/admin/reports/duplicates").json()
    assert d["total_groups"] == 1 and d["groups"][0]["copies"] == 2
    assert d["groups"][0]["confidence"] == "exact"

    csv = client.get("/admin/reports/duplicates?format=csv")
    assert csv.headers["content-type"].startswith("text/csv") and "2025.xlsx" in csv.text

    assert client.get("/admin/reports/stale?years=1").json() == []
    hyg = client.get("/admin/reports/hygiene").json()
    assert hyg["empty_folders"]["count"] == 0

    exc = client.get("/admin/reports/acl-exceptions").json()
    paths = {e["path"].replace(str(tree), "<root>") for e in exc}
    assert paths == {"<root>", "<root>\\HR"}  # share root + the folder with its own permissions
    hr = next(e for e in exc if e["path"].endswith("HR"))
    assert hr["inheritance_disabled"] and hr["entries"][0]["name"] == "DEPT-HR"


def test_permission_grid(client, admin, engine, tree):  # noqa: F811
    _scanned(engine, tree)
    grid = client.get("/admin/reports/permissions").json()
    cols = {c["path"].replace(str(tree), "<root>"): c["folder_id"] for c in grid["columns"]}
    assert set(cols) == {"<root>", "<root>\\HR"}
    rows = {r["name"]: r["cells"] for r in grid["rows"]}
    root, hr = str(cols["<root>"]), str(cols["<root>\\HR"])
    assert rows["All domain users"] == {root: "none", hr: "none"}
    assert rows["alice"] == {root: "read", hr: "none"}  # Finance only
    assert rows["bob"] == {root: "read", hr: "read"}  # Finance + HR

    csv = client.get("/admin/reports/permissions?format=csv")
    assert csv.status_code == 200 and "Alice" in csv.text


def test_group_members_are_replaced_on_refresh(db, engine, tree):  # noqa: F811
    _scanned(engine, tree)
    FakeDirectory.members["CN=Fin"] = [ALICE]
    try:
        resolve_principals(db, FakeDirectory(), force=True)
        members = {m.member_sid for m in db.query(GroupMember).filter_by(group_sid=FINANCE)}
        assert members == {ALICE}
        assert db.get(Principal, FINANCE).kind == "group"
    finally:
        FakeDirectory.members["CN=Fin"] = [ALICE, BOB]


def test_ldap_outage_keeps_known_principals(db, engine, tree):  # noqa: F811
    _scanned(engine, tree)
    before = db.get(Principal, FINANCE).resolved_at
    stats = resolve_principals(db, BrokenDirectory(), force=True)
    assert stats["errors"] > 0
    db.expire_all()
    fin = db.get(Principal, FINANCE)
    assert fin.kind == "group" and fin.name == "DEPT-Finance"  # not demoted to "unknown"
    assert fin.resolved_at == before  # retried on the next run
    members = {m.member_sid for m in db.query(GroupMember).filter_by(group_sid=FINANCE)}
    assert members == {ALICE, BOB}


def test_member_expansion_failure_keeps_previous_members(db, engine, tree):  # noqa: F811
    _scanned(engine, tree)

    class MembersDown(FakeDirectory):
        def group_user_members(self, dn):
            raise ConnectionError("timeout")

    resolve_principals(db, MembersDown(), force=True)
    members = {m.member_sid for m in db.query(GroupMember).filter_by(group_sid=FINANCE)}
    assert members == {ALICE, BOB}


def test_group_members_named_without_extra_lookups(db, engine, tree):  # noqa: F811
    _scanned(engine, tree)
    assert db.get(Principal, ALICE).display_name == "Alice"  # from the member search itself


def test_hygiene_reports_unlisted_folders_not_empty(client, admin, engine, tree):  # noqa: F811
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as db:
        share = Share(name="Finance", path=str(tree))
        db.add(share)
        db.commit()
        scan_share(db, share, LocalSource(str(tree), sd_provider))
        # Second scan: "Budget/Old" can't be listed. It must not turn up as empty.
        scan_share(db, share, FlakySource(str(tree), "Budget/Old"))
    hyg = client.get("/admin/reports/hygiene").json()
    assert hyg["empty_folders"]["count"] == 0
    assert hyg["unlisted_folders"]["count"] == 1
    assert "STATUS_NETWORK_NAME_DELETED" in hyg["unlisted_folders"]["items"][0]["error"]
    csv = client.get("/admin/reports/hygiene?format=csv")
    assert "could not list" in csv.text


# ── BUG-015: pagination parameters are validated ─────────────────────────────

def test_negative_limit_or_offset_is_a_422_not_a_500(client, admin):
    for url in ("/admin/jobs?limit=-1", "/admin/scan-runs?limit=0", "/admin/reports/duplicates?offset=-5",
                "/admin/reports/stale?limit=-1", "/admin/reports/audit?offset=-1", "/search?limit=0"):
        assert client.get(url).status_code == 422, url
