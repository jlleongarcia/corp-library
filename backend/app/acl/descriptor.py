"""
Parser for self-relative Windows security descriptors ([MS-DTYP] 2.4.6).

The scanner fetches each folder's descriptor over SMB as raw bytes; this module
turns it into an owner SID plus an ordered list of ACEs. Only the DACL matters
for read access, so the SACL is ignored.
"""

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional

# Security descriptor control flags
SE_DACL_PRESENT = 0x0004
SE_DACL_PROTECTED = 0x1000

# ACE types
ACCESS_ALLOWED = 0x00
ACCESS_DENIED = 0x01
ACCESS_ALLOWED_CALLBACK = 0x09
ACCESS_DENIED_CALLBACK = 0x0A

# ACE flags
OBJECT_INHERIT_ACE = 0x01
CONTAINER_INHERIT_ACE = 0x02
INHERIT_ONLY_ACE = 0x08
INHERITED_ACE = 0x10

# Generic rights and their file-system mapping ([MS-SMB2] / winnt.h)
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
GENERIC_EXECUTE = 0x20000000
GENERIC_ALL = 0x10000000
FILE_GENERIC_READ = 0x00120089
FILE_GENERIC_WRITE = 0x00120116
FILE_GENERIC_EXECUTE = 0x001200A0
FILE_ALL_ACCESS = 0x001F01FF

EVERYONE_SID = "S-1-1-0"


class DescriptorError(ValueError):
    """Raised when the bytes are not a valid self-relative security descriptor."""


@dataclass(frozen=True)
class Ace:
    sid: str
    ace_type: str  # "allow" | "deny"
    mask: int
    flags: int

    @property
    def inherited(self) -> bool:
        return bool(self.flags & INHERITED_ACE)

    @property
    def inherit_only(self) -> bool:
        return bool(self.flags & INHERIT_ONLY_ACE)


@dataclass
class SecurityDescriptor:
    owner_sid: Optional[str]
    is_protected: bool  # inheritance from the parent is disabled
    is_null_dacl: bool  # no DACL at all: Windows grants everyone full access
    aces: list[Ace] = field(default_factory=list)

    @property
    def has_explicit_aces(self) -> bool:
        return any(not a.inherited for a in self.aces)

    def acl_hash(self) -> str:
        """Stable hash of the DACL, used to deduplicate identical ACLs across folders."""
        h = hashlib.sha256()
        h.update(b"P" if self.is_protected else b"-")
        h.update(b"N" if self.is_null_dacl else b"-")
        for a in self.aces:
            h.update(f"|{a.ace_type}:{a.sid}:{a.mask:08x}:{a.flags:02x}".encode())
        return h.hexdigest()


def map_generic(mask: int) -> int:
    """Expand generic rights into their file-system specific equivalents."""
    if mask & GENERIC_READ:
        mask |= FILE_GENERIC_READ
    if mask & GENERIC_WRITE:
        mask |= FILE_GENERIC_WRITE
    if mask & GENERIC_EXECUTE:
        mask |= FILE_GENERIC_EXECUTE
    if mask & GENERIC_ALL:
        mask |= FILE_ALL_ACCESS
    return mask & ~(GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE | GENERIC_ALL)


def parse_sid(data: bytes, offset: int = 0) -> tuple[str, int]:
    """Parse a binary SID at offset. Returns (string SID, byte length)."""
    if offset + 8 > len(data):
        raise DescriptorError("SID truncated")
    revision, count = data[offset], data[offset + 1]
    authority = int.from_bytes(data[offset + 2 : offset + 8], "big")
    end = offset + 8 + 4 * count
    if end > len(data):
        raise DescriptorError("SID sub-authorities truncated")
    subs = struct.unpack_from(f"<{count}I", data, offset + 8)
    return "-".join(["S", str(revision), str(authority), *map(str, subs)]), end - offset


def sid_to_bytes(sid: str) -> bytes:
    """Encode a string SID in binary form (used by tests and LDAP lookups)."""
    parts = sid.split("-")
    if len(parts) < 3 or parts[0].upper() != "S":
        raise ValueError(f"Not a SID: {sid}")
    revision, authority = int(parts[1]), int(parts[2])
    subs = [int(p) for p in parts[3:]]
    return (
        bytes([revision, len(subs)])
        + authority.to_bytes(6, "big")
        + struct.pack(f"<{len(subs)}I", *subs)
    )


