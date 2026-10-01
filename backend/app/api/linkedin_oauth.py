"""LinkedIn OAuth authorization-code flow. `/start` and `/callback` are reached by the user's
browser being redirected by LinkedIn, not by the frontend's fetch client, so they are NOT behind
the owner-auth dependency the way other API routes are — the CSRF protection here is the OAuth
`state` parameter itself (generated per attempt, stored server-side, checked on callback and
cleared immediately after use, exactly the purpose `state` exists for in the OAuth spec).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.integrations import linkedin
from app.models.db import LinkedInCredential, get_db_session
from app.services import credentials as cred_service

log = logging.getLogger("ltp.api.linkedin_oauth")
router = APIRouter(prefix="/api/linkedin/oauth", tags=["linkedin-oauth"])


def _redirect_uri(request: Request) -> str:
    from app.config import settings as env_settings

    base = str(request.base_url).rstrip("/")
    return f"{base}{env_settings.linkedin_redirect_path}"


@router.get("/start")
def start(request: Request, db: Session = Depends(get_db_session)):
    from app.config import settings as env_settings

    client_id, client_secret = cred_service.get_linkedin_app_credentials(db)
    if not client_id or not client_secret:
        raise HTTPException(422, "Configure a LinkedIn client id and secret in Settings first.")
    auth_url, state = linkedin.build_authorization_url(client_id, _redirect_uri(request), env_settings.linkedin_scopes)
    row = db.get(LinkedInCredential, 1)
    if row is None:
        row = LinkedInCredential(id=1)
        db.add(row)
    row.oauth_state = state
    db.commit()
    return RedirectResponse(auth_url)


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db_session)):
    row = db.get(LinkedInCredential, 1)
    frontend_settings_url = "/settings?linkedin="

    if error:
        return RedirectResponse(f"{frontend_settings_url}error&message={error}")
    if not code or not state or not row or state != row.oauth_state:
        return RedirectResponse(f"{frontend_settings_url}error&message=invalid_or_expired_state")
    row.oauth_state = None
    db.commit()

    client_id, client_secret = cred_service.get_linkedin_app_credentials(db)
    if not client_id or not client_secret:
        return RedirectResponse(f"{frontend_settings_url}error&message=app_not_configured")

    try:
        token_data = await linkedin.exchange_code_for_token(code=code, client_id=client_id, client_secret=client_secret, redirect_uri=_redirect_uri(request))
        access_token = token_data["access_token"]
        member = await linkedin.fetch_member_info(access_token)
        account_name = member.get("name") or member.get("given_name") or "LinkedIn account"
        account_urn = f"urn:li:person:{member['sub']}"
        expires_at = linkedin.token_expiry_from_response(token_data)
        cred_service.save_linkedin_tokens(db, access_token, token_data.get("refresh_token"), expires_at, account_name, account_urn)
    except linkedin.LinkedInError as exc:
        log.error("LinkedIn OAuth callback failed: %s", exc)
        return RedirectResponse(f"{frontend_settings_url}error&message=token_exchange_failed")

    return RedirectResponse(f"{frontend_settings_url}connected")
