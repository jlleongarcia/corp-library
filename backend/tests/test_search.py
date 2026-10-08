"""
Phase 1 end to end: scan, index, then search / browse / open through the API as
users with different groups. Permissions come from .corplib-acl.json files
(services/devacl.py), so the real ACL code paths run.

    share/
      readme.txt                 everyone
      Finance/   read: finance   presupuesto 2025.docx, Informe-ventas.pdf
      HR/        read: hr, deny: alice
                                 contratos.txt
      Public/    list: everyone, read: finance   ("this folder only" for everyone else)
                                 notice.txt
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth import sessions
from app.config import settings
from app.models import AuditEvent, AuthSession, Document, File, Share
from app.services.indexer import run_index
from app.services.scanner import scan_share

from . import docs
from .conftest import sign_in


def write(path, content: bytes | str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content.encode("utf-8") if isinstance(content, str) else content)


def acl(folder, **rules):
    write(folder / ".corplib-acl.json", json.dumps(rules))


@pytest.fixture
def library(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "dev_groups", "alice:finance,hr;bob:hr;carol:")
    root = tmp_path / "share"
    write(root / "readme.txt", "Welcome to the department library")
    write(root / "Finance" / "presupuesto 2025.docx", docs.docx("Presupuesto de la campaña", "de información anual"))
    write(root / "Finance" / "Informe-ventas.pdf", docs.pdf("Quarterly sales report for the board"))
    acl(root / "Finance", read=["finance"])
    write(root / "HR" / "contratos.txt", "Contratos de trabajo del personal")
    acl(root / "HR", read=["hr"], deny=["alice"])
    write(root / "Public" / "notice.txt", "A public notice nobody else may open")
    acl(root / "Public", list=["everyone"], read=["finance"])

    share = Share(name="Dept", path=str(root))
    db.add(share)
    db.commit()
    assert scan_share(db, share).status == "success"
    stats = run_index(db)
    assert stats.pending == 0 and stats.failed == 0
    return root


def names(client, q, **params):
    r = client.get("/search", params={"q": q, **params})
    assert r.status_code == 200, r.text
    return sorted(x["name"] for x in r.json()["results"])


def file_id(db, name):
    return db.scalar(select(File.id).where(File.name == name))


# ── Indexing ──────────────────────────────────────────────────────────────────

def test_every_file_is_indexed_with_its_content(db, library):
    docs_by_name = {d.file.name: d for d in db.scalars(select(Document))}
    assert set(docs_by_name) == {"readme.txt", "presupuesto 2025.docx", "Informe-ventas.pdf", "contratos.txt", "notice.txt"}
    assert docs_by_name["Informe-ventas.pdf"].status == "text"
    assert "campaña" in docs_by_name["presupuesto 2025.docx"].content


def test_changed_file_is_extracted_again(db, library):
    import time
    time.sleep(1.1)  # mtime resolution
    write(library / "readme.txt", "Completely different words now")
    share = db.scalar(select(Share))
    scan_share(db, share)
    assert db.scalar(select(Document.status).join(File).where(File.name == "readme.txt")) == "pending"
    run_index(db)
    db.expire_all()
    assert "different" in db.scalar(select(Document.content).join(File).where(File.name == "readme.txt"))


def test_unsupported_and_oversized_files_are_searchable_by_name(db, library, client, monkeypatch):
    monkeypatch.setattr(settings, "extract_max_size", 10)
    write(library / "plano planta baja.dwg", b"binary cad")
    write(library / "big notes.txt", "x" * 100)
    scan_share(db, db.scalar(select(Share)))
    run_index(db)
    statuses = dict(db.execute(select(File.name, Document.status).join(Document)).all())
    assert statuses["plano planta baja.dwg"] == "metadata" and statuses["big notes.txt"] == "too_large"
    sign_in(client, "carol")
    assert names(client, "planta") == ["plano planta baja.dwg"]


# ── Search and permissions ────────────────────────────────────────────────────

def test_search_shows_each_user_only_what_windows_lets_them_open(client, library):
    sign_in(client, "alice")  # finance + hr, but denied on HR
    assert names(client, "presupuesto") == ["presupuesto 2025.docx"]
    assert names(client, "contratos") == []  # deny beats her hr membership
    assert names(client, "notice") == ["notice.txt"]

    sign_in(client, "bob")  # hr
    assert names(client, "contratos") == ["contratos.txt"]
    assert names(client, "presupuesto") == []

    sign_in(client, "carol")  # no groups: only what everyone can open
    assert names(client, "") == ["readme.txt"]
    # She may list Public ("this folder only") but not open its files (BUG-007).
    assert names(client, "notice") == []


def test_accents_stems_names_and_content(client, library):
    sign_in(client, "alice")
    assert names(client, "informacion") == ["presupuesto 2025.docx"]  # content has "información"
    assert names(client, "CAMPAÑA") == ["presupuesto 2025.docx"]
    assert names(client, "ventas") == ["Informe-ventas.pdf"]  # name only
    assert names(client, "quarterly board") == ["Informe-ventas.pdf"]  # content
    assert names(client, "finance") == ["Informe-ventas.pdf", "presupuesto 2025.docx"]  # folder name
    assert names(client, "presupuesto -campaña") == []


def test_excluded_words_and_phrases(client, db, library):
    sign_in(client, "alice")
    everything = names(client, "")
    assert names(client, "-campaña") == [n for n in everything if n != "presupuesto 2025.docx"]
    assert names(client, 'presupuesto -"informacion anual"') == []
    assert names(client, 'presupuesto -"anual informacion"') == ["presupuesto 2025.docx"]  # not that phrase
    if db.get_bind().dialect.name == "sqlite":
        pytest.skip("stemmed exclusions need PostgreSQL full-text search")
    # The content says "información"; another form of the word must exclude it too.
    # Each query runs as typed, as Spanish and as English stems: an exclusion
    # only one of them notices used to let the document through.
    assert names(client, "presupuesto -informaciones") == []
    assert names(client, "presupuesto -campañas") == []


def test_results_carry_snippet_and_network_path(client, library):
    sign_in(client, "alice")
    [hit] = client.get("/search", params={"q": "informacion"}).json()["results"]
    assert [s["text"] for s in hit["snippet"] if s["hit"]] == ["información"]
    assert hit["path"] == str(library / "Finance" / "presupuesto 2025.docx")


def test_filters(client, library):
    sign_in(client, "alice")
    assert names(client, "", type="pdf") == ["Informe-ventas.pdf"]
    assert names(client, "", type="word") == ["presupuesto 2025.docx"]
    assert names(client, "", type="text") == ["notice.txt", "readme.txt"]
    tomorrow = (datetime.now() + timedelta(days=2)).date().isoformat()
    assert names(client, "", modified_from=tomorrow) == []
    filters = client.get("/search/filters").json()
    assert [s["label"] for s in filters["shares"]] == ["Dept"]


def test_disabled_share_disappears_from_search(client, db, library):
    sign_in(client, "carol")
    db.scalar(select(Share)).enabled = False
    db.commit()
    assert names(client, "") == []


# ── Browse ────────────────────────────────────────────────────────────────────

def test_browse_shows_listable_folders_like_access_based_enumeration(client, library):
    sign_in(client, "carol")
    [share] = client.get("/browse/shares").json()
    root = client.get(f"/browse/folders/{share['root_folder_id']}").json()
    assert [f["name"] for f in root["folders"]] == ["Public"]  # Finance and HR hidden
    assert [f["name"] for f in root["files"]] == ["readme.txt"]

    public = client.get(f"/browse/folders/{root['folders'][0]['id']}").json()
    assert public["files"] == [] and public["files_hidden"] is True
    assert [b["name"] for b in public["breadcrumbs"]] == ["Dept", "Public"]

    sign_in(client, "alice")
    root = client.get(f"/browse/folders/{share['root_folder_id']}").json()
    assert [f["name"] for f in root["folders"]] == ["Finance", "Public"]  # HR: denied


def test_browsing_a_hidden_folder_is_not_found(client, db, library):
    from app.models import Folder

    hr = db.scalar(select(Folder).where(Folder.path == "HR"))
    sign_in(client, "alice")
    assert client.get(f"/browse/folders/{hr.id}").status_code == 404
    assert client.get("/browse/folders/999999").status_code == 404


# ── Documents ─────────────────────────────────────────────────────────────────

def test_document_page_and_download(client, db, library):
    sign_in(client, "alice")
    fid = file_id(db, "presupuesto 2025.docx")
    doc = client.get(f"/documents/{fid}").json()
    assert doc["index_status"] == "text" and "campaña" in doc["text_excerpt"]
    assert doc["path"] == str(library / "Finance" / "presupuesto 2025.docx")

    r = client.get(f"/documents/{fid}/download")
    assert r.status_code == 200 and r.content == (library / "Finance" / "presupuesto 2025.docx").read_bytes()
    assert "filename*=UTF-8''presupuesto%202025.docx" in r.headers["content-disposition"]
    assert r.headers["content-disposition"].startswith("attachment")

    pdf = file_id(db, "Informe-ventas.pdf")
    assert client.get(f"/documents/{pdf}").json()["preview"] == "pdf"
    r = client.get(f"/documents/{pdf}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert client.get(f"/documents/{fid}/preview").status_code == 415  # no inline docx


def test_documents_the_user_cant_open_are_not_found(client, db, library):
    sign_in(client, "bob")
    fid = file_id(db, "presupuesto 2025.docx")
    assert client.get(f"/documents/{fid}").status_code == 404
    assert client.get(f"/documents/{fid}/download").status_code == 404


def test_download_rechecks_the_live_permissions(client, db, library):
    sign_in(client, "alice")
    fid = file_id(db, "presupuesto 2025.docx")
    # Someone removes alice's access after the nightly scan.
    acl(library / "Finance", read=["finance"], deny=["alice"])
    assert client.get(f"/documents/{fid}").status_code == 200  # the index doesn't know yet
    r = client.get(f"/documents/{fid}/download")
    assert r.status_code == 403
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "denied")).file_id == fid


def test_file_that_vanished_since_the_scan(client, db, library):
    sign_in(client, "carol")
    os.remove(library / "readme.txt")
    r = client.get(f"/documents/{file_id(db, 'readme.txt')}/download")
    assert r.status_code in (404, 503)


# ── Audit ─────────────────────────────────────────────────────────────────────

def test_searches_views_and_downloads_are_audited(client, db, library):
    sign_in(client, "alice")
    fid = file_id(db, "presupuesto 2025.docx")
    client.get("/search", params={"q": "=HYPERLINK(1)"})
    client.get("/search", params={"q": "=HYPERLINK(1)", "offset": 20})  # next page: not recorded again
    client.get(f"/documents/{fid}")
    client.get(f"/documents/{fid}/download")
    actions = [e.action for e in db.scalars(select(AuditEvent).order_by(AuditEvent.id))]
    assert actions == ["sign_in", "search", "view", "download"]

    sign_in(client, "admin")
    log = client.get("/admin/reports/audit", params={"username": "alice"}).json()
    assert log["total"] == 4 and log["events"][0]["action"] == "download"
    csv = client.get("/admin/reports/audit", params={"format": "csv", "action": "search"}).text
    assert ";'=HYPERLINK(1);" in csv  # BUG-012: not a formula in Excel


def test_admins_get_no_extra_visibility(client, library):
    sign_in(client, "admin")
    assert names(client, "") == ["readme.txt"]


def test_index_status_and_reindex_job(client, library):
    sign_in(client, "admin")
    status = client.get("/admin/index-status").json()
    assert status["counts"]["text"] == 5 and status["counts"]["not_indexed"] == 0
    r = client.post("/admin/jobs/index", params={"retry": True})
    assert r.status_code == 202 and r.json()["payload"] == {"retry": True}


# ── Sessions and groups ───────────────────────────────────────────────────────

def test_group_changes_reach_existing_sessions(client, db, library, monkeypatch):
    sign_in(client, "carol")
    assert names(client, "contratos") == []
    monkeypatch.setattr(settings, "dev_groups", "carol:hr")
    assert names(client, "contratos") == []  # groups are cached in the session...
    row = db.scalar(select(AuthSession))
    row.groups_resolved_at = datetime.now(timezone.utc) - timedelta(hours=settings.groups_refresh_hours + 1)
    db.commit()
    assert names(client, "contratos") == ["contratos.txt"]  # ...until the refresh


def test_unreachable_ad_keeps_recent_groups_then_ends_the_session(client, db, library, monkeypatch):
    from app.auth.ldap_client import DirectoryUnavailable

    sign_in(client, "alice")
    row = db.scalar(select(AuthSession))
    row.method = "ldap"
    row.groups_resolved_at = datetime.now(timezone.utc) - timedelta(hours=settings.groups_refresh_hours + 1)
    db.commit()

    def unreachable(username):
        raise DirectoryUnavailable("DC down")

    monkeypatch.setattr(sessions, "lookup_user", unreachable)
    sessions._refresh_failed_at.clear()
    assert client.get("/auth/me").status_code == 200  # recent enough: keep working

    sessions._refresh_failed_at.clear()
    db.expire_all()
    row = db.scalar(select(AuthSession))
    row.groups_resolved_at = datetime.now(timezone.utc) - timedelta(
        hours=settings.groups_refresh_hours * sessions.GROUPS_MAX_AGE_FACTOR + 1
    )
    db.commit()
    assert client.get("/auth/me").status_code == 401  # too old to trust: sign in again


def test_account_removed_from_ad_ends_the_session(client, db, library, monkeypatch):
    sign_in(client, "alice")
    row = db.scalar(select(AuthSession))
    row.method = "ldap"
    row.groups_resolved_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    db.commit()
    monkeypatch.setattr(sessions, "lookup_user", lambda username: None)
    assert client.get("/auth/me").status_code == 401
    assert db.scalar(select(AuthSession)) is None
