import os
import shutil
import time

import pytest
from sqlalchemy import func, select

from app.acl.descriptor import FILE_GENERIC_READ, INHERITED_ACE, Ace, build_security_descriptor
from app.models import Acl, File, Folder, Share
from app.services.dedupe import run_dedupe
from app.services.scanner import scan_share
from app.services.sources import DirEntry, LocalSource

FINANCE = "S-1-5-21-1000-2000-3000-2201"
HR = "S-1-5-21-1000-2000-3000-2202"

ROOT_SD = build_security_descriptor([Ace(FINANCE, "allow", FILE_GENERIC_READ, 0x3)], protected=True)
INHERITED_SD = build_security_descriptor([Ace(FINANCE, "allow", FILE_GENERIC_READ, 0x3 | INHERITED_ACE)])
HR_SD = build_security_descriptor([Ace(HR, "allow", FILE_GENERIC_READ, 0x3)], protected=True)


def sd_provider(relpath: str):
    if relpath == "":
        return ROOT_SD
    if relpath.startswith("HR"):
        return HR_SD
    return INHERITED_SD


def write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "share"
    write(root / "Budget" / "2025.xlsx", b"budget-2025")
    write(root / "Budget" / "copy of 2025.xlsx", b"budget-2025")
    write(root / "Budget" / "Old" / "2019.xlsx", b"old")
    write(root / "HR" / "contracts.pdf", b"contract")
    write(root / "readme.txt", b"hello")
    write(root / "~$lock.docx", b"lock")  # Office lock file: ignored
    write(root / "Thumbs.db", b"thumbs")  # ignored
    return root


@pytest.fixture
def share(db, tree):
    s = Share(name="Finance", path=str(tree))
    db.add(s)
    db.commit()
    return s


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_first_scan_indexes_tree_and_acls(db, share, tree):
    run = scan_share(db, share, LocalSource(str(tree), sd_provider))
    assert run.status == "success"
    assert run.files_added == 5 and run.files_seen == 5
    assert count(db, Folder) == 4  # root, Budget, Budget/Old, HR
    assert count(db, File) == 5

    # Three distinct ACLs (root, inherited, HR) shared by four folders.
    assert count(db, Acl) == 3
    old = db.scalar(select(Folder).where(Folder.path == "Budget/Old"))
    assert old.depth == 2 and old.acl.entries[0].sid == FINANCE
    hr = db.scalar(select(Folder).where(Folder.path == "HR"))
    assert hr.acl.is_protected and hr.acl.has_explicit


def test_rescan_detects_changes(db, share, tree):
    src = LocalSource(str(tree), sd_provider)
    scan_share(db, share, src)
    f = db.scalar(select(File).where(File.name == "2025.xlsx"))
    f.quick_hash = "stale"
    db.commit()

    time.sleep(1.1)  # mtime resolution
    write(tree / "Budget" / "2025.xlsx", b"budget-2025-v2")
    write(tree / "new.docx", b"new")
    os.remove(tree / "readme.txt")
    shutil.rmtree(tree / "Budget" / "Old")

    run = scan_share(db, share, src)
    assert (run.files_added, run.files_updated, run.files_removed) == (1, 1, 2)
    db.expire_all()
    f = db.scalar(select(File).where(File.name == "2025.xlsx"))
    assert f.size == len(b"budget-2025-v2") and f.quick_hash is None
    assert db.scalar(select(Folder).where(Folder.path == "Budget/Old")) is None
    assert count(db, File) == 4


def test_unchanged_rescan_touches_nothing(db, share, tree):
    src = LocalSource(str(tree), sd_provider)
    scan_share(db, share, src)
    run = scan_share(db, share, src)
    assert (run.files_added, run.files_updated, run.files_removed) == (0, 0, 0)


