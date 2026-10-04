"""FastAPI application entrypoint for the onion grading backend and PWA client."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .api.router import api_router
from .db import engine, Base
from . import models  # noqa: F401

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgriGrade - Onion Grading API & PWA",
        description="FastAPI Backend for Automated AI Onion Grading System (Agmark standards compliant, Offline-first PWA)",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Configure CORS middleware
    if settings.CORS_ORIGINS:
        origins = (
            settings.CORS_ORIGINS
            if isinstance(settings.CORS_ORIGINS, list)
            else [str(settings.CORS_ORIGINS)]
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Mount static files for PWA (Service Worker, JS, CSS, Manifest)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Root PWA entrypoint
    @app.get("/", tags=["pwa"])
    def get_pwa_root():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {
            "name": "AgriGrade Onion Grading API",
            "version": "1.0.0",
            "status": "online",
            "docs": "/docs",
        }

    # Mount API routes
    app.include_router(api_router)

    # Initialize tables if SQLite
    Base.metadata.create_all(bind=engine)

    return app


app = create_app()
