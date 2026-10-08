"""
The folder plan: the agreed structure of each share, and how far the shares follow it.

A plan is a tree of `PlanFolder` entries per share, starting at the share's root.
Each entry says what the folder is for, what belongs there, and how files there
are named. Entries are matched to the scanned folders by path, ignoring case as
Windows does, so a planned folder can exist before or after the real one.

Where a scanned folder stands:

- planned:  it is in the plan.
- free:     it isn't, but its nearest planned ancestor allows subfolders of its
            own (one per project, per year...). It follows that entry's rules.
- outside:  neither. Its files are "outside the plan".

Files saved directly in a planned folder that doesn't take files (one that only
groups others, like a share root) are outside the plan too.

Naming patterns are checked against the file name without its extension,
ignoring case and accents. `*` is any text, `?` one character, and
{YYYY} {YY} {MM} {DD} {N} are a year, a two-digit year, a month, a day and a
number: "{YYYY}-{MM}-{DD} *" accepts "2025-03-14 Acta consejo".
"""

import heapq
import posixpath
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import File, Folder, PlanFolder, PlanSnapshot, Share
from .access import listable_folder_acl_ids
from .reports import display_path
from .text import fold

# A folder with more files than this, directly in it, is "overgrown" unless its
# plan entry says otherwise.
DEFAULT_MAX_FILES = 500
HISTORY_DAYS = 400
_CHUNK = 500  # folder ids per IN (...) when reading file names

PATTERN_TOKENS = {
    "YYYY": r"(?:19|20)\d\d",
    "YY": r"\d\d",
    "MM": r"(?:0[1-9]|1[0-2])",
    "DD": r"(?:0[1-9]|[12]\d|3[01])",
    "N": r"\d+?",  # lazy, so a part between stars ends as early as it can (compile_pattern)
}
_PATTERN_PART = re.compile(r"\{([^{}]*)\}|.", re.DOTALL)
# Not allowed in Windows file and folder names.
_INVALID_NAME_CHARS = set('<>:"|?*')

TEXT_FIELDS = ("purpose", "belongs", "not_belongs", "owner", "naming")
LIST_FIELDS = ("examples", "extensions", "keywords")


class PlanError(ValueError):
    """The request can't be applied as it is (shown to the admin)."""


class PlanConflict(PlanError):
    """Another entry already has that path."""


# ── Paths and names ───────────────────────────────────────────────────────────

def normalize_path(raw: str) -> str:
    """A share-relative path as typed ("\\Finance\\Budget\\", "finance/budget") -> "Finance/Budget"."""
    parts = [p.strip() for p in raw.replace("\\", "/").split("/")]
    parts = [p for p in parts if p]
    for p in parts:
        if p in (".", ".."):
            raise PlanError("A folder can't be called '.' or '..'")
        bad = sorted({c for c in p if c in _INVALID_NAME_CHARS or ord(c) < 32})
        if bad:
            raise PlanError(f"Windows doesn't allow {' '.join(bad)} in folder names ({p})")
        if p.endswith("."):
            raise PlanError(f"Windows doesn't allow folder names ending in a dot ({p})")
        if len(p) > 255:
            raise PlanError("Folder names are limited to 255 characters")
    return "/".join(parts)


def path_key(path: str) -> str:
    return path.lower()


def _parent(path: str) -> Optional[str]:
    return None if path == "" else posixpath.dirname(path)


def _split(name: str) -> tuple[str, str]:
    # The scanner's split: "a.b.PDF" -> ("a.b", "pdf"); ".profile" has no extension.
    head, dot, ext = name.rpartition(".")
    return (head, ext.lower()) if dot and head else (name, "")


def _stem(name: str) -> str:
    return _split(name)[0]


