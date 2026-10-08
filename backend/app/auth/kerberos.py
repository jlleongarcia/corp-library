"""
Kerberos single sign-on (HTTP Negotiate / SPNEGO).

The browser of a domain PC sends a Kerberos service ticket for HTTP/<APP_HOST>
in an `Authorization: Negotiate <base64>` header. We validate it with the
keytab IT generated for that SPN, which proves who the user is without any
password reaching the app. Groups are then read from AD as for any sign-in.

Needs the `gssapi` package and MIT Kerberos libraries: both are in the Docker
image (extra `sso`); on a Windows PC SSO simply reports itself unavailable.
"""

import base64
import binascii
import logging
import os
from dataclasses import dataclass
from typing import Optional

from ..config import settings

logger = logging.getLogger(__name__)


class SsoError(Exception):
    """The ticket was missing, invalid, or for another realm."""


@dataclass
class SsoResult:
    username: str  # the account name, without the realm, lower-cased
    reply_token: Optional[bytes]  # mutual authentication token for the browser, if any


def _accept(token: bytes) -> tuple[str, Optional[bytes]]:
    """Validate one SPNEGO token with the keytab; returns (principal, reply token)."""
    import gssapi  # only installed on Linux (extra `sso`)

    # The keytab is read through the environment variable MIT Kerberos looks at.
    os.environ["KRB5_KTNAME"] = settings.kerberos_keytab
    creds = gssapi.Credentials(usage="accept")
    ctx = gssapi.SecurityContext(creds=creds, usage="accept")
    reply = ctx.step(token)
    if not ctx.complete:
        # Browsers complete Kerberos in one round trip; anything else (NTLM
        # fallback, a multi-step exchange) is not supported.
        raise SsoError("Negotiation needs more than one step (NTLM is not supported)")
    return str(ctx.initiator_name), reply


# Replaced by the tests; never called when SSO is off.
acceptor = _accept


def authenticate(authorization_header: str) -> SsoResult:
    scheme, _, b64 = authorization_header.partition(" ")
    if scheme.lower() != "negotiate" or not b64.strip():
        raise SsoError("Not a Negotiate header")
    try:
        token = base64.b64decode(b64.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SsoError("Malformed Negotiate token") from exc
    if token.startswith(b"NTLMSSP"):
        # The PC didn't get a Kerberos ticket (not in the intranet zone, no SPN,
        # not on the domain): the sign-in form takes over.
        raise SsoError("Browser offered NTLM instead of Kerberos")

    try:
        principal, reply = acceptor(token)
    except SsoError:
        raise
    except Exception as exc:  # gssapi.exceptions.GSSError and friends
        logger.warning("SSO: ticket rejected: %s", exc)
        raise SsoError(str(exc)) from exc

    name, _, realm = principal.partition("@")
    expected = (settings.kerberos_realm or settings.ldap_domain).upper()
    if not name or realm.upper() != expected:
        logger.warning("SSO: principal %s is not from realm %s", principal, expected)
        raise SsoError("Ticket from an unexpected realm")
    return SsoResult(username=name.lower(), reply_token=reply)
