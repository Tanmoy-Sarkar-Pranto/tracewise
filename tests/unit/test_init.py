import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tracewise
from tracewise.core.models import SpanStatus
from tracewise.instrumentation.logging import TraceWiseLogHandler


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


def test_capture_logs_false_by_default(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"))
    handlers = [h for h in logging.getLogger().handlers
                if isinstance(h, TraceWiseLogHandler)]
    assert len(handlers) == 0


def test_capture_logs_true_attaches_handler(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), capture_logs=True)
    handlers = [h for h in logging.getLogger().handlers
                if isinstance(h, TraceWiseLogHandler)]
    assert len(handlers) == 1
    assert handlers[0].level == logging.NOTSET
    # cleanup
    for h in handlers:
        logging.getLogger().removeHandler(h)


def test_capture_logs_with_level(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), capture_logs=logging.WARNING)
    handlers = [h for h in logging.getLogger().handlers
                if isinstance(h, TraceWiseLogHandler)]
    assert len(handlers) == 1
    assert handlers[0].level == logging.WARNING
    for h in handlers:
        logging.getLogger().removeHandler(h)


async def test_capture_logs_end_to_end(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), capture_logs=True)

    @app.get("/work")
    async def work():
        logging.getLogger("myapp").warning("processing started")
        return {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/work")
        resp = await client.get("/tracewise/api/traces")

    # cleanup handler before assertions (so it doesn't affect other tests)
    for h in [h for h in logging.getLogger().handlers if isinstance(h, TraceWiseLogHandler)]:
        logging.getLogger().removeHandler(h)

    data = resp.json()
    assert len(data) == 1
    root_events = data[0]["root"]["events"]
    assert len(root_events) == 1
    assert root_events[0]["name"] == "log.WARNING"
    assert root_events[0]["attributes"]["log.message"] == "processing started"
    assert root_events[0]["attributes"]["log.logger"] == "myapp"
