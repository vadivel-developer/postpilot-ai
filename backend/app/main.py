from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, channels, drafts, linkedin_oauth, settings_routes
from app.config import settings
from app.models.db import init_db

logging.basicConfig(level=settings.log_level.upper())
log = logging.getLogger("ltp.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if settings.host not in ("127.0.0.1", "localhost"):
        log.warning(
            "LTP_HOST=%s: the API is not bound to localhost. Make sure HTTPS, an owner account, and a real "
            "encryption key (LTP_ENCRYPTION_KEY) are all in place before exposing this — see docs/DEPLOYMENT.md.",
            settings.host,
        )
    yield


app = FastAPI(title="LearnToPost AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(drafts.router)
app.include_router(settings_routes.router)
app.include_router(linkedin_oauth.router)
