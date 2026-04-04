import builtins
import logging

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import tracewise
from tracewise.core.models import SpanStatus
from tracewise.instrumentation import decorators as _decorators
from tracewise.instrumentation.logging import TraceWiseLogHandler
from tracewise.instrumentation.middleware import TraceWiseMiddleware


@pytest.fixture(autouse=True)
def reset_tracewise():
    yield
    tracewise._storage = None


def test_init_disabled_does_not_mount_viewer(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), enabled=False)
    paths = [str(getattr(r, "path", "")) for r in app.routes]
    assert not any("/tracewise" in p for p in paths)


async def test_init_disabled_after_enable_stops_tracing_same_app(tmp_path):
    app = FastAPI()
    db_path = str(tmp_path / "t.db")
    tracewise.init(app, db_path=db_path)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/ping")

    storage = getattr(app.state, "_tracewise_storage")
    assert len(storage.list_traces()) == 1

    tracewise.init(app, db_path=db_path, enabled=False)

    middleware = [m for m in app.user_middleware if m.cls is TraceWiseMiddleware]
    mounts = [r for r in app.routes if getattr(r, "path", None) == "/tracewise"]

    assert tracewise._storage is None
    assert _decorators._storage is None
    assert len(middleware) == 0
    assert len(mounts) == 0

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/ping")

    assert len(storage.list_traces()) == 1


async def test_init_can_reenable_after_disable_on_same_app(tmp_path):
    app = FastAPI()
    db_path = str(tmp_path / "t.db")
    tracewise.init(app, db_path=db_path)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/ping")

    storage = getattr(app.state, "_tracewise_storage")
    assert len(storage.list_traces()) == 1

    tracewise.init(app, db_path=db_path, enabled=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/ping")

    assert len(storage.list_traces()) == 1

    tracewise.init(app, db_path=db_path)

    middleware = [m for m in app.user_middleware if m.cls is TraceWiseMiddleware]
    mounts = [r for r in app.routes if getattr(r, "path", None) == "/tracewise"]

    assert len(middleware) == 1
    assert len(mounts) == 1

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/ping")

    assert len(storage.list_traces()) == 2


def test_init_disabled_clears_state_and_unpatches_httpx(tmp_path):
    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send
    app = FastAPI()
    tracewise.init(
        app,
        db_path=str(tmp_path / "enabled.db"),
        instrument_httpx=True,
    )
    assert tracewise._storage is not None
    assert _decorators._storage is tracewise._storage
    assert tracewise._httpx_instrumentation_enabled is True
    assert httpx.AsyncClient.send is not original_async_send
    assert httpx.Client.send is not original_sync_send

    disabled_app = FastAPI()
    tracewise.init(disabled_app, db_path=str(tmp_path / "disabled.db"), enabled=False)

    assert tracewise._storage is None
    assert _decorators._storage is None
    assert tracewise._httpx_instrumentation_enabled is False
    assert httpx.AsyncClient.send is original_async_send
    assert httpx.Client.send is original_sync_send


def test_init_opt_out_after_opt_in_unpatches_httpx(tmp_path):
    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send

    first_app = FastAPI()
    tracewise.init(
        first_app,
        db_path=str(tmp_path / "first.db"),
        instrument_httpx=True,
    )
    assert httpx.AsyncClient.send is not original_async_send
    assert httpx.Client.send is not original_sync_send
    assert tracewise._httpx_instrumentation_enabled is True

    second_app = FastAPI()
    tracewise.init(
        second_app,
        db_path=str(tmp_path / "second.db"),
        instrument_httpx=False,
    )
    assert tracewise._httpx_instrumentation_enabled is False
    assert httpx.AsyncClient.send is original_async_send
    assert httpx.Client.send is original_sync_send


def test_init_mounts_viewer_route(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"))
    paths = [str(getattr(r, "path", "")) for r in app.routes]
    assert any("tracewise" in p for p in paths)


def test_init_is_idempotent_for_same_app(tmp_path):
    app = FastAPI()

    tracewise.init(app, db_path=str(tmp_path / "t.db"))
    tracewise.init(app, db_path=str(tmp_path / "t.db"))

    middleware = [m for m in app.user_middleware if m.cls is TraceWiseMiddleware]
    mounts = [r for r in app.routes if getattr(r, "path", None) == "/tracewise"]

    assert len(middleware) == 1
    assert len(mounts) == 1


def test_init_capture_logs_is_idempotent(tmp_path):
    app = FastAPI()

    tracewise.init(app, db_path=str(tmp_path / "t.db"), capture_logs=True)
    tracewise.init(app, db_path=str(tmp_path / "t.db"), capture_logs=True)

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, TraceWiseLogHandler)]

    assert len(handlers) == 1

    for handler in handlers:
        logging.getLogger().removeHandler(handler)


