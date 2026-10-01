"""Owner authentication: a single local account, bootstrapped once, protecting the whole API.

Password hashing: PBKDF2-HMAC-SHA256 via the standard library (no extra dependency). Sessions are
signed (not just base64) cookies via itsdangerous, so a client cannot forge or tamper with one
without the server's session secret.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets as pysecrets

from fastapi import Cookie, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session as DbSession

from app.config import INSTANCE_DIR, settings
from app.models.db import Owner

_PBKDF2_ITERATIONS = 390_000
_SESSION_SECRET_FILE = INSTANCE_DIR / "session.key"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations_s, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations_s))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def _resolve_session_secret() -> str:
    """Same requirement as the credential encryption key: a value that survives process restarts,
    so an existing signed session cookie keeps working. A freshly random secret on every startup
    (the previous behaviour) silently logged out every signed-in owner on each backend restart."""
    if settings.session_secret:
        return settings.session_secret
    if _SESSION_SECRET_FILE.exists():
        return _SESSION_SECRET_FILE.read_text().strip()
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    secret = pysecrets.token_urlsafe(32)
    _SESSION_SECRET_FILE.write_text(secret)
    return secret


_session_secret = _resolve_session_secret()
_serializer = URLSafeTimedSerializer(_session_secret, salt="ltp-session")


def create_session_token(owner_id: int) -> str:
    return _serializer.dumps({"owner_id": owner_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age_seconds)
        return int(data["owner_id"])
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None


def get_current_owner(
    request: Request,
    ltp_session: str | None = Cookie(default=None),
) -> Owner:
    from app.models.db import (
        get_db_session,  # local import to avoid a cycle at module load
    )

    token = ltp_session
    if not token:
        raise HTTPException(status_code=401, detail="not signed in")
    owner_id = read_session_token(token)
    if owner_id is None:
        raise HTTPException(status_code=401, detail="session expired or invalid")
    db: DbSession = next(get_db_session())
    owner = db.get(Owner, owner_id)
    if owner is None:
        raise HTTPException(status_code=401, detail="account no longer exists")
    request.state.owner = owner
    return owner
