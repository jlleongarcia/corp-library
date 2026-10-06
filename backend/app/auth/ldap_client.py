"""LDAP / Active Directory authentication client using ldap3."""

import logging
from dataclasses import dataclass
from typing import Optional

from ldap3 import SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException

from ..acl.descriptor import parse_sid
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class LDAPUser:
    username: str
    display_name: str
    email: str
    sid: Optional[str]


def authenticate_ldap(username: str, password: str) -> Optional[LDAPUser]:
    """
    Authenticate against Active Directory by binding as the user.
    Returns an LDAPUser on success, None on failure.
    """
    if not password:
        return None  # an empty password would be an anonymous bind
    try:
        server = Server(settings.ldap_server, port=settings.ldap_port, use_ssl=settings.ldap_use_ssl)
        conn = Connection(
            server, user=f"{username}@{settings.ldap_domain}", password=password,
            auto_bind=True, read_only=True,
        )
        conn.search(
            search_base=settings.ldap_user_search_base or settings.ldap_base_dn,
            search_filter=settings.ldap_user_filter.format(username=username),
            search_scope=SUBTREE,
            attributes=["displayName", "mail", "objectSid"],
        )
        if not conn.response or "raw_attributes" not in conn.response[0]:
            logger.warning("LDAP: user '%s' authenticated but no search result found.", username)
            conn.unbind()
            return LDAPUser(username=username, display_name=username, email="", sid=None)

        entry = conn.response[0]
        attrs, raw = entry["attributes"], entry["raw_attributes"]
        sid = parse_sid(raw["objectSid"][0])[0] if raw.get("objectSid") else None
        conn.unbind()
        return LDAPUser(
            username=username,
            display_name=str(attrs.get("displayName") or username),
            email=str(attrs.get("mail") or ""),
            sid=sid,
        )
    except LDAPException as exc:
        logger.debug("LDAP authentication failed for '%s': %s", username, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected LDAP error for '%s': %s", username, exc)
        return None
