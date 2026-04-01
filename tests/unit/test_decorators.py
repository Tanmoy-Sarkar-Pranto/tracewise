import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tracewise.core.models import SpanStatus
from tracewise.instrumentation import decorators
from tracewise.instrumentation.decorators import trace_span
from tracewise.instrumentation.middleware import TraceWiseMiddleware
from tracewise.storage.sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=tmp_path / "test.db")


@pytest.fixture
def app(storage):
    _app = FastAPI()
    _app.add_middleware(TraceWiseMiddleware, storage=storage)
    decorators._storage = storage
    yield _app, storage
    decorators._storage = None


async def test_decorator_creates_child_span(app):
    _app, storage = app

    @trace_span("my.operation")
    async def my_func():
        return "done"

    @_app.get("/test")
    async def route():
        await my_func()
        return {}

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
        await client.get("/test")

    spans = storage.get_trace(storage.list_traces()[0])
    assert len(spans) == 2
    child = next(s for s in spans if s.name == "my.operation")
    root = next(s for s in spans if s.parent_span_id is None)
    assert child.parent_span_id == root.span_id


async def test_decorator_with_static_attributes(app):
    _app, storage = app

    @trace_span("payment", attributes={"payment.type": "card"})
    async def process():
        pass

    @_app.get("/pay")
    async def route():
        await process()
        return {}

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
        await client.get("/pay")

    spans = storage.get_trace(storage.list_traces()[0])
    child = next(s for s in spans if s.name == "payment")
    assert child.attributes["payment.type"] == "card"


async def test_decorator_with_callable_attributes(app):
    _app, storage = app

    @trace_span("get.user", attributes=lambda user_id, **_: {"user.id": user_id})
    async def get_user(user_id: str):
        return user_id

    @_app.get("/user/{user_id}")
    async def route(user_id: str):
        await get_user(user_id)
        return {}

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
        await client.get("/user/abc-123")

    spans = storage.get_trace(storage.list_traces()[0])
    child = next(s for s in spans if s.name == "get.user")
    assert child.attributes["user.id"] == "abc-123"


async def test_decorator_marks_error_on_exception(app):
    _app, storage = app

    @trace_span("failing.op")
    async def fail():
        raise RuntimeError("something broke")

    @_app.get("/fail")
    async def route():
        try:
            await fail()
        except RuntimeError:
            pass
        return {}

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
        await client.get("/fail")

    spans = storage.get_trace(storage.list_traces()[0])
    child = next(s for s in spans if s.name == "failing.op")
    assert child.status == SpanStatus.ERROR
    assert "error.message" in child.attributes


async def test_decorator_span_is_closed(app):
    _app, storage = app

    @trace_span("quick.op")
    async def quick():
        pass

    @_app.get("/quick")
    async def route():
        await quick()
        return {}

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
        await client.get("/quick")

    spans = storage.get_trace(storage.list_traces()[0])
    child = next(s for s in spans if s.name == "quick.op")
    assert child.end_time is not None


async def test_decorator_async_records_exception_event(app):
    _app, storage = app

    @trace_span("async.fail")
    async def fail():
        raise ValueError("async error")

    @_app.get("/async-fail")
    async def route():
        try:
            await fail()
        except ValueError:
            pass
        return {}

    async with AsyncClient(transport=ASGITransport(app=_app), base_url="http://test") as client:
        await client.get("/async-fail")

    spans = storage.get_trace(storage.list_traces()[0])
    child = next(s for s in spans if s.name == "async.fail")
    assert len(child.events) == 1
    event = child.events[0]
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "ValueError"
    assert event.attributes["exception.message"] == "async error"
    assert "Traceback" in event.attributes["exception.stacktrace"]
    assert "ValueError" in event.attributes["exception.stacktrace"]


def test_decorator_sync_records_exception_event(tmp_path):
    from tracewise.instrumentation import decorators as _dec
    from tracewise.storage.sqlite import SQLiteStorage as _S
    _storage = _S(db_path=tmp_path / "sync_test.db")
    _dec._storage = _storage

    try:
        @trace_span("sync.fail")
        def fail():
            raise TypeError("sync error")

        try:
            fail()
        except TypeError:
            pass

        spans = _storage.get_trace(_storage.list_traces()[0])
        child = next(s for s in spans if s.name == "sync.fail")
        assert len(child.events) == 1
        event = child.events[0]
        assert event.name == "exception"
        assert event.attributes["exception.type"] == "TypeError"
        assert event.attributes["exception.message"] == "sync error"
        assert "Traceback" in event.attributes["exception.stacktrace"]
        assert "TypeError" in event.attributes["exception.stacktrace"]
    finally:
        _dec._storage = None
