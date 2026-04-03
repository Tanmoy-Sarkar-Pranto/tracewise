import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tracewise.core.models import SpanStatus
from tracewise.instrumentation.middleware import TraceWiseMiddleware
from tracewise.storage.sqlite import SQLiteStorage

VALID_TRACEPARENT = "00-11111111111111111111111111111111-2222222222222222-01"
VALID_TRACEPARENT_FLAGS_00 = "00-11111111111111111111111111111111-2222222222222222-00"
UNSUPPORTED_TRACEPARENT = "01-11111111111111111111111111111111-2222222222222222-01"


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=tmp_path / "test.db")


@pytest.fixture
def app(storage):
    _app = FastAPI()
    _app.add_middleware(TraceWiseMiddleware, storage=storage)

    @_app.get("/hello")
    async def hello():
        return {"msg": "hello"}

    @_app.post("/inspect")
    async def inspect():
        return {"ok": True}

    @_app.get("/users/{user_id}")
    async def get_user(user_id: str):
        return {"user_id": user_id}

    @_app.get("/error")
    async def error():
        raise ValueError("boom")

    return _app


async def test_middleware_creates_root_span(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/hello")
    assert resp.status_code == 200
    traces = storage.list_traces()
    assert len(traces) == 1
    spans = storage.get_trace(traces[0])
    assert len(spans) == 1
    assert spans[0].name == "GET /hello"


async def test_root_span_has_no_parent(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello")
    spans = storage.get_trace(storage.list_traces()[0])
    assert spans[0].parent_span_id is None


async def test_span_is_closed_after_request(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello")
    spans = storage.get_trace(storage.list_traces()[0])
    assert spans[0].end_time is not None
    assert spans[0].status == SpanStatus.OK


async def test_error_span_status(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with pytest.raises(Exception):
            await client.get("/error")
    spans = storage.get_trace(storage.list_traces()[0])
    assert spans[0].status == SpanStatus.ERROR
    assert "error.message" in spans[0].attributes


async def test_separate_requests_have_separate_trace_ids(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello")
        await client.get("/hello")
    traces = storage.list_traces(limit=10)
    assert len(traces) == 2


async def test_error_span_has_exception_event(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with pytest.raises(Exception):
            await client.get("/error")
    spans = storage.get_trace(storage.list_traces()[0])
    span = spans[0]
    assert len(span.events) == 1
    event = span.events[0]
    assert event.name == "exception"
    assert event.attributes["exception.type"] == "ValueError"
    assert event.attributes["exception.message"] == "boom"
    assert "Traceback" in event.attributes["exception.stacktrace"]
    assert "ValueError" in event.attributes["exception.stacktrace"]


async def test_request_metadata_is_captured(app, storage):
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.10", 50000)),
        base_url="http://test",
    ) as client:
        await client.post(
            "/inspect?foo=bar&page=2",
            content=b"{}",
            headers={
                "User-Agent": "pytest-agent",
                "Content-Type": "application/json",
            },
        )

    span = storage.get_trace(storage.list_traces()[0])[0]
    assert span.attributes["http.query_string"] == "foo=bar&page=2"
    assert span.attributes["http.client_ip"] == "203.0.113.10"
    assert span.attributes["http.user_agent"] == "pytest-agent"
    assert span.attributes["http.request_content_type"] == "application/json"


async def test_missing_request_metadata_is_omitted(app, storage):
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("203.0.113.11", 50001)),
        base_url="http://test",
    ) as client:
        await client.get("/hello")

    span = storage.get_trace(storage.list_traces()[0])[0]
    assert "http.query_string" not in span.attributes
    assert "http.request_content_type" not in span.attributes
    assert span.attributes["http.client_ip"] == "203.0.113.11"


async def test_response_content_length_is_captured(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/hello")

    span = storage.get_trace(storage.list_traces()[0])[0]
    assert span.attributes["http.response_content_length"] == resp.headers["content-length"]


async def test_route_template_is_captured(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/users/abc-123")

    span = storage.get_trace(storage.list_traces()[0])[0]
    assert span.attributes["http.route"] == "/users/{user_id}"


async def test_middleware_adopts_valid_inbound_traceparent(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello", headers={"traceparent": VALID_TRACEPARENT})

    traces = storage.list_traces()
    assert traces == ["11111111111111111111111111111111"]

    span = storage.get_trace(traces[0])[0]
    assert span.trace_id == "11111111111111111111111111111111"
    assert span.parent_span_id == "2222222222222222"
    assert span.span_id != "2222222222222222"
    assert span.name == "GET /hello"


async def test_middleware_accepts_valid_inbound_traceparent_with_flags_00(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello", headers={"traceparent": VALID_TRACEPARENT_FLAGS_00})

    span = storage.get_trace(storage.list_traces()[0])[0]
    assert span.trace_id == "11111111111111111111111111111111"
    assert span.parent_span_id == "2222222222222222"


async def test_middleware_ignores_malformed_traceparent(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello", headers={"traceparent": "not-a-valid-traceparent"})

    traces = storage.list_traces()
    assert traces != ["11111111111111111111111111111111"]
    span = storage.get_trace(storage.list_traces()[0])[0]
    assert span.parent_span_id is None


async def test_middleware_ignores_unsupported_traceparent_version(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello", headers={"traceparent": UNSUPPORTED_TRACEPARENT})

    traces = storage.list_traces()
    assert traces != ["11111111111111111111111111111111"]
    span = storage.get_trace(storage.list_traces()[0])[0]
    assert span.parent_span_id is None


async def test_middleware_generates_fresh_request_span_ids_for_same_inbound_traceparent(app, storage):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/hello", headers={"traceparent": VALID_TRACEPARENT})
        await client.get("/hello", headers={"traceparent": VALID_TRACEPARENT})

    traces = storage.list_traces()
    assert traces == ["11111111111111111111111111111111"]

    spans = storage.get_trace(traces[0])
    assert len(spans) == 2
    assert spans[0].trace_id == "11111111111111111111111111111111"
    assert spans[1].trace_id == "11111111111111111111111111111111"
    assert spans[0].span_id != spans[1].span_id
    assert spans[0].parent_span_id == "2222222222222222"
    assert spans[1].parent_span_id == "2222222222222222"
