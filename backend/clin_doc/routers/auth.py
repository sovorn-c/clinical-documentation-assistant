"""Auth endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from clin_doc.auth import CurrentUser, LoginForm, authenticate, create_access_token
from clin_doc.db.session import DbSession
from clin_doc.schemas import Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: LoginForm, session: DbSession) -> Token:
    user = authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return Token(access_token=create_access_token(user))


@router.get("/me", response_model=dict)
def me(user: CurrentUser) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }
