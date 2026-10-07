import pytest

from app.acl.descriptor import (
    FILE_ALL_ACCESS, FILE_GENERIC_READ, GENERIC_READ, INHERIT_ONLY_ACE, INHERITED_ACE,
    Ace, DescriptorError, build_security_descriptor, parse_security_descriptor, parse_sid, sid_to_bytes,
)
from app.acl.evaluate import access_level, can_read, can_read_files, effective_mask, file_aces

ALICE = "S-1-5-21-1000-2000-3000-1101"
BOB = "S-1-5-21-1000-2000-3000-1102"
FINANCE = "S-1-5-21-1000-2000-3000-2201"
MODIFY = 0x001301BF


def test_sid_round_trip():
    for sid in ("S-1-1-0", "S-1-5-32-544", ALICE):
        assert parse_sid(sid_to_bytes(sid))[0] == sid


def test_descriptor_round_trip():
    aces = [
        Ace(BOB, "deny", FILE_GENERIC_READ, 0),
        Ace(FINANCE, "allow", MODIFY, INHERITED_ACE | 0x3),
        Ace("S-1-3-0", "allow", FILE_ALL_ACCESS, INHERIT_ONLY_ACE | 0x3),
    ]
    sd = parse_security_descriptor(build_security_descriptor(aces, owner_sid=ALICE, protected=True))
    assert sd.owner_sid == ALICE
    assert sd.is_protected and not sd.is_null_dacl
    assert sd.aces == aces
    assert sd.has_explicit_aces  # the deny ACE is not inherited


def test_generic_rights_are_mapped():
    sd = parse_security_descriptor(build_security_descriptor([Ace(ALICE, "allow", GENERIC_READ, 0)]))
    assert sd.aces[0].mask == FILE_GENERIC_READ


def test_null_dacl_grants_everyone():
    # Control flags without SE_DACL_PRESENT: header only.
    raw = bytes([1, 0]) + (0x8000).to_bytes(2, "little") + bytes(16)
    sd = parse_security_descriptor(raw)
    assert sd.is_null_dacl
    assert can_read(sd.aces, {"S-1-1-0"})


def test_truncated_descriptor_raises():
    raw = build_security_descriptor([Ace(ALICE, "allow", MODIFY, 0)])
    with pytest.raises(DescriptorError):
        parse_security_descriptor(raw[:-6])


def test_acl_hash_ignores_owner_but_not_entries():
    a = [Ace(ALICE, "allow", MODIFY, 0)]
    h1 = parse_security_descriptor(build_security_descriptor(a, owner_sid=ALICE)).acl_hash()
    h2 = parse_security_descriptor(build_security_descriptor(a, owner_sid=BOB)).acl_hash()
    h3 = parse_security_descriptor(build_security_descriptor([Ace(BOB, "allow", MODIFY, 0)])).acl_hash()
    assert h1 == h2 != h3


def test_deny_before_allow_wins():
    aces = [Ace(ALICE, "deny", FILE_GENERIC_READ, 0), Ace(FINANCE, "allow", MODIFY, 0)]
    assert not can_read(aces, {ALICE, FINANCE})
    assert can_read(aces, {BOB, FINANCE})


def test_allow_before_deny_keeps_granted_rights():
    # Non-canonical order: Windows evaluates in order, so the earlier allow stands.
    aces = [Ace(FINANCE, "allow", FILE_GENERIC_READ, 0), Ace(ALICE, "deny", FILE_GENERIC_READ, 0)]
    assert can_read(aces, {ALICE, FINANCE})


def test_inherit_only_aces_do_not_apply():
    aces = [Ace(ALICE, "allow", FILE_ALL_ACCESS, INHERIT_ONLY_ACE)]
    assert not can_read(aces, {ALICE})


def test_no_matching_sid_means_no_access():
    assert not can_read([Ace(FINANCE, "allow", MODIFY, 0)], {ALICE})
    assert not can_read([], {ALICE})


def test_access_levels():
    assert access_level(FILE_ALL_ACCESS) == "full"
    assert access_level(MODIFY) == "modify"
    assert access_level(FILE_GENERIC_READ) == "read"
    assert access_level(0) == "none"
    assert access_level(effective_mask([Ace(ALICE, "allow", MODIFY, 0)], {ALICE})) == "modify"


# ── Files inside a folder (BUG-007) ──────────────────────────────────────────

THIS_FOLDER_ONLY = 0x0
FILES_ONLY = 0x1 | INHERIT_ONLY_ACE  # object inherit + inherit only
FOLDER_SUBFOLDERS_FILES = 0x3


def test_this_folder_only_lets_users_list_but_not_open_files():
    aces = [Ace(FINANCE, "allow", FILE_GENERIC_READ, THIS_FOLDER_ONLY)]
    assert can_read(aces, {FINANCE})  # can list the folder
    assert not can_read_files(aces, {FINANCE})  # but its files don't inherit the ACE


def test_files_only_grant_applies_to_files_not_the_folder():
    aces = [Ace(FINANCE, "allow", FILE_GENERIC_READ, FILES_ONLY)]
    assert not can_read(aces, {FINANCE})
    assert can_read_files(aces, {FINANCE})


def test_inherited_deny_on_files_is_kept_in_order():
    aces = [
        Ace(ALICE, "deny", FILE_GENERIC_READ, FOLDER_SUBFOLDERS_FILES),
        Ace(FINANCE, "allow", MODIFY, FOLDER_SUBFOLDERS_FILES),
    ]
    assert not can_read_files(aces, {ALICE, FINANCE})
    assert can_read_files(aces, {BOB, FINANCE})
    assert all(a.flags & INHERITED_ACE and not a.flags & INHERIT_ONLY_ACE for a in file_aces(aces))


def test_creator_owner_never_grants_on_files():
    aces = [Ace("S-1-3-0", "allow", FILE_ALL_ACCESS, FILES_ONLY)]
    assert not can_read_files(aces, {"S-1-3-0", ALICE})
