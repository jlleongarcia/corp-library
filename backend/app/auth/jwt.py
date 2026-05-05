from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from ..config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class CurrentUser:
    """Decoded JWT payload attached to every authenticated request."""

    def __init__(
        self,
        username: str,
        display_name: str,
        email: str,
        groups: list[str],
        is_admin: bool,
    ):
        self.username = username
        self.display_name = display_name
        self.email = email
        self.groups = groups
        self.is_admin = is_admin


def create_access_token(
    username: str,
    display_name: str,
    email: str,
    groups: list[str],
    is_admin: bool,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": username,
        "display_name": display_name,
        "email": email,
        "groups": groups,
        "is_admin": is_admin,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    _unauth = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if not username:
            raise _unauth
        return CurrentUser(
            username=username,
            display_name=payload.get("display_name", username),
            email=payload.get("email", ""),
            groups=payload.get("groups", []),
            is_admin=payload.get("is_admin", False),
        )
    except JWTError:
        raise _unauth


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
