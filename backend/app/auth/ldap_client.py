"""LDAP / Active Directory authentication client using ldap3."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from ldap3 import ALL, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class LDAPUser:
    username: str
    display_name: str
    email: str
    groups: list[str] = field(default_factory=list)


def _extract_cn(dn: str) -> str:
    """Extract the CN value from a Distinguished Name string."""
    for part in dn.split(","):
        stripped = part.strip()
        if stripped.upper().startswith("CN="):
            return stripped[3:]
    return dn


def authenticate_ldap(username: str, password: str) -> Optional[LDAPUser]:
    """
    Authenticate against Active Directory via LDAP simple bind.
    Returns an LDAPUser on success, None on failure.
    """
    try:
        server = Server(
            settings.ldap_server,
            port=settings.ldap_port,
            use_ssl=settings.ldap_use_ssl,
            get_info=ALL,
        )
        # Authenticate by binding as the user
        user_principal = f"{username}@{settings.ldap_domain}"
        conn = Connection(server, user=user_principal, password=password, auto_bind=True)

        # Search for user attributes and group memberships
        search_base = settings.ldap_user_search_base or settings.ldap_base_dn
        search_filter = settings.ldap_user_filter.format(username=username)

        conn.search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["displayName", "mail", settings.ldap_group_attribute],
        )

        if not conn.entries:
            logger.warning("LDAP: user '%s' authenticated but no search result found.", username)
            return LDAPUser(username=username, display_name=username, email="")

        entry = conn.entries[0]
        display_name = str(entry.displayName) if entry.displayName else username
        email = str(entry.mail) if entry.mail else ""
        raw_groups = (
            entry[settings.ldap_group_attribute].values
            if entry[settings.ldap_group_attribute]
            else []
        )
        groups = [_extract_cn(str(g)) for g in raw_groups]

        conn.unbind()
        return LDAPUser(username=username, display_name=display_name, email=email, groups=groups)

    except LDAPException as exc:
        logger.debug("LDAP authentication failed for '%s': %s", username, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected LDAP error for '%s': %s", username, exc)
        return None
