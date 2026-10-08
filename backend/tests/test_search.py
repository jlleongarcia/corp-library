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
from sqlalchemy import select, update

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


def rescan(db):
    scan_share(db, db.scalar(select(Share)))
    return run_index(db)


class SpyExtractor:
    """Records what the content pass actually reads."""

    def __init__(self, slow: float = 0):
        self.read: list[bytes] = []
        self.slow = slow

    def extract(self, extension, data):
        import time
        from app.services.extract import extract

        self.read.append(data)
        time.sleep(self.slow)
        return extract(extension, data)

    def close(self):
        pass


def test_changed_name_only_file_is_not_read(db, library):
    """BUG-025: an edited .dwg or .zip used to be downloaded and marked "error"."""
    import time
    write(library / "plano.dwg", b"v1")
    write(library / "fotos.zip", b"zip v1")
    rescan(db)
    time.sleep(1.1)  # mtime resolution
    write(library / "plano.dwg", b"v2, edited")
    write(library / "fotos.zip", b"zip v2, edited")
    scan_share(db, db.scalar(select(Share)))
    spy = SpyExtractor()
    stats = run_index(db, extractor=spy)
    statuses = dict(db.execute(select(File.name, Document.status).join(Document)).all())
    assert statuses["plano.dwg"] == statuses["fotos.zip"] == "metadata"
    assert stats.failed == 0 and spy.read == []


def test_file_that_killed_the_worker_is_not_read_again(db, library):
    """BUG-024: a file left `extracting` by a dead worker fails instead of looping."""
    fid = file_id(db, "readme.txt")
    db.execute(update(Document).where(Document.file_id == fid).values(status="extracting"))
    db.commit()
    spy = SpyExtractor()
    stats = run_index(db, extractor=spy)
    doc = db.get(Document, fid)
    db.refresh(doc)
    assert stats.interrupted == 1 and doc.status == "error" and "worker stopped" in doc.error
    assert spy.read == []


def test_extraction_failure_of_one_file_keeps_the_others(db, library, monkeypatch):
    from app.services.extract import ExtractionError

    write(library / "a.txt", "first")
    write(library / "b.txt", "second")
    scan_share(db, db.scalar(select(Share)))

    class Picky(SpyExtractor):
        def extract(self, extension, data):
            if data == b"first":
                raise ExtractionError("the file crashed the text extractor (exit code -11)")
            return super().extract(extension, data)

    run_index(db, extractor=Picky())
    statuses = dict(db.execute(select(File.name, Document.status).join(Document)).all())
    assert statuses["a.txt"] == "error" and statuses["b.txt"] == "text"


def test_index_round_stops_at_its_deadline(db, library):
    """BUG-026: the deadline is checked after every file, not every 20."""
    for i in range(4):
        write(library / f"note{i}.txt", f"note number {i}")
    scan_share(db, db.scalar(select(Share)))
    spy = SpyExtractor(slow=0.3)
    stats = run_index(db, deadline=datetime.now(timezone.utc) + timedelta(seconds=0.1), extractor=spy)
    assert len(spy.read) == 1 and stats.pending == 3


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


def test_file_stricter_than_its_folder_keeps_its_text_to_itself(client, db, library):
    """BUG-023: the folder lets everyone read; the file itself only HR."""
    write(library / "salaries.txt", "Confidential salary review")
    write(library / "minutes.txt", "Board minutes everyone may read")
    acl(library, files={"salaries.txt": {"read": ["hr"]},
                        "minutes.txt": {"deny": ["bob"], "inherit": True}})
    rescan(db)
    salaries = file_id(db, "salaries.txt")

    sign_in(client, "carol")
    assert names(client, "salary") == [] and names(client, "salaries") == []
    assert names(client, "minutes") == ["minutes.txt"]  # inherits "everyone" from the share root
    assert client.get(f"/documents/{salaries}").status_code == 404
    root = db.scalar(select(File.folder_id).where(File.id == salaries))
    listed = [f["name"] for f in client.get(f"/browse/folders/{root}").json()["files"]]
    assert "salaries.txt" not in listed and "minutes.txt" in listed

    sign_in(client, "bob")  # hr
    assert names(client, "salary") == ["salaries.txt"]
    assert "Confidential" in client.get(f"/documents/{salaries}").json()["text_excerpt"]
    assert names(client, "minutes") == []  # his explicit deny comes before the inherited allow