@lru_cache(maxsize=512)
def compile_pattern(pattern: str) -> re.Pattern:
    # The parts between stars. Translating each `*` to `.*` backtracks
    # exponentially: "* * * * * x" took 20 s on one long name (BUG-037).
    chunks: list[list[str]] = [[]]
    for m in _PATTERN_PART.finditer(pattern.strip()):
        token, char = m.group(1), m.group(0)
        if token is not None:
            regex = PATTERN_TOKENS.get(token.strip().upper())
            if regex is None:
                known = " ".join("{" + t + "}" for t in PATTERN_TOKENS)
                raise PlanError(f"Unknown {char} in the naming pattern; use {known}, * or ?")
            chunks[-1].append(regex)
        elif char == "*":
            chunks.append([])
        elif char == "?":
            chunks[-1].append(".")
        else:
            chunks[-1].append(re.escape(fold(char)))
    first, *middle, last = ["".join(c) for c in chunks] if len(chunks) > 1 else ["".join(chunks[0]), None]
    # Each middle part takes its earliest match and never gives it back (an
    # atomic group): the classic glob algorithm, linear instead of exponential.
    # Matching it as early as possible leaves the most room for what follows.
    out = first + "".join(f"(?>.*?{c})" for c in middle if c)
    if last is not None:
        out += ".*" + last
    return re.compile(out, re.DOTALL)


def name_matches(pattern: str, filename: str) -> bool:
    return compile_pattern(pattern).fullmatch(fold(_stem(filename))) is not None


def _clean_list(values: list[str], kind: str) -> list[str]:
    out, seen = [], set()
    for v in values:
        v = v.strip()
        if kind == "extensions":
            v = v.lstrip(".").lower()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


# ── Editing ───────────────────────────────────────────────────────────────────

def tree_order(key: str) -> list[str]:
    # By path parts, so each folder comes right before its subfolders. Sorting
    # the plain path puts "a b" between "a" and "a/x" (" " < "/"), and
    # PostgreSQL's collation ignores the "/" altogether (BUG-035).
    return key.split("/")


def entries(db: Session, share_id: Optional[int] = None) -> list[PlanFolder]:
    """A share's plan (or every share's), as a tree: each entry before the ones below it."""
    stmt = select(PlanFolder)
    if share_id is not None:
        stmt = stmt.where(PlanFolder.share_id == share_id)
    return sorted(db.scalars(stmt), key=lambda e: (e.share_id, tree_order(e.path_key)))


def _by_key(db: Session, share_id: int) -> dict[str, PlanFolder]:
    return {e.path_key: e for e in entries(db, share_id)}


def _apply(entry: PlanFolder, fields: dict[str, Any]) -> None:
    for name in TEXT_FIELDS:
        if name in fields:
            setattr(entry, name, (fields[name] or "").strip())
    for name in LIST_FIELDS:
        if name in fields:
            setattr(entry, name, _clean_list(fields[name] or [], name))
    if "naming_pattern" in fields:
        pattern = (fields["naming_pattern"] or "").strip() or None
        if pattern:
            compile_pattern(pattern)  # raises PlanError if it's not valid
        entry.naming_pattern = pattern
    for name in ("allow_files", "allow_subfolders"):
        if fields.get(name) is not None:
            setattr(entry, name, bool(fields[name]))
    if "max_files" in fields:
        entry.max_files = fields["max_files"]


def create_entry(db: Session, share: Share, path: str, fields: dict[str, Any], username: str) -> PlanFolder:
    path = normalize_path(path)
    plan = _by_key(db, share.id)
    if path_key(path) in plan:
        raise PlanConflict("That folder is already in the plan")
    parent = _parent(path)
    if parent is not None and path_key(parent) not in plan:
        raise PlanError("Add its parent folder to the plan first" if plan else "Start the plan with the share's root")
    entry = PlanFolder(share_id=share.id, path=path, path_key=path_key(path), updated_by=username,
                       allow_files=parent is not None)  # a share's root usually only groups folders
    _apply(entry, fields)
    db.add(entry)
    db.commit()
    return entry


