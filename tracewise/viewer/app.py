from fastapi import FastAPI
from tracewise.storage.base import BaseStorage


def create_viewer_app(storage: BaseStorage) -> FastAPI:
    app = FastAPI()
    return app
