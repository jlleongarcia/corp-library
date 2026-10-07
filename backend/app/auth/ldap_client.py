"""LDAP / Active Directory authentication client using ldap3."""

import logging
import ssl
from dataclasses import dataclass
from typing import Optional

from ldap3 import SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPBindError, LDAPException
from ldap3.utils.conv import escape_filter_chars

from ..acl.descriptor import parse_sid
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class LDAPUser:
    username: str  # sAMAccountName as stored in AD, lower-cased
    display_name: str
    email: str
    sid: Optional[str]


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
    return Server(settings.ldap_server, port=settings.ldap_port, use_ssl=settings.ldap_use_ssl, tls=tls)


def _entries(conn: Connection) -> list[dict]:
    # Searches from the domain root can also return referrals; keep real entries only.
    return [r for r in conn.response or [] if r.get("type") == "searchResEntry"]


def authenticate_ldap(username: str, password: str) -> Optional[LDAPUser]:
    """
    Authenticate against Active Directory by binding as the user.
    Returns an LDAPUser on success, None on failure.

    The identity returned is the account AD finds for the typed username, not
    the typed text itself: admin rights are matched on it.
    """
    if not password:
        return None  # an empty password would be an anonymous bind
    try:
        conn = Connection(
            make_server(), user=f"{username}@{settings.ldap_domain}", password=password,
            auto_bind=True, read_only=True,
        )
        conn.search(
            search_base=settings.ldap_user_search_base or settings.ldap_base_dn,
            search_filter=settings.ldap_user_filter.format(username=escape_filter_chars(username)),
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "displayName", "mail", "objectSid"],
        )
        entries = _entries(conn)
        conn.unbind()
        if len(entries) != 1:
            # Bound fine, but we can't tie the login to exactly one account: fail closed.
            logger.warning("LDAP: '%s' authenticated but the search found %d accounts.", username, len(entries))
            return None

        attrs, raw = entries[0]["attributes"], entries[0]["raw_attributes"]
        sam = str(attrs.get("sAMAccountName") or "").lower()
        if not sam:
            logger.warning("LDAP: account found for '%s' has no sAMAccountName.", username)
            return None
        return LDAPUser(
            username=sam,
            display_name=str(attrs.get("displayName") or sam),
            email=str(attrs.get("mail") or ""),
            sid=parse_sid(raw["objectSid"][0])[0] if raw.get("objectSid") else None,
        )
    except LDAPBindError as exc:  # wrong username or password
        logger.debug("LDAP authentication failed for '%s': %s", username, exc)
        return None
    except LDAPException as exc:  # unreachable DC, TLS/certificate problem, ...: an admin must see it
        logger.error("LDAP error while signing in '%s': %s: %s", username, type(exc).__name__, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected LDAP error for '%s': %s", username, exc)
        return None