def update_entry(db: Session, entry: PlanFolder, fields: dict[str, Any], username: str) -> PlanFolder:
    """Change an entry. A new path moves (or renames) it with everything planned below it."""
    new_path = normalize_path(fields["path"]) if fields.get("path") is not None else entry.path
    old_key, new_key = entry.path_key, path_key(new_path)
    now = datetime.now(timezone.utc)
    if new_path != entry.path:
        if entry.path == "":
            raise PlanError("The share's root can't be moved")
        if new_path == "":
            raise PlanError("Another entry can't become the share's root")
        plan = _by_key(db, entry.share_id)
        if new_key != old_key and new_key in plan:
            raise PlanConflict("That folder is already in the plan")
        if new_key.startswith(old_key + "/"):
            raise PlanError("A folder can't be moved inside itself")
        if path_key(_parent(new_path)) not in plan:
            raise PlanError("Add the new parent folder to the plan first")
        for other in plan.values():
            if other.path_key.startswith(old_key + "/"):
                other.path = new_path + other.path[len(entry.path):]
                other.path_key = path_key(other.path)
                other.updated_at, other.updated_by = now, username
        entry.path, entry.path_key = new_path, new_key
    _apply(entry, fields)
    entry.updated_at, entry.updated_by = now, username
    db.commit()
    return entry


def delete_entry(db: Session, entry: PlanFolder) -> int:
    """Removes the entry and everything planned below it. Returns how many entries went."""
    doomed = [e for e in entries(db, entry.share_id)
              if entry.path == "" or e.path_key == entry.path_key or e.path_key.startswith(entry.path_key + "/")]
    for e in doomed:
        db.delete(e)
    db.commit()
    return len(doomed)


def import_folders(db: Session, share: Share, depth: int, username: str) -> int:
    """
    Start (or extend) a plan from the folders on the share, down to `depth`
    levels. The deepest level allows subfolders, so what is below it isn't
    reported as outside the plan. Entries already in the plan are left alone.
    """
    plan = _by_key(db, share.id)
    added = 0
    if "" not in plan:
        plan[""] = create_entry(db, share, "", {}, username)
        added += 1
    for path, folder_depth in db.execute(
        select(Folder.path, Folder.depth)
        .where(Folder.share_id == share.id, Folder.depth >= 1, Folder.depth <= depth)
        .order_by(Folder.depth, Folder.path)
    ):
        key = path_key(path)
        if key in plan or path_key(_parent(path)) not in plan:
            continue
        entry = PlanFolder(share_id=share.id, path=path, path_key=key, updated_by=username,
                           allow_subfolders=folder_depth == depth)
        db.add(entry)
        plan[key] = entry
        added += 1
    db.commit()
    return added


def example_problems(entry: PlanFolder) -> list[str]:
    """Examples that its own naming pattern or file types would reject: the rule is probably wrong."""
    problems = []
    for name in entry.examples:
        ext = _split(name)[1]
        if entry.naming_pattern and not name_matches(entry.naming_pattern, name):
            problems.append(f"'{name}' doesn't follow the naming pattern")
        elif entry.extensions and ext not in entry.extensions:
            problems.append(f"'{name}' isn't one of the file types")
    return problems


# ── Where a folder stands ─────────────────────────────────────────────────────

Status = Literal["planned", "free", "outside"]


@dataclass
class Placement:
    status: Status
    # planned: the folder's entry; free: the entry whose rules it follows;
    # outside: the nearest planned ancestor (where its files could go), if any.
    entry: Optional[PlanFolder]


def place(plan: dict[str, PlanFolder], folder_path: str) -> Placement:
    key = path_key(folder_path)
    if key in plan:
        return Placement("planned", plan[key])
    while key:
        key = posixpath.dirname(key)
        if key in plan:
            ancestor = plan[key]
            return Placement("free" if ancestor.allow_subfolders else "outside", ancestor)
    return Placement("outside", None)


def placement_for_folder(db: Session, share_id: int, folder_path: str) -> Optional[Placement]:
    """For the browse page. None when the share has no plan."""
    plan = _by_key(db, share_id)
    return place(plan, folder_path) if plan else None