class FlakySource(LocalSource):
    """Fails to list one folder, as a transient SMB error would."""

    def __init__(self, root, fail_path):
        super().__init__(root, sd_provider)
        self.fail_path = fail_path

    def list_dir(self, relpath):
        if relpath == self.fail_path:
            raise OSError("STATUS_NETWORK_NAME_DELETED")
        return super().list_dir(relpath)


def test_list_error_keeps_previous_contents(db, share, tree):
    scan_share(db, share, LocalSource(str(tree), sd_provider))
    run = scan_share(db, share, FlakySource(str(tree), "Budget"))
    assert run.status == "partial" and run.error_count == 1
    assert "STATUS_NETWORK_NAME_DELETED" in run.error_sample
    assert db.scalar(select(func.count()).select_from(File).join(Folder).where(Folder.path == "Budget")) == 2
    assert db.scalar(select(Folder).where(Folder.path == "Budget/Old")) is not None


def test_missing_acl_is_recorded_not_fatal(db, share, tree):
    def broken(relpath):
        if relpath == "HR":
            raise PermissionError("ACCESS_DENIED")
        return sd_provider(relpath)

    run = scan_share(db, share, LocalSource(str(tree), broken))
    assert run.status == "partial"
    hr = db.scalar(select(Folder).where(Folder.path == "HR"))
    assert hr.acl_id is None and "ACCESS_DENIED" in hr.acl_error
    assert db.scalar(select(func.count()).select_from(File).where(File.folder_id == hr.id)) == 1


def test_dedupe_finds_exact_duplicates(db, share, tree):
    src = LocalSource(str(tree), sd_provider)
    scan_share(db, share, src)
    stats = run_dedupe(db, {share.id: src})
    assert stats.errors == 0 and stats.full_hashed == 2
    a, b = db.scalars(select(File).where(File.name.like("%2025.xlsx"))).all()
    assert a.content_hash and a.content_hash == b.content_hash
    # Second run has nothing new to hash.
    again = run_dedupe(db, {share.id: src})
    assert again.quick_hashed == again.full_hashed == 0


class ReparseSource(LocalSource):
    """Adds a junction (folder reparse point) and a deduplicated file (file reparse point) to the root."""

    def list_dir(self, relpath):
        entries = super().list_dir(relpath)
        if relpath == "":
            entries += [
                DirEntry("Link to elsewhere", is_dir=True, size=0, mtime=None, ctime=None, is_reparse_point=True),
                DirEntry("deduped.pdf", is_dir=False, size=4096, mtime=None, ctime=None, is_reparse_point=True),
            ]
        return entries


def test_reparse_folders_skipped_but_reparse_files_indexed(db, share, tree):
    run = scan_share(db, share, ReparseSource(str(tree), sd_provider))
    assert run.status == "success" and run.folders_skipped == 1
    assert db.scalar(select(File).where(File.name == "deduped.pdf")) is not None
    assert db.scalar(select(Folder).where(Folder.name == "Link to elsewhere")) is None


def test_unreachable_share_fails_the_run(db, share, tree):
    scan_share(db, share, LocalSource(str(tree), sd_provider))
    run = scan_share(db, share, FlakySource(str(tree), ""))
    assert run.status == "failed"
    assert count(db, File) == 5  # nothing wiped
    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    assert "STATUS_NETWORK_NAME_DELETED" in root.list_error


def test_list_error_cleared_once_folder_lists_again(db, share, tree):
    src = LocalSource(str(tree), sd_provider)
    scan_share(db, share, FlakySource(str(tree), "Budget"))
    budget = db.scalar(select(Folder).where(Folder.path == "Budget"))
    assert budget.list_error
    scan_share(db, share, src)
    db.refresh(budget)
    assert budget.list_error is None


def test_local_symlinked_folder_is_not_indexed_as_a_file(db, share, tree, tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    try:
        os.symlink(target, tree / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks needs extra rights on this OS")
    run = scan_share(db, share, LocalSource(str(tree), sd_provider))
    assert run.folders_skipped == 1
    assert db.scalar(select(File).where(File.name == "link")) is None
