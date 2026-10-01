"""Reads/writes Gemini and LinkedIn credentials. Precedence: a credential saved through the UI
always overrides one found in an environment variable; removing the UI value reveals the
environment configuration again, if present. A Settings response never includes the secret value
itself — only whether one is configured, its source, and a masked display hint.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.models.db import GeminiCredential, LinkedInCredential, NvidiaCredential
from app.security.secrets import decrypt, encrypt, mask

ENV_GEMINI_KEY = "GEMINI_API_KEY"
ENV_NVIDIA_KEY = "NVIDIA_API_KEY"
ENV_LINKEDIN_CLIENT_ID = "LINKEDIN_CLIENT_ID"
ENV_LINKEDIN_CLIENT_SECRET = "LINKEDIN_CLIENT_SECRET"


class CredentialStatus:
    def __init__(self, configured: bool, source: str | None, masked: str | None, extra: dict | None = None):
        self.configured = configured
        self.source = source  # "ui" | "env" | None
        self.masked = masked
        self.extra = extra or {}


def _row(db: Session) -> GeminiCredential:
    row = db.get(GeminiCredential, 1)
    if row is None:
        row = GeminiCredential(id=1)
        db.add(row)
        db.flush()
    return row


def gemini_status(db: Session) -> CredentialStatus:
    row = _row(db)
    if row.encrypted_api_key:
        return CredentialStatus(True, "ui", f"••••{row.last_four}" if row.last_four else "••••", {"model": row.model})
    if os.environ.get(ENV_GEMINI_KEY):
        return CredentialStatus(True, "env", "configured on server", {"model": row.model})
    return CredentialStatus(False, None, None, {"model": row.model})


def get_gemini_api_key(db: Session) -> str | None:
    row = _row(db)
    if row.encrypted_api_key:
        return decrypt(row.encrypted_api_key)
    return os.environ.get(ENV_GEMINI_KEY)


def set_gemini_api_key(db: Session, api_key: str) -> None:
    row = _row(db)
    row.encrypted_api_key = encrypt(api_key)
    row.last_four = api_key[-4:] if len(api_key) >= 4 else "****"
    row.source = "ui"
    row.last_test_ok = None
    row.last_test_message = None
    db.commit()


def remove_gemini_api_key(db: Session) -> None:
    row = _row(db)
    row.encrypted_api_key = None
    row.last_four = None
    row.last_test_ok = None
    row.last_test_message = None
    db.commit()


def set_gemini_model(db: Session, model: str) -> None:
    row = _row(db)
    row.model = model
    db.commit()


def get_gemini_model(db: Session) -> str:
    return _row(db).model


def record_gemini_test(db: Session, ok: bool, message: str) -> None:
    row = _row(db)
    row.last_test_ok = ok
    row.last_test_message = mask(message) if not ok and len(message) > 200 else message
    from app.models.db import utcnow

    row.last_test_at = utcnow()
    db.commit()


# ---------------------------------------------------------------- NVIDIA NIM


def _nvidia_row(db: Session) -> NvidiaCredential:
    row = db.get(NvidiaCredential, 1)
    if row is None:
        row = NvidiaCredential(id=1)
        db.add(row)
        db.flush()
    return row


def nvidia_status(db: Session) -> CredentialStatus:
    row = _nvidia_row(db)
    if row.encrypted_api_key:
        return CredentialStatus(True, "ui", f"••••{row.last_four}" if row.last_four else "••••", {"model": row.model})
    if os.environ.get(ENV_NVIDIA_KEY):
        return CredentialStatus(True, "env", "configured on server", {"model": row.model})
    return CredentialStatus(False, None, None, {"model": row.model})


def get_nvidia_api_key(db: Session) -> str | None:
    row = _nvidia_row(db)
    if row.encrypted_api_key:
        return decrypt(row.encrypted_api_key)
    return os.environ.get(ENV_NVIDIA_KEY)


def set_nvidia_api_key(db: Session, api_key: str) -> None:
    row = _nvidia_row(db)
    row.encrypted_api_key = encrypt(api_key)
    row.last_four = api_key[-4:] if len(api_key) >= 4 else "****"
    row.source = "ui"
    row.last_test_ok = None
    row.last_test_message = None
    db.commit()


def remove_nvidia_api_key(db: Session) -> None:
    row = _nvidia_row(db)
    row.encrypted_api_key = None
    row.last_four = None
    row.last_test_ok = None
    row.last_test_message = None
    db.commit()


def set_nvidia_model(db: Session, model: str) -> None:
    row = _nvidia_row(db)
    row.model = model
    db.commit()


def get_nvidia_model(db: Session) -> str:
    return _nvidia_row(db).model


def record_nvidia_test(db: Session, ok: bool, message: str) -> None:
    row = _nvidia_row(db)
    row.last_test_ok = ok
    row.last_test_message = mask(message) if not ok and len(message) > 200 else message
    from app.models.db import utcnow

    row.last_test_at = utcnow()
    db.commit()


# ---------------------------------------------------------------- LinkedIn


def _li_row(db: Session) -> LinkedInCredential:
    row = db.get(LinkedInCredential, 1)
    if row is None:
        row = LinkedInCredential(id=1)
        db.add(row)
        db.flush()
    return row


def linkedin_app_status(db: Session) -> CredentialStatus:
    row = _li_row(db)
    if row.client_id and row.encrypted_client_secret:
        return CredentialStatus(True, "ui", f"client_id ••••{row.client_id[-4:]}")
    if os.environ.get(ENV_LINKEDIN_CLIENT_ID) and os.environ.get(ENV_LINKEDIN_CLIENT_SECRET):
        return CredentialStatus(True, "env", "configured on server")
    return CredentialStatus(False, None, None)


def get_linkedin_app_credentials(db: Session) -> tuple[str | None, str | None]:
    row = _li_row(db)
    if row.client_id and row.encrypted_client_secret:
        return row.client_id, decrypt(row.encrypted_client_secret)
    return os.environ.get(ENV_LINKEDIN_CLIENT_ID), os.environ.get(ENV_LINKEDIN_CLIENT_SECRET)


def set_linkedin_app_credentials(db: Session, client_id: str, client_secret: str) -> None:
    row = _li_row(db)
    row.client_id = client_id
    row.encrypted_client_secret = encrypt(client_secret)
    row.source = "ui"
    db.commit()


def remove_linkedin_app_credentials(db: Session) -> None:
    row = _li_row(db)
    row.client_id = None
    row.encrypted_client_secret = None
    row.encrypted_access_token = None
    row.encrypted_refresh_token = None
    row.token_expires_at = None
    row.connected_account_name = None
    row.connected_account_urn = None
    db.commit()


def linkedin_connection_status(db: Session) -> dict:
    row = _li_row(db)
    if not row.encrypted_access_token:
        return {"connected": False}
    from app.models.db import utcnow

    expired = bool(row.token_expires_at and row.token_expires_at <= utcnow())
    return {
        "connected": True,
        "account_name": row.connected_account_name,
        "expired": expired,
        "expires_at": row.token_expires_at.isoformat() if row.token_expires_at else None,
    }


def save_linkedin_tokens(db: Session, access_token: str, refresh_token: str | None, expires_at, account_name: str, account_urn: str) -> None:
    row = _li_row(db)
    row.encrypted_access_token = encrypt(access_token)
    row.encrypted_refresh_token = encrypt(refresh_token) if refresh_token else None
    row.token_expires_at = expires_at
    row.connected_account_name = account_name
    row.connected_account_urn = account_urn
    db.commit()


def get_linkedin_access_token(db: Session) -> str | None:
    row = _li_row(db)
    if not row.encrypted_access_token:
        return None
    return decrypt(row.encrypted_access_token)


def disconnect_linkedin(db: Session) -> None:
    row = _li_row(db)
    row.encrypted_access_token = None
    row.encrypted_refresh_token = None
    row.token_expires_at = None
    row.connected_account_name = None
    row.connected_account_urn = None
    db.commit()