def _folders_up_to(db: Session, share_id: int, depth: int) -> dict[str, tuple[int, Optional[int]]]:
    """Scanned folders (id, ACL id) by path key, down to `depth` levels."""
    return {
        path_key(p): (fid, acl) for fid, p, acl in db.execute(
            select(Folder.id, Folder.path, Folder.acl_id).where(Folder.share_id == share_id, Folder.depth <= depth)
        )
    }


def depth(path: str) -> int:
    """Folders below the share's root: "" is 0, "a/b" is 2."""
    return path.count("/") + 1 if path else 0


def admin_view(db: Session, share_id: Optional[int] = None) -> list[dict]:
    """Every entry, with whether its folder exists yet: the editor's data."""
    out = []
    plan = entries(db, share_id)
    shares = {s.id: s for s in db.scalars(select(Share))}
    folders_by_share: dict[int, dict] = {}
    for e in plan:
        if e.share_id not in folders_by_share:
            deepest = max(depth(x.path) for x in plan if x.share_id == e.share_id)
            folders_by_share[e.share_id] = _folders_up_to(db, e.share_id, deepest)
        folder = folders_by_share[e.share_id].get(e.path_key)
        out.append(entry_dict(e, shares[e.share_id], folder_id=folder[0] if folder else None,
                              exists=folder is not None, problems=example_problems(e), admin=True))
    return out


def entry_dict(e: PlanFolder, share: Share, folder_id: Optional[int] = None, exists: Optional[bool] = None,
               problems: Optional[list[str]] = None, admin: bool = False) -> dict:
    d = {
        "id": e.id, "share_id": e.share_id, "share": share.name, "path": e.path,
        "name": posixpath.basename(e.path) or share.name, "depth": depth(e.path),
        "network_path": display_path(share.path, e.path),
        "purpose": e.purpose, "belongs": e.belongs, "not_belongs": e.not_belongs, "owner": e.owner,
        "naming": e.naming, "naming_pattern": e.naming_pattern, "examples": e.examples,
        "extensions": e.extensions, "keywords": e.keywords, "allow_files": e.allow_files,
        "allow_subfolders": e.allow_subfolders, "folder_id": folder_id,
    }
    if admin:
        d.update(max_files=e.max_files, exists=exists, example_problems=problems or [],
                 updated_at=e.updated_at, updated_by=e.updated_by)
    return d


# ── The folder guide (everyone) ───────────────────────────────────────────────

def guide(db: Session, token: frozenset[str]) -> list[dict]:
    """
    The plan as each user may see it: an entry is shown if they can list its
    folder in Explorer, or, for a folder that doesn't exist yet, the nearest one
    above it that does. So the guide never names a folder that Windows hides
    from them, as browsing doesn't.
    """
    listable = set(listable_folder_acl_ids(db, token))
    out = []
    plan = entries(db)
    for share in db.scalars(select(Share).where(Share.enabled).order_by(Share.name)):
        mine = [e for e in plan if e.share_id == share.id]
        if not mine:
            continue
        folders = _folders_up_to(db, share.id, max(depth(e.path) for e in mine))
        visible = []
        for e in mine:
            key = e.path_key
            folder = folders.get(key)
            while folder is None and key:
                key = posixpath.dirname(key)
                folder = folders.get(key)
            if folder is None or folder[1] not in listable:
                continue
            visible.append(entry_dict(e, share, folder_id=folder[0] if key == e.path_key else None))
        if visible:
            out.append({"share_id": share.id, "share": share.name, "path": share.path, "entries": visible})
    return out


# ── Compliance ────────────────────────────────────────────────────────────────

class _Desc:
    """Reverses the order of a sort key (heapq only keeps the smallest items)."""

    __slots__ = ("key",)

    def __init__(self, key):
        self.key = key

    def __lt__(self, other: "_Desc") -> bool:
        return other.key < self.key

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Desc) and other.key == self.key


