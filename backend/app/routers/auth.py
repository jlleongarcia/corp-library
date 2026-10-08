"""
Sign-in. Two ways in, same result (a session cookie with the user's groups):

- GET /auth/sso: Kerberos. The browser of a domain PC answers the
  `WWW-Authenticate: Negotiate` challenge with a ticket, without the user typing anything.
- POST /auth/login: the sign-in form (LDAP bind as the user), the fallback when
  SSO isn't available on a PC. In DEV_MODE, any username without a password.
"""

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..auth import kerberos, throttle
from ..auth.dev import dev_identity
from ..auth.ldap_client import DirectoryUnavailable, authenticate_ldap, lookup_user
from ..auth.sessions import CurrentUser, end_session, get_current_user, start_session
from ..config import dev_mode_problem, settings
from ..database import get_db
from ..schemas import AuthConfig, LoginRequest, UserPublic
from ..services import audit

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

DIRECTORY_DOWN = "Active Directory can't be reached right now. Please try again in a few minutes."


def _public(user: CurrentUser) -> UserPublic:
    return UserPublic(
        username=user.username, display_name=user.display_name, email=user.email, is_admin=user.is_admin
    )


@router.get("/config", response_model=AuthConfig)
def config():
    return AuthConfig(app_name=settings.app_name, sso_enabled=settings.sso_enabled, dev_mode=settings.dev_mode)


@router.get("/sso", response_model=UserPublic)
def sso(request: Request, response: Response, db: Session = Depends(get_db)):
    if not settings.sso_enabled:
        raise HTTPException(status_code=404, detail="Single sign-on is not configured")
    header = request.headers.get("authorization")
    if not header:
        # The challenge: a browser that trusts this site retries with a Kerberos ticket.
        raise HTTPException(status_code=401, detail="Negotiate", headers={"WWW-Authenticate": "Negotiate"})
    try:
        result = kerberos.authenticate(header)
    except kerberos.SsoError as exc:
        # 403, not 401: a second challenge would only make the browser try again.
        audit.record(db, "sign_in_failed", None, request, method="sso", reason=str(exc)[:200])
        raise HTTPException(status_code=403, detail="Single sign-on failed")

    try:
        who = lookup_user(result.username)
    except DirectoryUnavailable:
        raise HTTPException(status_code=503, detail=DIRECTORY_DOWN)
    if who is None:
        audit.record(db, "sign_in_failed", result.username, request, method="sso", reason="account not found or disabled")
        raise HTTPException(status_code=403, detail="Your account was not found in Active Directory")

    user = start_session(db, request, response, who, "sso")
    audit.record(db, "sign_in", user.username, request, method="sso")
    if result.reply_token:
        response.headers["WWW-Authenticate"] = "Negotiate " + base64.b64encode(result.reply_token).decode()
    return _public(user)


@router.post("/login", response_model=UserPublic)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    # DOMAIN\alice and alice@domain work too (BUG-029).
    username = throttle.normalize_username(payload.username)
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if settings.dev_mode:
        # Checked at startup too; repeated here so no code path can skip it.
        if problem := dev_mode_problem(settings):
            raise HTTPException(status_code=500, detail=problem)
        who = dev_identity(username)
        method = "dev"
    else:
        # Refused here, before AD sees another wrong password: the form must not be a
        # way to lock a colleague's account (BUG-029).
        if wait := throttle.blocked_for(username):
            minutes = max(1, -(-int(wait.total_seconds()) // 60))
            audit.record(db, "sign_in_failed", username, request, method="ldap", reason="throttled")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed sign-ins for this account. Try again in {minutes} minute"
                       f"{'s' if minutes != 1 else ''}, or ask IT if you've forgotten your password.",
                headers={"Retry-After": str(int(wait.total_seconds()) + 1)},
            )
        try:
            who = authenticate_ldap(username, payload.password)
        except DirectoryUnavailable:
            raise HTTPException(status_code=503, detail=DIRECTORY_DOWN)
        if who is None:
            throttle.record_failure(username)
            audit.record(db, "sign_in_failed", username, request, method="ldap")
            raise invalid
        throttle.record_success(username)
        method = "ldap"

    # The account AD resolved, not the typed text, is the identity (and decides admin rights).
    user = start_session(db, request, response, who, method)
    audit.record(db, "sign_in", user.username, request, method=method)
    return _public(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           user: CurrentUser = Depends(get_current_user)):
    audit.record(db, "sign_out", user.username, request)
    end_session(db, request, response)


@router.get("/me", response_model=UserPublic)
def me(current_user: CurrentUser = Depends(get_current_user)):
    return _public(current_user)