def _parse_acl(data: bytes, offset: int) -> list[Ace]:
    if offset + 8 > len(data):
        raise DescriptorError("ACL header truncated")
    _rev, _sbz1, acl_size, ace_count, _sbz2 = struct.unpack_from("<BBHHH", data, offset)
    if offset + acl_size > len(data):
        raise DescriptorError("ACL truncated")
    aces: list[Ace] = []
    pos = offset + 8
    for _ in range(ace_count):
        if pos + 4 > offset + acl_size:
            raise DescriptorError("ACE header truncated")
        ace_type, ace_flags, ace_size = struct.unpack_from("<BBH", data, pos)
        if ace_size < 4 or pos + ace_size > offset + acl_size:
            raise DescriptorError("Invalid ACE size")
        if ace_type in (ACCESS_ALLOWED, ACCESS_DENIED, ACCESS_ALLOWED_CALLBACK, ACCESS_DENIED_CALLBACK):
            (mask,) = struct.unpack_from("<I", data, pos + 4)
            sid, _ = parse_sid(data, pos + 8)
            if ace_type in (ACCESS_ALLOWED, ACCESS_DENIED):
                kind = "allow" if ace_type == ACCESS_ALLOWED else "deny"
                aces.append(Ace(sid=sid, ace_type=kind, mask=map_generic(mask), flags=ace_flags))
            elif ace_type == ACCESS_DENIED_CALLBACK:
                # Conditional deny: we can't evaluate the condition, so assume it applies.
                aces.append(Ace(sid=sid, ace_type="deny", mask=map_generic(mask), flags=ace_flags))
            # Conditional allow: we can't evaluate the condition, so it never grants (fail closed).
        # Object ACEs and others don't occur on file-system objects; skipping an
        # unknown allow is safe, and unknown deny types don't exist for files.
        pos += ace_size
    return aces


def parse_security_descriptor(data: bytes) -> SecurityDescriptor:
    if len(data) < 20:
        raise DescriptorError("Security descriptor too short")
    _rev, _sbz1, control, off_owner, _off_group, _off_sacl, off_dacl = struct.unpack_from(
        "<BBHIIII", data, 0
    )
    owner = parse_sid(data, off_owner)[0] if off_owner else None
    is_protected = bool(control & SE_DACL_PROTECTED)

    if not (control & SE_DACL_PRESENT) or off_dacl == 0:
        # NULL DACL: Windows grants full access to everyone. Mirror that faithfully
        # and let the hygiene report flag it.
        return SecurityDescriptor(
            owner_sid=owner,
            is_protected=is_protected,
            is_null_dacl=True,
            aces=[Ace(EVERYONE_SID, "allow", FILE_ALL_ACCESS, 0)],
        )

    return SecurityDescriptor(
        owner_sid=owner,
        is_protected=is_protected,
        is_null_dacl=False,
        aces=_parse_acl(data, off_dacl),
    )


# ── Builder (tests and the local dev source) ─────────────────────────────────

def build_security_descriptor(
    aces: list[Ace], owner_sid: Optional[str] = None, protected: bool = False
) -> bytes:
    """Encode a self-relative security descriptor. The inverse of the parser."""
    ace_blobs = []
    for a in aces:
        sid = sid_to_bytes(a.sid)
        ace_type = ACCESS_ALLOWED if a.ace_type == "allow" else ACCESS_DENIED
        size = 8 + len(sid)
        ace_blobs.append(struct.pack("<BBHI", ace_type, a.flags, size, a.mask) + sid)
    acl_body = b"".join(ace_blobs)
    acl = struct.pack("<BBHHH", 2, 0, 8 + len(acl_body), len(aces), 0) + acl_body

    owner = sid_to_bytes(owner_sid) if owner_sid else b""
    control = 0x8000 | SE_DACL_PRESENT | (SE_DACL_PROTECTED if protected else 0)
    off_owner = 20 if owner else 0
    off_dacl = 20 + len(owner)
    header = struct.pack("<BBHIIII", 1, 0, control, off_owner, 0, 0, off_dacl)
    return header + owner + acl