class _Capped:
    """
    The first `limit` items in `key` order (all of them if limit is None), and
    how many there were. Keeping the first ones *added* would show an arbitrary
    200 of the biggest offenders, in database order (BUG-036).
    """

    def __init__(self, limit: Optional[int], key):
        self.limit, self.key, self.count = limit, key, 0
        self._heap: list = []  # the kept items, largest key on top

    def add(self, item: dict) -> None:
        self.count += 1
        if self.limit == 0:
            return
        entry = (_Desc(self.key(item)), _Desc(self.count), item)
        if self.limit is None or len(self._heap) < self.limit:
            heapq.heappush(self._heap, entry)
        elif entry[0].key < self._heap[0][0].key:
            heapq.heapreplace(self._heap, entry)

    def out(self) -> dict:
        items = [item for _, _, item in sorted(self._heap, reverse=True)]
        return {"count": self.count, "items": items}


def evaluate(db: Session, share: Share, limit: Optional[int] = 200) -> Optional[dict]:
    """
    How one share follows its plan: files outside it, misnamed files, files of
    unexpected types, planned folders missing or empty, and overgrown folders.
    None if the share has no plan. Lists keep the first `limit` items (the
    biggest folders first, files by path; None: all); totals count all.
    """
    plan = _by_key(db, share.id)
    if not plan:
        return None
    rows = db.execute(
        select(Folder.id, Folder.parent_id, Folder.path, Folder.depth, Folder.list_error)
        .where(Folder.share_id == share.id)
    ).all()
    direct: dict[int, int] = dict(db.execute(
        select(File.folder_id, func.count(File.id)).where(File.share_id == share.id).group_by(File.folder_id)
    ).all())
    subtree = dict(direct)
    # Folders the scanner couldn't list, or with one below them: what they hold is unknown (BUG-038).
    unlisted = {fid for fid, _, _, _, list_error in rows if list_error is not None}
    unknown = set(unlisted)
    for fid, parent, _, _, _ in sorted(rows, key=lambda r: r[3], reverse=True):
        if parent is not None:
            subtree[parent] = subtree.get(parent, 0) + subtree.get(fid, 0)
            if fid in unknown:
                unknown.add(parent)

    def where(p: str, name: str = "") -> str:
        return display_path(share.path, p, name)

    def by_path(x: dict):
        return tree_order(x["path"].lower().replace("\\", "/"))

    def biggest(x: dict):
        return (-x["files"], by_path(x))

    placements = {fid: place(plan, p) for fid, _, p, _, _ in rows}
    paths = {fid: p for fid, _, p, _, _ in rows}
    outside, overgrown = _Capped(limit, biggest), _Capped(limit, biggest)
    misnamed, wrong_type, empty = _Capped(limit, by_path), _Capped(limit, by_path), _Capped(limit, by_path)
    missing = _Capped(limit, by_path)
    files_outside = 0
    governed: dict[int, PlanFolder] = {}  # folder -> entry whose naming/type rules apply

    for fid, parent, p, _, _ in rows:
        pl, n = placements[fid], direct.get(fid, 0)
        if pl.status == "outside":
            files_outside += n
            if parent is None or placements[parent].status != "outside":  # the top of an unplanned branch
                outside.add({
                    "path": where(p), "folder_id": fid, "files": subtree.get(fid, 0), "reason": "not_in_plan",
                    "plan_id": pl.entry.id if pl.entry else None,
                    "plan_path": where(pl.entry.path) if pl.entry else None,
                })
            continue
        entry = pl.entry
        if pl.status == "planned" and subtree.get(fid, 0) == 0 and fid not in unknown:
            empty.add({"plan_id": entry.id, "path": where(p)})
        if pl.status == "planned" and not entry.allow_files:
            if n:
                files_outside += n
                outside.add({"path": where(p), "folder_id": fid, "files": n, "reason": "no_files_here",
                             "plan_id": entry.id, "plan_path": where(entry.path)})
            continue
        if entry.naming_pattern or entry.extensions:
            governed[fid] = entry
        cap = entry.max_files or DEFAULT_MAX_FILES
        if n > cap:
            overgrown.add({"path": where(p), "folder_id": fid, "files": n, "limit": cap})

    existing = {path_key(p): fid for fid, p in paths.items()}
    for e in plan.values():
        if e.path_key in existing:
            continue
        key = e.path_key
        while key and key not in existing:
            key = posixpath.dirname(key)
        if existing.get(key) in unlisted:
            continue  # it may be there: the folder that would hold it couldn't be listed
        missing.add({"plan_id": e.id, "path": where(e.path)})

    named = 0
    ids = list(governed)
    for i in range(0, len(ids), _CHUNK):
        for folder_id, name, ext in db.execute(
            select(File.folder_id, File.name, File.extension).where(File.folder_id.in_(ids[i:i + _CHUNK]))
        ):
            entry = governed[folder_id]
            if entry.naming_pattern:
                # Only files under a naming rule count towards "correctly named" (BUG-039).
                named += 1
                if not name_matches(entry.naming_pattern, name):
                    misnamed.add({"path": where(paths[folder_id], name), "pattern": entry.naming_pattern,
                                  "plan_id": entry.id, "plan_path": where(entry.path)})
            if entry.extensions and ext not in entry.extensions:
                wrong_type.add({"path": where(paths[folder_id], name), "extension": ext,
                                "allowed": entry.extensions, "plan_id": entry.id, "plan_path": where(entry.path)})

    files_total = sum(direct.values())
    return {
        "share_id": share.id, "share": share.name,
        "totals": {
            "files_total": files_total, "files_in_plan": files_total - files_outside,
            "files_checked": named, "files_misnamed": misnamed.count, "files_wrong_type": wrong_type.count,
            "folders_planned": len(plan), "folders_missing": missing.count,
            "folders_empty": empty.count, "folders_overgrown": overgrown.count,
        },
        "outside": outside.out(),
        "misnamed": misnamed.out(),
        "wrong_type": wrong_type.out(),
        "missing": missing.out(),
        "empty": empty.out(),
        "overgrown": overgrown.out(),
    }