def test_init_does_not_require_httpx_when_httpx_instrumentation_disabled(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tracewise.instrumentation.httpx":
            raise ModuleNotFoundError("No module named 'httpx'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), instrument_httpx=False)

    paths = [str(getattr(r, "path", "")) for r in app.routes]
    assert any("tracewise" in p for p in paths)


def test_init_does_not_require_sqlalchemy_when_sqlalchemy_instrumentation_disabled(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tracewise.instrumentation.sqlalchemy":
            raise ModuleNotFoundError("No module named 'sqlalchemy'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), instrument_sqlalchemy=False)

    paths = [str(getattr(r, "path", "")) for r in app.routes]
    assert any("tracewise" in p for p in paths)


def test_init_sqlalchemy_opt_in_installs_engine_listeners(tmp_path):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from tracewise.instrumentation import sqlalchemy as tracewise_sqlalchemy

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), instrument_sqlalchemy=True)

    assert tracewise._sqlalchemy_instrumentation_enabled is True
    assert event.contains(Engine, "before_cursor_execute", tracewise_sqlalchemy._before_cursor_execute)
    assert event.contains(Engine, "after_cursor_execute", tracewise_sqlalchemy._after_cursor_execute)
    assert event.contains(Engine, "handle_error", tracewise_sqlalchemy._handle_error)


def test_init_opt_out_after_sqlalchemy_opt_in_removes_engine_listeners(tmp_path):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from tracewise.instrumentation import sqlalchemy as tracewise_sqlalchemy

    first_app = FastAPI()
    tracewise.init(first_app, db_path=str(tmp_path / "first.db"), instrument_sqlalchemy=True)

    second_app = FastAPI()
    tracewise.init(second_app, db_path=str(tmp_path / "second.db"), instrument_sqlalchemy=False)

    assert tracewise._sqlalchemy_instrumentation_enabled is False
    assert not event.contains(Engine, "before_cursor_execute", tracewise_sqlalchemy._before_cursor_execute)
    assert not event.contains(Engine, "after_cursor_execute", tracewise_sqlalchemy._after_cursor_execute)
    assert not event.contains(Engine, "handle_error", tracewise_sqlalchemy._handle_error)


def test_init_disabled_clears_state_and_unpatches_sqlalchemy(tmp_path):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from tracewise.instrumentation import sqlalchemy as tracewise_sqlalchemy

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "enabled.db"), instrument_sqlalchemy=True)

    assert tracewise._sqlalchemy_instrumentation_enabled is True
    assert event.contains(Engine, "before_cursor_execute", tracewise_sqlalchemy._before_cursor_execute)

    disabled_app = FastAPI()
    tracewise.init(disabled_app, db_path=str(tmp_path / "disabled.db"), enabled=False)

    assert tracewise._sqlalchemy_instrumentation_enabled is False
    assert not event.contains(Engine, "before_cursor_execute", tracewise_sqlalchemy._before_cursor_execute)
    assert not event.contains(Engine, "after_cursor_execute", tracewise_sqlalchemy._after_cursor_execute)
    assert not event.contains(Engine, "handle_error", tracewise_sqlalchemy._handle_error)


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


def test_init_disabled_after_enable_removes_log_handler(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"), capture_logs=True)

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, TraceWiseLogHandler)]
    assert len(handlers) == 1

    tracewise.init(app, db_path=str(tmp_path / "t.db"), enabled=False)

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, TraceWiseLogHandler)]
    assert len(handlers) == 0


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


async def test_start_span_records_exception_event(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "t.db"))

    @app.get("/risky")
    async def risky():
        try:
            async with tracewise.start_span("risky.op"):
                raise RuntimeError("fail inside context")
        except RuntimeError:
            pass
        return {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/risky")

    storage = tracewise._storage
    all_spans = storage.get_trace(storage.list_traces()[0])
    span = next(s for s in all_spans if s.name == "risky.op")
    assert len(span.events) == 1
    event = span.events[0]
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "RuntimeError"
    assert event.attributes["exception.message"] == "fail inside context"
    assert "Traceback" in event.attributes["exception.stacktrace"]
    assert "RuntimeError" in event.attributes["exception.stacktrace"]
