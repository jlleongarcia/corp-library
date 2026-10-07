"""
Access evaluation against a DACL, following Windows' MAXIMUM_ALLOWED semantics:
ACEs are processed in order; a deny ACE removes rights not yet granted, an allow
ACE adds rights not yet denied. Inherit-only ACEs don't apply to the object itself.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

FILE_READ_DATA = 0x0001  # also FILE_LIST_DIRECTORY on folders
FILE_WRITE_DATA = 0x0002
DELETE = 0x00010000
WRITE_DAC = 0x00040000
FILE_ALL_ACCESS = 0x001F01FF

OBJECT_INHERIT_ACE = 0x01
INHERIT_ONLY_ACE = 0x08
INHERITED_ACE = 0x10

# Placeholders replaced by the new file's owner/group when it inherits the ACE.
# File owners aren't scanned, so these can't be evaluated: they never grant.
CREATOR_SIDS = frozenset({"S-1-3-0", "S-1-3-1"})

# Every authenticated domain user carries these SIDs in their token when
# accessing a file share: Everyone, Authenticated Users, Network.
BASELINE_SIDS = frozenset({"S-1-1-0", "S-1-5-11", "S-1-5-2"})


class AceLike(Protocol):
    sid: str
    ace_type: str
    mask: int
    flags: int


def effective_mask(aces: Iterable[AceLike], token_sids: set[str] | frozenset[str]) -> int:
    granted = 0
    denied = 0
    for ace in aces:
        if ace.flags & INHERIT_ONLY_ACE or ace.sid not in token_sids:
            continue
        if ace.ace_type == "deny":
            denied |= ace.mask & ~granted
        else:
            granted |= ace.mask & ~denied
    return granted


def can_read(aces: Iterable[AceLike], token_sids: set[str] | frozenset[str]) -> bool:
    """For a folder's own DACL this means "can list the folder", not "can open its files"."""
    return bool(effective_mask(aces, token_sids) & FILE_READ_DATA)


@dataclass(frozen=True)
class InheritedAce:
    sid: str
    ace_type: str
    mask: int
    flags: int


def file_aces(folder_aces: Iterable[AceLike]) -> list[InheritedAce]:
    """
    The DACL a file inherits from its folder: only the folder's ACEs marked
    "object inherit" (applies to files), including inherit-only ones, in order.

    A folder's own access is the wrong question for its files: "Read, this folder
    only" lets people list a folder without opening anything in it, and "Read,
    files only" is inherit-only on the folder yet grants every file. Assumes the
    file has no explicit ACEs of its own (files aren't scanned individually).
    """
    return [
        InheritedAce(a.sid, a.ace_type, a.mask, (a.flags & ~INHERIT_ONLY_ACE) | INHERITED_ACE)
        for a in folder_aces
        if a.flags & OBJECT_INHERIT_ACE and a.sid not in CREATOR_SIDS
    ]


def file_effective_mask(folder_aces: Iterable[AceLike], token_sids: set[str] | frozenset[str]) -> int:
    return effective_mask(file_aces(folder_aces), token_sids)


def can_read_files(folder_aces: Iterable[AceLike], token_sids: set[str] | frozenset[str]) -> bool:
    """Whether the token can open the files directly inside a folder with this DACL."""
    return bool(file_effective_mask(folder_aces, token_sids) & FILE_READ_DATA)


def access_level(mask: int) -> str:
    """Summarise a mask the way Explorer's Security tab would."""
    if mask & FILE_ALL_ACCESS == FILE_ALL_ACCESS:
        return "full"
    if mask & FILE_WRITE_DATA and mask & DELETE and mask & FILE_READ_DATA:
        return "modify"
    if mask & FILE_WRITE_DATA:
        return "write"
    if mask & FILE_READ_DATA:
        return "read"
    return "none"