# ── Progress over time ────────────────────────────────────────────────────────

def take_snapshots(db: Session, day: Optional[date] = None) -> int:
    """Record today's totals for every enabled share with a plan (one row per share and day)."""
    day = day or datetime.now().astimezone().date()
    taken = 0
    for share in db.scalars(select(Share).where(Share.enabled).order_by(Share.id)):
        result = evaluate(db, share, limit=0)
        if result is None:
            continue
        snap = db.scalar(select(PlanSnapshot).where(PlanSnapshot.share_id == share.id, PlanSnapshot.day == day))
        if snap is None:
            snap = PlanSnapshot(share_id=share.id, day=day)
            db.add(snap)
        for k, v in result["totals"].items():
            setattr(snap, k, v)
        snap.taken_at = datetime.now(timezone.utc)
        taken += 1
    db.commit()
    return taken


SNAPSHOT_FIELDS = (
    "files_total", "files_in_plan", "files_checked", "files_misnamed", "files_wrong_type",
    "folders_planned", "folders_missing", "folders_empty", "folders_overgrown",
)


def progress(db: Session, days: int = HISTORY_DAYS) -> list[dict]:
    """Daily snapshots per share, oldest first, for the progress chart."""
    since = datetime.now().astimezone().date() - timedelta(days=days)
    out: dict[int, dict] = {}
    for snap, name in db.execute(
        select(PlanSnapshot, Share.name).join(Share, PlanSnapshot.share_id == Share.id)
        .where(PlanSnapshot.day >= since).order_by(Share.name, PlanSnapshot.day)
    ):
        share = out.setdefault(snap.share_id, {"share_id": snap.share_id, "share": name, "snapshots": []})
        share["snapshots"].append({"day": snap.day, "taken_at": snap.taken_at,
                                   **{k: getattr(snap, k) for k in SNAPSHOT_FIELDS}})
    return list(out.values())
