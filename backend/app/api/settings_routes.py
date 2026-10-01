"""Settings endpoints. Per the spec: a Settings response exposes status, never the stored secret
value itself; a newly typed (unsaved) key can be revealed client-side, but a saved one is never sent
back from the server.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.schemas import (
    BrandSettingsRequest,
    GeminiKeyRequest,
    GeminiModelRequest,
    LinkedInAppRequest,
    NvidiaKeyRequest,
    NvidiaModelRequest,
)
from app.config import settings as env_settings
from app.models.db import get_db_session
from app.security.auth import get_current_owner
from app.services import app_settings
from app.services import credentials as cred_service
from app.services.gemini_client import DEFAULT_MODEL, SUPPORTED_MODELS, GeminiClient
from app.services.nvidia_client import DEFAULT_MODEL as NVIDIA_DEFAULT_MODEL
from app.services.nvidia_client import SUPPORTED_MODELS as NVIDIA_SUPPORTED_MODELS
from app.services.nvidia_client import NvidiaClient
from app.services.ollama_client import DEFAULT_BASE_URL as OLLAMA_DEFAULT_BASE_URL
from app.services.ollama_client import DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL
from app.services.ollama_client import SUPPORTED_MODELS as OLLAMA_SUPPORTED_MODELS
from app.services.ollama_client import OllamaClient

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_owner)])


# ---------------------------------------------------------------- Gemini


@router.get("/gemini")
def gemini_status(db: Session = Depends(get_db_session)) -> dict:
    s = cred_service.gemini_status(db)
    return {"configured": s.configured, "source": s.source, "masked": s.masked, "model": s.extra.get("model"), "supported_models": SUPPORTED_MODELS}


@router.put("/gemini")
def save_gemini_key(body: GeminiKeyRequest, db: Session = Depends(get_db_session)) -> dict:
    cred_service.set_gemini_api_key(db, body.api_key.strip())
    return {"status": "Key configured"}


@router.delete("/gemini")
def remove_gemini_key(db: Session = Depends(get_db_session)) -> dict:
    cred_service.remove_gemini_api_key(db)
    return {"status": "removed"}


@router.put("/gemini/model")
def save_gemini_model(body: GeminiModelRequest, db: Session = Depends(get_db_session)) -> dict:
    if body.model not in SUPPORTED_MODELS:
        raise HTTPException(422, f"unsupported model; choose one of {SUPPORTED_MODELS}")
    cred_service.set_gemini_model(db, body.model)
    return {"model": body.model}


@router.post("/gemini/test")
async def test_gemini(db: Session = Depends(get_db_session)) -> dict:
    api_key = cred_service.get_gemini_api_key(db)
    if not api_key:
        raise HTTPException(422, "No Gemini API key configured yet.")
    model = cred_service.get_gemini_model(db) or DEFAULT_MODEL
    client = GeminiClient(api_key=api_key, model=model)
    ok, message = await client.test_connection()
    cred_service.record_gemini_test(db, ok, message)
    return {"ok": ok, "message": message}


# ---------------------------------------------------------------- LLM provider (Gemini / local Ollama / NVIDIA NIM)


@router.get("/llm")
def llm_status(db: Session = Depends(get_db_session)) -> dict:
    prefs = app_settings.get_all(db)
    return {
        "provider": prefs.get("llm_provider", "gemini"),
        "ollama_model": prefs.get("ollama_model") or OLLAMA_DEFAULT_MODEL,
        "ollama_base_url": prefs.get("ollama_base_url") or OLLAMA_DEFAULT_BASE_URL,
        "ollama_supported_models": OLLAMA_SUPPORTED_MODELS,
    }


@router.post("/ollama/test")
async def test_ollama(db: Session = Depends(get_db_session)) -> dict:
    prefs = app_settings.get_all(db)
    client = OllamaClient(base_url=prefs.get("ollama_base_url") or OLLAMA_DEFAULT_BASE_URL, model=prefs.get("ollama_model") or OLLAMA_DEFAULT_MODEL)
    ok, message = await client.test_connection()
    return {"ok": ok, "message": message}


# ---------------------------------------------------------------- NVIDIA NIM


@router.get("/nvidia")
def nvidia_status(db: Session = Depends(get_db_session)) -> dict:
    s = cred_service.nvidia_status(db)
    return {"configured": s.configured, "source": s.source, "masked": s.masked, "model": s.extra.get("model"), "supported_models": NVIDIA_SUPPORTED_MODELS}


@router.put("/nvidia")
def save_nvidia_key(body: NvidiaKeyRequest, db: Session = Depends(get_db_session)) -> dict:
    cred_service.set_nvidia_api_key(db, body.api_key.strip())
    return {"status": "Key configured"}


@router.delete("/nvidia")
def remove_nvidia_key(db: Session = Depends(get_db_session)) -> dict:
    cred_service.remove_nvidia_api_key(db)
    return {"status": "removed"}


@router.put("/nvidia/model")
def save_nvidia_model(body: NvidiaModelRequest, db: Session = Depends(get_db_session)) -> dict:
    cred_service.set_nvidia_model(db, body.model)
    return {"model": body.model}


@router.post("/nvidia/test")
async def test_nvidia(db: Session = Depends(get_db_session)) -> dict:
    api_key = cred_service.get_nvidia_api_key(db)
    if not api_key:
        raise HTTPException(422, "No NVIDIA API key configured yet.")
    model = cred_service.get_nvidia_model(db) or NVIDIA_DEFAULT_MODEL
    client = NvidiaClient(api_key=api_key, model=model)
    ok, message = await client.test_connection()
    cred_service.record_nvidia_test(db, ok, message)
    return {"ok": ok, "message": message}


# ---------------------------------------------------------------- LinkedIn app + connection


def _redirect_uri(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}{env_settings.linkedin_redirect_path}"


@router.get("/linkedin")
def linkedin_status(request: Request, db: Session = Depends(get_db_session)) -> dict:
    app_status = cred_service.linkedin_app_status(db)
    conn = cred_service.linkedin_connection_status(db)
    return {"app_configured": app_status.configured, "app_source": app_status.source, "app_masked": app_status.masked, "redirect_uri": _redirect_uri(request), "connection": conn}


@router.put("/linkedin")
def save_linkedin_app(body: LinkedInAppRequest, db: Session = Depends(get_db_session)) -> dict:
    cred_service.set_linkedin_app_credentials(db, body.client_id.strip(), body.client_secret.strip())
    return {"status": "saved"}


@router.delete("/linkedin")
def remove_linkedin_app(db: Session = Depends(get_db_session)) -> dict:
    cred_service.remove_linkedin_app_credentials(db)
    return {"status": "removed"}


@router.post("/linkedin/disconnect")
def disconnect_linkedin(db: Session = Depends(get_db_session)) -> dict:
    cred_service.disconnect_linkedin(db)
    return {"status": "disconnected"}


# ---------------------------------------------------------------- brand / preferences


@router.get("/brand")
def get_brand(db: Session = Depends(get_db_session)) -> dict:
    return app_settings.get_all(db)


@router.put("/brand")
def save_brand(body: BrandSettingsRequest, db: Session = Depends(get_db_session)) -> dict:
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    app_settings.set_many(db, values)
    return app_settings.get_all(db)
