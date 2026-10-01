"""Owner bootstrap/login. Bootstrap only ever works while no owner account exists yet, and (per the
spec) is meant to be run locally before the app is exposed anywhere — `main.py` binds to
127.0.0.1 by default specifically so an unclaimed bootstrap flow is never reachable from outside
the machine unless the operator deliberately changes LTP_HOST.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.schemas import BootstrapRequest, LoginRequest
from app.config import settings
from app.models.db import Owner, get_db_session
from app.security.auth import (
    create_session_token,
    get_current_owner,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, owner_id: int) -> None:
    token = create_session_token(owner_id)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=False,  # set True automatically once served over HTTPS in production — see docs
    )


@router.get("/status")
def status(db: Session = Depends(get_db_session)) -> dict:
    owner_exists = db.query(Owner).count() > 0
    return {"owner_exists": owner_exists}


@router.post("/bootstrap")
def bootstrap(body: BootstrapRequest, response: Response, db: Session = Depends(get_db_session)) -> dict:
    if db.query(Owner).count() > 0:
        raise HTTPException(status_code=409, detail="An owner account already exists.")
    owner = Owner(username=body.username, password_hash=hash_password(body.password))
    db.add(owner)
    db.commit()
    db.refresh(owner)
    _set_session_cookie(response, owner.id)
    return {"username": owner.username}


@router.post("/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db_session)) -> dict:
    owner = db.query(Owner).filter_by(username=body.username).one_or_none()
    if owner is None or not verify_password(body.password, owner.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    _set_session_cookie(response, owner.id)
    return {"username": owner.username}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(settings.session_cookie_name)
    return {"ok": True}


@router.get("/me")
def me(owner: Owner = Depends(get_current_owner)) -> dict:
    return {"username": owner.username}
