"""
Fake Windows permissions for local test shares (DEV_MODE only).

Local folders have no Windows ACLs the app can use, so without this nothing
would be searchable on a developer PC (no ACL = nobody sees it). By default
everyone can read everything. To test permissions, put a `.corplib-acl.json`
in a folder; it replaces the inherited permissions for that folder and below,
as "disable inheritance" does in Explorer:

    {"read": ["hr", "alice"], "deny": ["bob"], "list": ["everyone"]}

- read: open files and list folders, inherited by everything below
- deny: denied read, inherited by everything below
- list: list this folder only (its files stay closed: BUG-007)

A file can have permissions of its own (BUG-023), set in the ACL file of its
folder. They replace the folder's, unless "inherit" is true:

    {"files": {"salaries.xlsx": {"read": ["hr"]},
               "minutes.docx": {"deny": ["bob"], "inherit": true}}}

An ACL file with only "files" leaves the folder's own permissions alone.
Names are usernames or the groups in DEV_GROUPS; "everyone" is everyone.
"""

import json
import logging
import os
import posixpath
from typing import Optional

from ..acl.descriptor import (
    CONTAINER_INHERIT_ACE, FILE_GENERIC_READ, INHERITED_ACE, OBJECT_INHERIT_ACE, Ace,
    build_security_descriptor,
)
from ..auth.dev import dev_sid

logger = logging.getLogger(__name__)

ACL_FILE = ".corplib-acl.json"
INHERIT = OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
DEFAULT_RULES = {"read": ["everyone"]}
FOLDER_KEYS = ("read", "deny", "list")


def _folder_aces(rules: dict) -> list[Ace]:
    """The ACEs set on the folder holding the rules. Deny first, as Windows orders them."""
    aces = [Ace(dev_sid(n), "deny", FILE_GENERIC_READ, INHERIT) for n in rules.get("deny", [])]
    aces += [Ace(dev_sid(n), "allow", FILE_GENERIC_READ, INHERIT) for n in rules.get("read", [])]
    aces += [Ace(dev_sid(n), "allow", FILE_GENERIC_READ, 0) for n in rules.get("list", [])]
    return aces


def _inherited(aces: list[Ace], flag: int) -> list[Ace]:
    """What a child inherits: the ACEs with `flag` (OI for files, CI for folders)."""
    return [Ace(a.sid, a.ace_type, a.mask, a.flags | INHERITED_ACE) for a in aces if a.flags & flag]


def _read_rules(root: str, folder: str) -> Optional[dict]:
    """The ACL file of this folder; None if there is none, {} if it's broken (nobody: fail closed)."""
    path = os.path.join(root, *folder.split("/"), ACL_FILE) if folder else os.path.join(root, ACL_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            rules = json.load(f)
        return rules if isinstance(rules, dict) else {}
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable %s: %s", path, exc)
        return {}


def _nearest_rules(root: str, folder: str) -> tuple[str, dict]:
    """The closest folder at or above `folder` whose ACL file sets folder permissions, and its rules."""
    current = folder
    while True:
        rules = _read_rules(root, current)
        if rules is not None and (not rules or any(k in rules for k in FOLDER_KEYS)):
            return current, rules
        if not current:
            return "", DEFAULT_RULES
        current = posixpath.dirname(current)


def dev_security_descriptor(root: str, relpath: str) -> Optional[bytes]:
    abs_path = os.path.join(root, *relpath.split("/")) if relpath else root
    is_dir = os.path.isdir(abs_path)
    folder = relpath if is_dir else posixpath.dirname(relpath)
    owner_folder, rules = _nearest_rules(root, folder)
    aces = _folder_aces(rules)
    if not is_dir:
        inherited = _inherited(aces, OBJECT_INHERIT_ACE)
        own = ((_read_rules(root, folder) or {}).get("files") or {}).get(posixpath.basename(relpath))
        if own is None:
            return build_security_descriptor(inherited)
        explicit = [Ace(a.sid, a.ace_type, a.mask, 0) for a in _folder_aces(own)]
        if own.get("inherit"):
            return build_security_descriptor(explicit + inherited)
        return build_security_descriptor(explicit, protected=True)
    if owner_folder != folder:
        return build_security_descriptor(_inherited(aces, CONTAINER_INHERIT_ACE))
    return build_security_descriptor(aces, protected=True)


def provider_for(root: str):
    return lambda relpath: dev_security_descriptor(os.path.abspath(root), relpath)
