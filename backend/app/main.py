from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import ensure_data_dirs, settings
from app.core.db import init_db
from app.services.ingest_service import ingest_service


def create_app() -> FastAPI:
    ensure_data_dirs()
    init_db()
    if settings.startup_index_catalog:
        ingest_service.ensure_catalog()

    app = FastAPI(title="Local Academic AI Assistant", version="1.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
