"""
Phase 2: the folder plan, its guide, the compliance report and its progress.

    share/                       plan: root (only groups folders)
      readme.txt                 -> outside: no files allowed in the root
      Contratos/                 planned: "{YYYY}-{N} *", pdf/docx, other subfolders allowed
        2025-001 Limpieza.pdf
        contrato viejo.pdf       -> misnamed
        2025-002 Notas.txt       -> wrong type
        2024/2024-007 Obras.docx (free: follows Contratos' rules)
      Personal/  read: hr        planned, at most 1 file -> overgrown
        a.txt, b.txt
      Archivo/                   planned, empty
      Varios/                    not in the plan -> outside (2 files)
        x.txt, Sub/y.txt
                                 Actas: planned, not on the share yet
"""

import json
import os
import time
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Folder, Job, PlanSnapshot, Share
from app.services import jobs, plan
from app.services.plan import PlanError, name_matches, normalize_path
from app.services.scanner import scan_share
from app.worker import run_job

from .conftest import sign_in


def write(path, content: str = "x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


@pytest.fixture
def share(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "dev_groups", "alice:finance;bob:hr;carol:")
    root = tmp_path / "share"
    write(root / "readme.txt")
    for name in ("2025-001 Limpieza.pdf", "contrato viejo.pdf", "2025-002 Notas.txt", "2024/2024-007 Obras.docx"):
        write(root / "Contratos" / name)
    write(root / "Personal" / "a.txt")
    write(root / "Personal" / "b.txt")
    write(root / "Personal" / ".corplib-acl.json", json.dumps({"read": ["hr"]}))
    os.makedirs(root / "Archivo")
    write(root / "Varios" / "x.txt")
    write(root / "Varios" / "Sub" / "y.txt")

    s = Share(name="Dept", path=str(root))
    db.add(s)
    db.commit()
    assert scan_share(db, s).status == "success"
    return s


def add(client, share_id, path, **fields):
    r = client.post("/admin/plan", json={"share_id": share_id, "path": path, **fields})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def planned(client, admin, share):
    add(client, share.id, "", allow_files=False, purpose="Department share")
    add(client, share.id, "contratos", purpose="Signed contracts", naming_pattern="{YYYY}-{N} *",
        extensions=[".PDF", "docx"], allow_subfolders=True, keywords=["contract", "contrato"],
        examples=["2025-001 Limpieza.pdf"])
    add(client, share.id, "Personal", purpose="Staff files", max_files=1)
    add(client, share.id, "Archivo", purpose="Closed matters")
    add(client, share.id, "Actas", purpose="Board minutes", keywords=["minutes", "actas"])
    return share


# ── Rules ─────────────────────────────────────────────────────────────────────

def test_naming_patterns():
    assert name_matches("{YYYY}-{MM}-{DD} *", "2025-03-14 Acta consejo.docx")
    assert not name_matches("{YYYY}-{MM}-{DD} *", "2025-13-14 Acta.docx")  # no 13th month
    assert not name_matches("{YYYY}-{MM}-{DD} *", "Acta 2025-03-14.docx")
    # Case and accents don't matter, the extension isn't part of the name.
    assert name_matches("Informe {N}", "INFORMÉ 12.pdf")
    assert name_matches("inf-{yy}_??", "INF-25_ab.xlsx")
    assert not name_matches("inf-{YY}_??", "INF-25_abc.xlsx")
    assert name_matches("a.b *", "a.b c.pdf")  # dots and other characters are literal
    with pytest.raises(PlanError, match="Unknown {DATE}"):
        plan.compile_pattern("{DATE} *")


def test_naming_patterns_with_many_stars_stay_fast():
    # BUG-037: each `*` was a backtracking `.*`; this took 20 s for one file.
    started = time.perf_counter()
    assert not name_matches("* * * * * * x", "a " * 120 + ".pdf")
    assert time.perf_counter() - started < 0.5
    # Each part between stars matches as early as it can, without losing matches.
    assert name_matches("*{N}*{N}", "12.pdf")
    assert name_matches("* - {YYYY} - *", "Obra - 2024 - fase 2 - 2025 - final.pdf")
    assert not name_matches("* - {YYYY}", "Obra - 2024 - fase.pdf")


def test_paths_are_normalized_and_validated():
    assert normalize_path("\\Finance\\\\Budget\\ ") == "Finance/Budget"
    assert normalize_path(" / ") == ""
    for bad in ("Finance/../HR", "a:b", "Budget.", "a?b"):
        with pytest.raises(PlanError):
            normalize_path(bad)


# ── Editor ────────────────────────────────────────────────────────────────────

def test_plan_is_edited_by_admins_and_read_by_everyone(client, share):
    sign_in(client, "carol")
    assert client.get("/admin/plan").status_code == 403
    assert client.post("/admin/plan", json={"share_id": share.id, "path": ""}).status_code == 403
    assert client.get("/plan").json() == []


def test_editor_keeps_the_plan_a_tree(client, admin, share):
    r = client.post("/admin/plan", json={"share_id": share.id, "path": "Contratos"})
    assert r.status_code == 422 and "root" in r.json()["detail"]
    root = add(client, share.id, "")
    assert root["allow_files"] is False and root["exists"] and root["name"] == "Dept"

    r = client.post("/admin/plan", json={"share_id": share.id, "path": "Contratos/2025"})
    assert r.status_code == 422 and "parent" in r.json()["detail"]
    c = add(client, share.id, "Contratos", naming_pattern="{YYYY}-{N} *", examples=["2025-1 a.pdf", "malo.pdf"])
    assert c["allow_files"] and not c["allow_subfolders"] and c["exists"]
    assert c["example_problems"] == ["'malo.pdf' doesn't follow the naming pattern"]
    # Windows ignores case: CONTRATOS is the same folder.
    assert client.post("/admin/plan", json={"share_id": share.id, "path": "CONTRATOS"}).status_code == 409
    r = client.post("/admin/plan", json={"share_id": share.id, "path": "X", "naming_pattern": "{FECHA}"})
    assert r.status_code == 422 and "Unknown {FECHA}" in r.json()["detail"]

    sub = add(client, share.id, "Contratos/2025")
    assert not sub["exists"]
    add(client, share.id, "Legal")
    # Moving an entry moves what is planned below it.
    r = client.put(f"/admin/plan/{c['id']}", json={"path": "Legal/Contracts", "owner": " Ana "})
    assert r.status_code == 200, r.text
    assert r.json()["owner"] == "Ana" and r.json()["updated_by"] == "admin"
    paths = sorted(e["path"] for e in client.get("/admin/plan", params={"share_id": share.id}).json())
    assert paths == ["", "Legal", "Legal/Contracts", "Legal/Contracts/2025"]
    r = client.put(f"/admin/plan/{c['id']}", json={"path": "Legal/Contracts/2025/x"})
    assert r.status_code == 422 and "inside itself" in r.json()["detail"]
    assert client.put(f"/admin/plan/{root['id']}", json={"path": "Root"}).status_code == 422

    # Deleting an entry deletes what is planned below it.
    assert client.delete(f"/admin/plan/{c['id']}").json() == {"deleted": 2}
    assert client.delete(f"/admin/plan/{root['id']}").json() == {"deleted": 2}
    assert client.get("/admin/plan").json() == []


def test_plan_lists_each_folder_before_its_subfolders(client, admin, share):
    # BUG-035: sorted by path, "Contratos 2024" came between "Contratos" and "Contratos/2024"
    # (" " < "/"), so the editor and the guide drew 2024 under the wrong folder.
    for path in ("", "Contratos", "Contratos 2024", "Contratos-B", "Contratos/2024", "Contratos/2024/Obras"):
        add(client, share.id, path)
    order = ["", "Contratos", "Contratos/2024", "Contratos/2024/Obras", "Contratos 2024", "Contratos-B"]
    assert [e["path"] for e in client.get("/admin/plan").json()] == order
    assert [e["path"] for e in client.get("/plan").json()[0]["entries"]] == order


def test_plan_can_start_from_the_existing_folders(client, admin, share):
    r = client.post("/admin/plan/import", json={"share_id": share.id, "depth": 1})
    assert r.status_code == 201 and r.json() == {"added": 5}
    entries = {e["path"]: e for e in client.get("/admin/plan").json()}
    assert set(entries) == {"", "Archivo", "Contratos", "Personal", "Varios"}
    # The deepest imported level allows the subfolders below it, which weren't imported.
    assert entries["Contratos"]["allow_subfolders"] and not entries[""]["allow_subfolders"]
    assert client.post("/admin/plan/import", json={"share_id": share.id, "depth": 1}).json() == {"added": 0}
    # Nothing is outside a plan made from what is there (except the root's own file).
    report = client.get("/admin/reports/compliance", params={"share_id": share.id}).json()
    assert report["totals"]["files_in_plan"] == report["totals"]["files_total"] - 1


# ── Compliance ────────────────────────────────────────────────────────────────

def test_compliance_report(client, planned):
    r = client.get("/admin/reports/compliance", params={"share_id": planned.id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totals"] == {
        "files_total": 9, "files_in_plan": 6, "files_checked": 4, "files_misnamed": 1, "files_wrong_type": 1,
        "folders_planned": 5, "folders_missing": 1, "folders_empty": 1, "folders_overgrown": 1,
    }

    def tail(path):
        return path.replace(str(planned.path), "").lstrip("\\/").replace("\\", "/")

    outside = [(tail(i["path"]), i["files"], i["reason"]) for i in data["outside"]["items"]]
    assert outside == [("Varios", 2, "not_in_plan"), ("", 1, "no_files_here")]  # Varios/Sub: under Varios
    assert [tail(i["path"]) for i in data["misnamed"]["items"]] == ["Contratos/contrato viejo.pdf"]
    wrong = data["wrong_type"]["items"][0]
    assert tail(wrong["path"]) == "Contratos/2025-002 Notas.txt" and wrong["allowed"] == ["pdf", "docx"]
    assert [tail(i["path"]) for i in data["missing"]["items"]] == ["Actas"]
    assert [tail(i["path"]) for i in data["empty"]["items"]] == ["Archivo"]
    assert [(tail(i["path"]), i["files"], i["limit"]) for i in data["overgrown"]["items"]] == [("Personal", 2, 1)]

    csv = client.get("/admin/reports/compliance", params={"share_id": planned.id, "format": "csv"})
    assert csv.status_code == 200 and "contrato viejo.pdf" in csv.text and "planned folder missing" in csv.text
    plan_csv = client.get("/admin/reports/plan")
    assert "Signed contracts" in plan_csv.text and "not yet" in plan_csv.text

    assert client.get("/admin/reports/compliance", params={"share_id": 999}).status_code == 404


def test_lists_are_capped_but_totals_count_everything(db, planned):
    data = plan.evaluate(db, db.get(Share, planned.id), limit=1)
    assert data["outside"]["count"] == 2 and len(data["outside"]["items"]) == 1
    assert data["totals"]["files_in_plan"] == 6


def test_lists_keep_the_biggest_problems_and_the_csv_keeps_them_all(client, db, planned):
    # BUG-036: the first `limit` items found were kept (in database order), not the biggest.
    data = plan.evaluate(db, db.get(Share, planned.id), limit=1)
    assert [(i["reason"], i["files"]) for i in data["outside"]["items"]] == [("not_in_plan", 2)]
    # The CSV lists everything, whatever the limit (the UI says "export for all").
    csv = client.get("/admin/reports/compliance", params={"share_id": planned.id, "limit": 1, "format": "csv"})
    assert "outside the plan" in csv.text and "files not allowed here" in csv.text


def test_unlisted_folders_are_not_reported_empty_or_missing(client, db, planned):
    # BUG-038: what's in a folder the scanner couldn't list is unknown.
    add(client, planned.id, "Archivo/2020")
    totals = client.get("/admin/reports/compliance", params={"share_id": planned.id}).json()["totals"]
    assert (totals["folders_empty"], totals["folders_missing"]) == (1, 2)  # Archivo; Actas, Archivo/2020
    archivo = db.scalar(select(Folder).where(Folder.share_id == planned.id, Folder.path == "Archivo"))
    archivo.list_error = "Access denied"
    db.commit()
    data = client.get("/admin/reports/compliance", params={"share_id": planned.id}).json()
    assert (data["totals"]["folders_empty"], data["totals"]["folders_missing"]) == (0, 1)
    assert data["missing"]["items"][0]["path"].endswith("Actas")


def test_correctly_named_counts_only_files_under_a_naming_pattern(client, db, planned):
    # BUG-039: files under a file-type rule only counted as "checked", inflating "correctly named".
    client.put(f"/admin/plan/{_entry_id(client, 'Personal')}", json={"extensions": ["txt"]})
    totals = plan.evaluate(db, db.get(Share, planned.id))["totals"]
    assert (totals["files_checked"], totals["files_misnamed"]) == (4, 1)  # Contratos and its 2024 folder


def test_csv_download_name_may_hold_any_character(client, db, planned):
    # BUG-040: the share's name went into a Latin-1 header: "€" was a 500.
    share = db.get(Share, planned.id)
    share.name = 'Gestión "€"'
    db.commit()
    r = client.get("/admin/reports/compliance", params={"share_id": planned.id, "format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (
        'attachment; filename="compliance-Gesti_n ___.csv"; '
        "filename*=UTF-8''compliance-Gesti%C3%B3n%20%22%E2%82%AC%22.csv"
    )


def test_share_without_a_plan_has_no_report(client, admin, share):
    assert client.get("/admin/reports/compliance", params={"share_id": share.id}).status_code == 404


# ── Progress over time ────────────────────────────────────────────────────────

def test_progress_keeps_one_snapshot_per_share_and_day(client, db, planned):
    today = date.today()
    assert plan.take_snapshots(db, today - timedelta(days=1)) == 1
    assert plan.take_snapshots(db, today) == 1
    # Moving the stray files into the plan improves today's figures; today's row is replaced.
    client.put(f"/admin/plan/{_entry_id(client, '')}", json={"allow_files": True})
    db.expire_all()
    assert plan.take_snapshots(db, today) == 1
    assert db.scalar(select(func.count()).select_from(PlanSnapshot)) == 2

    progress = client.get("/admin/reports/compliance/progress").json()
    assert len(progress) == 1 and progress[0]["share"] == "Dept"
    assert [s["files_in_plan"] for s in progress[0]["snapshots"]] == [6, 7]
    csv = client.get("/admin/reports/compliance/progress", params={"format": "csv"})
    assert csv.status_code == 200 and "files_in_plan" in csv.text


def test_snapshot_follows_every_scan_batch_and_can_be_requested(client, db, planned):
    job = jobs.enqueue(db, jobs.SCAN, {"share_id": planned.id})
    run_job(db, jobs.claim_next(db))
    jobs.finish(db, job)
    assert jobs.COMPLIANCE in set(db.scalars(select(Job.kind).where(Job.status == "queued")))

    r = client.post("/admin/jobs/compliance")
    assert r.status_code == 202 and r.json()["kind"] == "compliance"
    run_job(db, db.get(Job, r.json()["id"]))
    assert db.scalar(select(PlanSnapshot.files_total)) == 9


def test_follow_up_jobs_are_queued_even_if_the_last_scan_fails(db, planned, tmp_path):
    # BUG-042: an unreachable share scanned last meant no snapshot (nor index, dedupe) that night.
    gone = Share(name="Gone", path=str(tmp_path / "not-there"))
    db.add(gone)
    db.commit()
    jobs.enqueue(db, jobs.SCAN, {"share_id": gone.id})
    with pytest.raises(RuntimeError):
        run_job(db, jobs.claim_next(db))
    queued = set(db.scalars(select(Job.kind).where(Job.status == "queued")))
    assert {jobs.COMPLIANCE, jobs.INDEX, jobs.DEDUPE, jobs.RESOLVE} <= queued


def _entry_id(client, path):
    return next(e["id"] for e in client.get("/admin/plan").json() if e["path"] == path)


# ── Folder guide and browse ───────────────────────────────────────────────────

def test_guide_shows_each_user_only_folders_windows_lets_them_see(client, planned):
    def guide_for(user):
        sign_in(client, user)
        shares = client.get("/plan").json()
        return {e["path"]: e for s in shares for e in s["entries"]}

    carol = guide_for("carol")
    # Personal is closed to her; Actas doesn't exist yet and is shown under the root she can list.
    assert set(carol) == {"", "contratos", "Archivo", "Actas"}
    assert carol["contratos"]["folder_id"] is not None and carol["Actas"]["folder_id"] is None
    assert carol["contratos"]["keywords"] == ["contract", "contrato"]
    assert "max_files" not in carol["contratos"]  # admin-only details stay out of the guide
    assert "Personal" in guide_for("bob")


def test_browse_shows_where_a_folder_stands_in_the_plan(client, db, planned):
    sign_in(client, "bob")

    def placement(path):
        folder_id = db.scalar(select(Folder.id).where(Folder.share_id == planned.id, Folder.path == path))
        return client.get(f"/browse/folders/{folder_id}").json()["plan"]

    p = placement("Contratos")
    assert p["status"] == "planned" and p["entry"]["purpose"] == "Signed contracts"
    p = placement("Contratos/2024")
    assert p["status"] == "free" and p["entry"]["path"] == "contratos" and p["entry"]["folder_id"] is None
    p = placement("Varios/Sub")
    assert p["status"] == "outside" and p["entry"]["path"] == ""

    sign_in(client, "admin")
    client.delete(f"/admin/plan/{_entry_id(client, '')}")
    sign_in(client, "bob")
    assert placement("Contratos") is None


def test_browse_hides_the_guide_of_a_folder_above_that_the_user_cannot_list(client, db, planned):
    # BUG-041: under a folder closed to them, users saw its guide (purpose, owner...) while browsing.
    root = db.get(Share, planned.id).path
    write(os.path.join(root, "Personal", "Abierto", ".corplib-acl.json"), json.dumps({"read": ["everyone"]}))
    write(os.path.join(root, "Personal", "Abierto", "horario.txt"))
    assert scan_share(db, db.get(Share, planned.id)).status == "success"
    folder_id = db.scalar(select(Folder.id).where(Folder.share_id == planned.id, Folder.path == "Personal/Abierto"))

    sign_in(client, "carol")  # may open Abierto, not Personal
    assert client.get(f"/browse/folders/{folder_id}").json()["plan"] == {"status": "outside", "entry": None}
    sign_in(client, "bob")
    assert client.get(f"/browse/folders/{folder_id}").json()["plan"]["entry"]["purpose"] == "Staff files"
