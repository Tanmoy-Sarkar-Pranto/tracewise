import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tracewise
from tracewise.core.models import SpanStatus


@pytest.fixture(autouse=True)
def reset_tracewise():
    yield
    tracewise._storage = None


def test_init_disabled_does_not_mount_viewer(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), enabled=False)
    paths = [str(getattr(r, "path", "")) for r in app.routes]
    assert not any("/tracewise" in p for p in paths)


def test_init_mounts_viewer_route(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"))
    paths = [str(getattr(r, "path", "")) for r in app.routes]
    assert any("tracewise" in p for p in paths)


async def test_init_wires_middleware_and_viewer(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"))

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/ping")
        resp = await client.get("/tracewise/api/traces")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["root"]["name"] == "GET /ping"


async def test_start_span_creates_child(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"))

    @app.get("/work")
    async def work():
        async with tracewise.start_span("inner.work"):
            pass
        return {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/work")
        resp = await client.get("/tracewise/api/traces")

    trace = resp.json()[0]
    children = trace["root"]["children"]
    assert len(children) == 1
    assert children[0]["name"] == "inner.work"


def test_get_current_span_returns_none_outside_request():
    assert tracewise.get_current_span() is None
