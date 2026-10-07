import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.jwt import CurrentUser, create_access_token, get_current_user, is_admin_user
from ..auth.ldap_client import authenticate_ldap
from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _upsert_user(db: Session, user: CurrentUser) -> None:
    row = db.scalar(select(User).where(User.username == user.username))
    if row is None:
        row = User(username=user.username)
        db.add(row)
    row.display_name = user.display_name
    row.email = user.email
    row.sid = user.sid
    row.is_admin = user.is_admin
    row.last_login = datetime.now(timezone.utc)
    db.commit()


def _public(user: CurrentUser) -> UserPublic:
    return UserPublic(
        username=user.username, display_name=user.display_name, email=user.email, is_admin=user.is_admin
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if settings.dev_mode:
        if settings.ldap_server:
            raise HTTPException(status_code=500, detail="DEV_MODE must not be enabled when LDAP is configured")
        if not username or payload.password != settings.dev_password:
            raise invalid
        user = CurrentUser(username, username, "", is_admin_user(username))
    else:
        ldap_user = authenticate_ldap(username, payload.password)
        if not ldap_user:
            raise invalid
        # The account AD resolved, not the typed text, is the identity (and decides admin rights).
        user = CurrentUser(
            ldap_user.username, ldap_user.display_name, ldap_user.email,
            is_admin_user(ldap_user.username), ldap_user.sid,
        )

    _upsert_user(db, user)
    return TokenResponse(access_token=create_access_token(user), user=_public(user))


@router.get("/me", response_model=UserPublic)
def me(current_user: CurrentUser = Depends(get_current_user)):
    return _public(current_user)
