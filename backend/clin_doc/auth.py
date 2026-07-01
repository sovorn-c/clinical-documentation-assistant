"""Simple JWT auth (execute-plan §4, §9 Phase 2).

A ``users`` table + password hashing (passlib bcrypt) + JWT (python-jose). A
single demo clinician is seeded from settings on startup so the demo env is
login-able out of the box; override ``SEED_USERNAME``/``SEED_PASSWORD`` in any
real deployment (Phase 6 security pass).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlmodel import Session, select

from clin_doc.db.models import User
from clin_doc.db.session import get_session
from clin_doc.settings import get_settings

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _truncate(password: str) -> bytes:
    # bcrypt operates on up to 72 bytes; longer inputs are truncated (the
    # canonical bcrypt behavior). bcrypt>=4 raises instead, so do it ourselves.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_truncate(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_truncate(password), hashed.encode("utf-8"))
    except ValueError:
        return False


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username)).first()
    if user and verify_password(password, user.hashed_password):
        return user
    return None


def create_access_token(user: User) -> str:
    s = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=s.jwt_ttl_minutes)
    payload = {"sub": user.id, "username": user.username, "role": user.role, "exp": expire}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_alg)


def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_alg])


def get_current_user(
    token: Annotated[str, Depends(_oauth2)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        uid = payload.get("sub")
        if uid is None:
            raise creds_exc
    except JWTError as exc:
        raise creds_exc from exc
    user = session.get(User, uid)
    if user is None:
        raise creds_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


def seed_user(session: Session) -> User | None:
    """Create the demo clinician if no users exist. Returns the seeded user or None."""
    if session.exec(select(User)).first() is not None:
        return None
    s = get_settings()
    user = User(
        username=s.seed_username,
        hashed_password=hash_password(s.seed_password),
        display_name=s.seed_display_name,
        role="clinician",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
