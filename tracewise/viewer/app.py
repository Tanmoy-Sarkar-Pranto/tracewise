from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tracewise.storage.base import BaseStorage
from tracewise.viewer.api import create_router

_STATIC_DIR = Path(__file__).parent / "static"


def create_viewer_app(storage: BaseStorage) -> FastAPI:
    app = FastAPI(title="TraceWise Viewer", docs_url=None, redoc_url=None)
    app.include_router(create_router(storage))

    if _STATIC_DIR.exists() and any(_STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

    return app
