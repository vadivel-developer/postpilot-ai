"""Application configuration. Routine settings come from environment variables / .env; per-account
secrets (Gemini API key, LinkedIn client secret) are entered through the Settings UI at runtime and
stored encrypted in the database, never in a config file. See app/security/secrets.py.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent  # learn-to-post-ai/
BACKEND_ROOT = ROOT / "backend"
INSTANCE_DIR = BACKEND_ROOT / "instance"  # local, git-ignored: db file, fallback encryption key, images
IMAGES_DIR = INSTANCE_DIR / "images"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LTP_", env_file=str(ROOT / ".env"), extra="ignore")

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    # A public app must set this to its real origin; local dev defaults to same-origin.
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # Session / auth
    session_secret: str = ""  # if unset, a random one is generated at startup and sessions won't
    # survive a restart; set LTP_SESSION_SECRET for persistent login across restarts.
    session_cookie_name: str = "ltp_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14

    # Encryption for stored provider credentials (Gemini key, LinkedIn client secret, tokens).
    # If unset, a machine-local key is generated and stored via the OS credential store (Windows
    # Credential Locker) or, if unavailable, a git-ignored local key file — see security/secrets.py.
    # Never falls back to storing credentials unencrypted.
    encryption_key: str = ""

    # Database
    database_url: str = f"sqlite:///{(INSTANCE_DIR / 'app.db').as_posix()}"

    # Worker
    worker_poll_interval_seconds: float = 2.0
    job_lease_seconds: int = 120
    job_max_attempts: int = 3

    # LinkedIn OAuth (client id/secret are entered via Settings UI, not here; this is only the
    # fixed, non-secret redirect path the developer app must register).
    linkedin_redirect_path: str = "/api/linkedin/oauth/callback"
    linkedin_scopes: str = "openid profile w_member_social"

    # Demo mode never calls a real external API even if credentials are configured.
    demo_mode: bool = False

    # Default preferences (overridable in Settings UI, persisted in AppSetting table thereafter)
    default_timezone: str = "Asia/Kolkata"
    default_output_language: str = "English"


def get_settings() -> Settings:
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()


settings = get_settings()
