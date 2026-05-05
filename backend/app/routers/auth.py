import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..auth.jwt import CurrentUser, create_access_token, get_current_user
from ..auth.ldap_client import authenticate_ldap
from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _upsert_user(
    db: Session,
    username: str,
    display_name: str,
    email: str,
    groups: list[str],
    is_admin: bool,
) -> User:
    user = db.query(User).filter(User.username == username).first()
    now = datetime.now(timezone.utc)
    if user:
        user.display_name = display_name
        user.email = email
        user.ad_groups = json.dumps(groups)
        user.last_login = now
    else:
        user = User(
            username=username,
            display_name=display_name,
            email=email,
            ad_groups=json.dumps(groups),
            is_admin=is_admin,
            last_login=now,
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()

    if settings.dev_mode:
        # --- Dev mode: built-in admin account ---
        if (
            username == settings.dev_admin_username.lower()
            and payload.password == settings.dev_admin_password
        ):
            _upsert_user(db, username, "Admin User", "admin@corp.local", ["IT_Admins"], True)
            token = create_access_token(
                username, "Admin User", "admin@corp.local", ["IT_Admins"], True
            )
            return TokenResponse(
                access_token=token,
                user=UserPublic(
                    username=username,
                    display_name="Admin User",
                    email="admin@corp.local",
                    is_admin=True,
                    ad_groups=["IT_Admins"],
                ),
            )
        # --- Dev mode: local DB users (for testing multiple roles) ---
        db_user = db.query(User).filter(User.username == username).first()
        if (
            db_user
            and db_user.hashed_password
            and pwd_context.verify(payload.password, db_user.hashed_password)
        ):
            groups = json.loads(db_user.ad_groups or "[]")
            token = create_access_token(
                db_user.username,
                db_user.display_name or username,
                db_user.email or "",
                groups,
                db_user.is_admin,
            )
            db_user.last_login = datetime.now(timezone.utc)
            db.commit()
            return TokenResponse(
                access_token=token,
                user=UserPublic(
                    username=db_user.username,
                    display_name=db_user.display_name,
                    email=db_user.email,
                    is_admin=db_user.is_admin,
                    ad_groups=groups,
                ),
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # --- Production: LDAP / Active Directory ---
    ldap_user = authenticate_ldap(username, payload.password)
    if not ldap_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    is_admin = bool({"IT_Admins", "CorpLibrary_Admins"} & set(ldap_user.groups))
    _upsert_user(db, username, ldap_user.display_name, ldap_user.email, ldap_user.groups, is_admin)
    token = create_access_token(
        username, ldap_user.display_name, ldap_user.email, ldap_user.groups, is_admin
    )
    return TokenResponse(
        access_token=token,
        user=UserPublic(
            username=username,
            display_name=ldap_user.display_name,
            email=ldap_user.email,
            is_admin=is_admin,
            ad_groups=ldap_user.groups,
        ),
    )


@router.get("/me", response_model=UserPublic)
def me(current_user: CurrentUser = Depends(get_current_user)):
    return UserPublic(
        username=current_user.username,
        display_name=current_user.display_name,
        email=current_user.email,
        is_admin=current_user.is_admin,
        ad_groups=current_user.groups,
    )
