"""
Access evaluation against a DACL, following Windows' MAXIMUM_ALLOWED semantics:
ACEs are processed in order; a deny ACE removes rights not yet granted, an allow
ACE adds rights not yet denied. Inherit-only ACEs don't apply to the object itself.
"""

from collections.abc import Iterable
from typing import Protocol

FILE_READ_DATA = 0x0001  # also FILE_LIST_DIRECTORY on folders
FILE_WRITE_DATA = 0x0002
DELETE = 0x00010000
WRITE_DAC = 0x00040000
FILE_ALL_ACCESS = 0x001F01FF

INHERIT_ONLY_ACE = 0x08

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
    return bool(effective_mask(aces, token_sids) & FILE_READ_DATA)


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
