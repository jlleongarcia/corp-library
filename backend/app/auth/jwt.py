"""
Bearer tokens for the API.

Phase 0 keeps v0.1's JWT login so the admin can reach the reports. Phase 1
replaces this with Kerberos SSO and an HttpOnly session cookie.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from ..config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass
class CurrentUser:
    username: str
    display_name: str
    email: str
    is_admin: bool
    sid: Optional[str] = None


def is_admin_user(username: str) -> bool:
    return username.lower() in {u.lower() for u in settings.admin_users}


def create_access_token(user: CurrentUser) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "sid": user.sid,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise unauthorized
    username = payload.get("sub")
    if not username:
        raise unauthorized
    return CurrentUser(
        username=username,
        display_name=payload.get("display_name") or username,
        email=payload.get("email") or "",
        sid=payload.get("sid"),
        # Admin status is re-evaluated on every request, so removing someone
        # from ADMIN_USERS takes effect immediately.
        is_admin=is_admin_user(username),
    )


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
