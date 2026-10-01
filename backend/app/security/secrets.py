"""Encryption for provider credentials (Gemini API key, LinkedIn client secret, LinkedIn tokens).

Key management, in order of preference:
  1. LTP_ENCRYPTION_KEY environment variable (deployment: inject from a real secret manager).
  2. The OS credential store (Windows Credential Locker, via `keyring`) for local development.
  3. A local key file under backend/instance/ (git-ignored) as a last-resort fallback, with a loud
     warning — this is weaker than an OS store and unsuitable for a shared or production host.

Whatever the key source, credentials are ALWAYS encrypted before they touch the database. There is
no code path that stores a provider secret in plaintext.
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from app.config import INSTANCE_DIR, settings

log = logging.getLogger("ltp.security")

_KEYRING_SERVICE = "learn-to-post-ai"
_KEYRING_USER = "encryption-key"
_FALLBACK_KEY_FILE = INSTANCE_DIR / "encryption.key"

_fernet: Fernet | None = None
_key_source: str = "unknown"


def _load_or_create_key() -> tuple[bytes, str]:
    if settings.encryption_key:
        return settings.encryption_key.encode(), "environment variable (LTP_ENCRYPTION_KEY)"

    try:
        import keyring

        existing = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
        if existing:
            return existing.encode(), "OS credential store (keyring)"
        new_key = Fernet.generate_key()
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, new_key.decode())
        log.info("generated a new encryption key and stored it in the OS credential store")
        return new_key, "OS credential store (keyring)"
    except Exception as exc:  # keyring backend unavailable, locked, headless CI, etc.
        log.warning("OS credential store unavailable (%s); falling back to a local key file. "
                    "This is fine for local development only — set LTP_ENCRYPTION_KEY for anything "
                    "shared or deployed.", exc)

    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    if _FALLBACK_KEY_FILE.exists():
        return _FALLBACK_KEY_FILE.read_bytes().strip(), "local key file (fallback)"
    new_key = Fernet.generate_key()
    _FALLBACK_KEY_FILE.write_bytes(new_key)
    try:
        os.chmod(_FALLBACK_KEY_FILE, 0o600)
    except OSError:
        pass  # best-effort on Windows
    return new_key, "local key file (fallback, newly generated)"


def _get_fernet() -> Fernet:
    global _fernet, _key_source
    if _fernet is None:
        key, source = _load_or_create_key()
        _fernet = Fernet(key)
        _key_source = source
        log.info("credential encryption key source: %s", source)
    return _fernet


def key_source() -> str:
    _get_fernet()
    return _key_source


def encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("stored credential could not be decrypted (wrong or rotated key)") from exc


def mask(secret: str, keep: int = 4) -> str:
    """For UI display only — never send the real secret to the frontend."""
    if len(secret) <= keep:
        return "•" * len(secret)
    return "•" * (len(secret) - keep) + secret[-keep:]