def test_file_shared_in_a_folder_whose_files_are_closed(client, db, library):
    """A file of its own in "this folder only" Public: visible although its neighbours aren't."""
    acl(library / "Public", list=["everyone"], read=["finance"],
        files={"open letter.txt": {"read": ["everyone"]}})
    write(library / "Public" / "open letter.txt", "An open letter")
    rescan(db)
    sign_in(client, "carol")
    assert names(client, "letter") == ["open letter.txt"]
    public = db.scalar(select(File.folder_id).where(File.name == "notice.txt"))
    view = client.get(f"/browse/folders/{public}").json()
    assert [f["name"] for f in view["files"]] == ["open letter.txt"] and view["files_hidden"] is False
    assert [s["label"] for s in client.get("/search/filters").json()["shares"]] == ["Dept"]


def test_count_is_optional_and_capped(client, library, monkeypatch):
    """BUG-027."""
    from app.services import search as search_service

    sign_in(client, "alice")
    r = client.get("/search", params={"q": "", "count": False, "sort": "newest"}).json()
    assert r["total"] is None and len(r["results"]) == 4  # not HR: denied
    monkeypatch.setattr(search_service, "COUNT_CAP", 2)
    r = client.get("/search", params={"q": ""}).json()
    assert r["total"] == 2 and r["total_capped"] is True and len(r["results"]) == 4


def test_name_matches_survive_when_too_many_documents_match(client, db, library, monkeypatch):
    """BUG-027: past COUNT_CAP matches only candidates are ranked; a matching name must stay one."""
    from app.services import search as search_service

    if db.get_bind().dialect.name == "sqlite":
        pytest.skip("ranking needs PostgreSQL full-text search")
    write(library / "contrato marco.txt", "Acuerdo general con el proveedor")
    os.utime(library / "contrato marco.txt", (0, 946684800))  # 2000-01-01: the oldest of all
    for i in range(5):
        write(library / f"nota {i}.txt", f"Este contrato número {i} sigue en revisión")
    rescan(db)
    monkeypatch.setattr(search_service, "COUNT_CAP", 2)
    sign_in(client, "carol")
    r = client.get("/search", params={"q": "contrato"}).json()
    assert r["total"] == 2 and r["total_capped"] is True
    assert r["results"][0]["name"] == "contrato marco.txt"  # by name, though only 2 newest by content


def test_renamed_share_is_found_by_its_new_name(client, db, library):
    """BUG-030: the share's name is part of every path in the index."""
    from app.models import Job

    sign_in(client, "admin")
    share = db.scalar(select(Share))
    assert client.put(f"/admin/shares/{share.id}", json={"name": "Departamento"}).status_code == 200
    job = db.scalar(select(Job).where(Job.kind == "index"))
    assert job.payload == {"rebuild_share": share.id}
    run_index(db, rebuild_share=share.id)
    sign_in(client, "carol")
    assert names(client, "departamento") == ["readme.txt"]
    assert names(client, "dept") == []
    assert names(client, "welcome") == ["readme.txt"]  # the text is still searchable


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


def test_browser_gets_a_page_not_json_when_a_file_cant_be_opened(client, db, library):
    """BUG-028: download and preview are plain links; JSON would replace the app."""
    sign_in(client, "alice")
    fid = file_id(db, "presupuesto 2025.docx")
    acl(library / "Finance", read=["finance"], deny=["alice"])
    tab = {"Sec-Fetch-Dest": "document", "Accept": "text/html"}
    r = client.get(f"/documents/{fid}/download", headers=tab)
    assert r.status_code == 403 and r.headers["content-type"].startswith("text/html")
    assert "You can&#x27;t open this file" in r.text and f'href="/documents/{fid}"' in r.text
    # The app's own requests still get JSON.
    assert client.get(f"/documents/{fid}/download").json()["detail"].startswith("The file server")

    client.post("/auth/logout")
    r = client.get(f"/documents/{fid}/preview", headers={"Sec-Fetch-Dest": "iframe"})
    assert r.status_code == 401 and 'href="/login"' in r.text


def test_download_handle_is_closed_even_if_never_read(library):
    """BUG-032: a browser that disconnects before the first chunk never runs the iterator."""
    from contextlib import contextmanager

    from app.services.library import open_stream
    from app.services.sources import LocalSource

    opened = []

    class Recording(LocalSource):
        @contextmanager
        def open_read(self, relpath):
            with super().open_read(relpath) as fh:
                opened.append(fh)
                yield fh

    chunks, close = open_stream(Recording(str(library)), "readme.txt")
    assert not opened[0].closed
    close()
    assert opened[0].closed
