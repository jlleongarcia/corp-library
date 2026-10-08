"""
Active Directory: sign-in with a password, and the groups that decide access.

Every sign-in ends with the user's `tokenGroups`: the SIDs of all the security
groups they belong to, nested ones included. It is what Windows puts in their
access token, so checking ACLs against it gives the same answer Explorer does.
"""

import logging
import ssl
from dataclasses import dataclass, field
from typing import Optional

from ldap3 import BASE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPBindError, LDAPException
from ldap3.utils.conv import escape_filter_chars

from ..acl.descriptor import parse_sid
from ..config import settings

logger = logging.getLogger(__name__)

USER_ATTRIBUTES = ["sAMAccountName", "displayName", "mail", "objectSid", "userAccountControl"]
ACCOUNTDISABLE = 0x2


class DirectoryUnavailable(Exception):
    """AD couldn't answer (unreachable, certificate, permissions): not the user's fault."""


@dataclass
class LDAPUser:
    username: str  # sAMAccountName as stored in AD, lower-cased
    display_name: str
    email: str
    sid: Optional[str]
    group_sids: list[str] = field(default_factory=list)


def make_server() -> Server:
    """The domain controller, with its TLS certificate always validated."""
    tls = None
    if settings.ldap_use_ssl:
        # ldap3 skips certificate validation unless told otherwise; without it,
        # anyone in the middle could read the passwords sent in the bind.
        tls = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=settings.ldap_ca_cert_file or None,
            valid_names=[settings.ldap_server],
        )
    return Server(
        settings.ldap_server, port=settings.ldap_port, use_ssl=settings.ldap_use_ssl, tls=tls,
        connect_timeout=5,
    )


def _entries(conn: Connection) -> list[dict]:
    # Searches from the domain root can also return referrals; keep real entries only.
    return [r for r in conn.response or [] if r.get("type") == "searchResEntry"]


def _find_user(conn: Connection, username: str) -> Optional[dict]:
    conn.search(
        search_base=settings.ldap_user_search_base or settings.ldap_base_dn,
        search_filter=settings.ldap_user_filter.format(username=escape_filter_chars(username)),
        search_scope=SUBTREE,
        attributes=USER_ATTRIBUTES,
    )
    entries = _entries(conn)
    if len(entries) != 1:
        # We can't tie the name to exactly one account: fail closed.
        logger.warning("LDAP: the search for '%s' found %d accounts.", username, len(entries))
        return None
    return entries[0]


def _token_groups(conn: Connection, dn: str) -> list[str]:
    """
    All security groups of the account, nested included (constructed attribute;
    AD only computes it for a base-scope search on the account itself).
    """
    conn.search(search_base=dn, search_filter="(objectClass=*)", search_scope=BASE, attributes=["tokenGroups"])
    entries = _entries(conn)
    raw = entries[0]["raw_attributes"].get("tokenGroups", []) if entries else []
    if not raw:
        # Every account is at least in Domain Users: an empty answer means we
        # weren't allowed to read it, not that the user has no groups.
        raise DirectoryUnavailable(f"tokenGroups unreadable for {dn}")
    return [parse_sid(b)[0] for b in raw]


def _user_from_entry(conn: Connection, entry: dict) -> Optional[LDAPUser]:
    attrs, raw = entry["attributes"], entry["raw_attributes"]
    sam = str(attrs.get("sAMAccountName") or "").lower()
    if not sam or not raw.get("objectSid"):
        logger.warning("LDAP: account %s has no sAMAccountName or objectSid.", entry.get("dn"))
        return None
    if int(attrs.get("userAccountControl") or 0) & ACCOUNTDISABLE:
        logger.info("LDAP: account '%s' is disabled.", sam)
        return None
    return LDAPUser(
        username=sam,
        display_name=str(attrs.get("displayName") or sam),
        email=str(attrs.get("mail") or ""),
        sid=parse_sid(raw["objectSid"][0])[0],
        group_sids=_token_groups(conn, entry["dn"]),
    )


def authenticate_ldap(username: str, password: str) -> Optional[LDAPUser]:
    """
    Sign in by binding as the user. Returns None for bad credentials or when the
    name doesn't match exactly one account; raises DirectoryUnavailable when AD
    can't answer.

    The identity returned is the account AD finds for the typed username, not
    the typed text itself: admin rights are matched on it.
    """
    if not password:
        return None  # an empty password would be an anonymous bind
    try:
        conn = Connection(
            make_server(), user=f"{username}@{settings.ldap_domain}", password=password,
            auto_bind=True, read_only=True, receive_timeout=10,
        )
        try:
            entry = _find_user(conn, username)
            return _user_from_entry(conn, entry) if entry else None
        finally:
            conn.unbind()
    except LDAPBindError as exc:  # wrong username or password
        logger.debug("LDAP authentication failed for '%s': %s", username, exc)
        return None
    except (LDAPException, OSError) as exc:  # unreachable DC, TLS/certificate problem, ...
        logger.error("LDAP error while signing in '%s': %s: %s", username, type(exc).__name__, exc)
        raise DirectoryUnavailable(str(exc)) from exc


def lookup_user(username: str) -> Optional[LDAPUser]:
    """
    Look an account up with the service account (LDAP_BIND_DN): used after a
    Kerberos sign-in, and to refresh the groups of a long-lived session.
    Returns None if the account doesn't exist (any more); raises
    DirectoryUnavailable when AD can't answer.
    """
    if not settings.ldap_server or not settings.ldap_bind_dn:
        raise DirectoryUnavailable("LDAP_SERVER / LDAP_BIND_DN not configured")
    try:
        conn = Connection(
            make_server(), user=settings.ldap_bind_dn, password=settings.ldap_bind_password,
            auto_bind=True, read_only=True, receive_timeout=10,
        )
        try:
            entry = _find_user(conn, username)
            return _user_from_entry(conn, entry) if entry else None
        finally:
            conn.unbind()
    except (LDAPException, OSError) as exc:
        logger.error("LDAP lookup of '%s' failed: %s: %s", username, type(exc).__name__, exc)
        raise DirectoryUnavailable(str(exc)) from exc
