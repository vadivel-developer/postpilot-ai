"""LinkedIn OAuth 2.0 (authorization code flow) and the Posts API (personal-profile publishing),
against LinkedIn's official REST endpoints. This module makes real HTTP calls to
api.linkedin.com / www.linkedin.com — it has not been exercised against a live LinkedIn developer
app in this environment (no client id/secret was available to test with); see docs/VERIFICATION.md
for exactly what is and isn't confirmed working end to end.

Company-page posting is a separate LinkedIn permission (`w_organization_social`) and a separate API
shape from personal-profile posting; this module only implements the personal-profile path the spec
asked for first, and never assumes one permission implies the other.
"""

from __future__ import annotations

import datetime as dt
import logging
import secrets

import httpx

log = logging.getLogger("ltp.linkedin")

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
IMAGES_REGISTER_URL = "https://api.linkedin.com/rest/images?action=initializeUpload"
API_VERSION = "202409"  # LinkedIn-Version header; bump when the app is verified against a newer one


class LinkedInError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def build_authorization_url(client_id: str, redirect_uri: str, scopes: str) -> tuple[str, str]:
    """Returns (authorization_url, state) — state must be stored server-side and checked on callback."""
    state = secrets.token_urlsafe(24)
    params = httpx.QueryParams({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "scope": scopes, "state": state})
    return f"{AUTH_URL}?{params}", state


async def exchange_code_for_token(*, code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            TOKEN_URL,
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "client_id": client_id, "client_secret": client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if r.status_code != 200:
        raise LinkedInError(f"Token exchange failed: {r.status_code} {r.text[:300]}", r.status_code)
    return r.json()


async def fetch_member_info(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code != 200:
        raise LinkedInError(f"Could not fetch account info: {r.status_code} {r.text[:300]}", r.status_code)
    return r.json()


async def upload_image(access_token: str, person_urn: str, image_bytes: bytes) -> str:
    """Registers and uploads an image, returning its asset URN for use in a post."""
    async with httpx.AsyncClient(timeout=30) as client:
        reg = await client.post(
            IMAGES_REGISTER_URL,
            json={"initializeUploadRequest": {"owner": person_urn}},
            headers={"Authorization": f"Bearer {access_token}", "LinkedIn-Version": API_VERSION, "Content-Type": "application/json"},
        )
        if reg.status_code not in (200, 201):
            raise LinkedInError(f"Image upload registration failed: {reg.status_code} {reg.text[:300]}", reg.status_code)
        data = reg.json()["value"]
        upload_url, asset_urn = data["uploadUrl"], data["image"]

        put = await client.put(upload_url, content=image_bytes, headers={"Authorization": f"Bearer {access_token}"})
        if put.status_code not in (200, 201):
            raise LinkedInError(f"Image upload failed: {put.status_code}", put.status_code)
    return asset_urn


async def create_post(*, access_token: str, person_urn: str, text: str, image_asset_urn: str | None) -> dict:
    """Publishes a text (optionally + image) post to the connected personal profile. Returns the
    response headers/body needed to record a durable post id."""
    payload: dict = {
        "author": person_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if image_asset_urn:
        payload["content"] = {"media": {"id": image_asset_urn}}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            POSTS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}", "LinkedIn-Version": API_VERSION, "Content-Type": "application/json", "X-Restli-Protocol-Version": "2.0.0"},
        )
    if r.status_code == 201:
        post_urn = r.headers.get("x-restli-id") or r.headers.get("X-RestLi-Id")
        return {"status": "published", "post_urn": post_urn}
    if r.status_code in (408, 502, 503, 504):
        # Server-side outcome genuinely unknown from this response alone.
        raise LinkedInError(f"LinkedIn did not confirm the post (HTTP {r.status_code}) — treat as uncertain, do not retry blindly.", r.status_code)
    raise LinkedInError(f"LinkedIn rejected the post: {r.status_code} {r.text[:300]}", r.status_code)


def post_url_from_urn(post_urn: str | None) -> str | None:
    if not post_urn:
        return None
    # LinkedIn does not publish a stable, documented public-URL-from-URN mapping for every post
    # type; the activity id embedded in the URN is the best identifier we can surface reliably.
    return f"https://www.linkedin.com/feed/update/{post_urn}/"


def token_expiry_from_response(token_response: dict) -> dt.datetime | None:
    expires_in = token_response.get("expires_in")
    if not expires_in:
        return None
    return dt.datetime.now(dt.UTC) + dt.timedelta(seconds=int(expires_in))
