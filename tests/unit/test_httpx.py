import httpx
import pytest
from fastapi import FastAPI

import tracewise
from tracewise.core.models import SpanKind, SpanStatus
from tracewise.instrumentation import httpx as tracewise_httpx


def test_httpx_patch_is_not_installed_when_opted_out(tmp_path):
    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send
    app = FastAPI()

    tracewise.init(app, db_path=str(tmp_path / "opt_out_unpatched.db"), instrument_httpx=False)

    assert httpx.AsyncClient.send is original_async_send
    assert httpx.Client.send is original_sync_send


async def test_httpx_instrumentation_is_opt_in(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "opt_in.db"))

    async with tracewise.start_span("parent.work"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="http://upstream",
        ) as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    assert len(spans) == 1
    assert spans[0].name == "parent.work"
    assert spans[0].kind != SpanKind.CLIENT


async def test_async_httpx_creates_child_client_span(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "async_child.db"), instrument_httpx=True)

    async with tracewise.start_span("parent.work"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="http://upstream",
        ) as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    parent = next(span for span in spans if span.name == "parent.work")
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)

    assert child.parent_span_id == parent.span_id
    assert child.name == "HTTP GET upstream"
    assert child.status == SpanStatus.OK
    assert child.attributes["http.method"] == "GET"
    assert child.attributes["http.url"] == "http://upstream/ping"
    assert child.attributes["http.status_code"] == 200
    assert child.attributes["http.client_library"] == "httpx"
    assert child.attributes["http.client_class"] == "AsyncClient"


async def test_async_httpx_without_parent_creates_root_client_trace(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "async_root.db"), instrument_httpx=True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream),
        base_url="http://api.example.test",
    ) as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)

    assert len(spans) == 1
    span = spans[0]
    assert span.parent_span_id is None
    assert span.kind == SpanKind.CLIENT
    assert span.name == "HTTP GET api.example.test"
    assert span.attributes["http.client_class"] == "AsyncClient"


async def test_sync_httpx_creates_child_client_span(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "sync_child.db"), instrument_httpx=True)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(204, request=request)
    )

    async with tracewise.start_span("parent.work") as parent:
        with httpx.Client(
            transport=transport,
            base_url="https://sync.example.test",
        ) as client:
            response = client.get("/health")

    assert response.status_code == 204
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)

    assert child.parent_span_id == parent.span_id
    assert child.name == "HTTP GET sync.example.test"
    assert child.status == SpanStatus.OK
    assert child.attributes["http.method"] == "GET"
    assert child.attributes["http.url"] == "https://sync.example.test/health"
    assert child.attributes["http.status_code"] == 204
    assert child.attributes["http.client_class"] == "Client"


def test_sync_httpx_creates_root_client_span(tmp_path):
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "sync_root.db"), instrument_httpx=True)

    transport = httpx.MockTransport(
        lambda request: httpx.Response(204, request=request)
    )

    with httpx.Client(
        transport=transport,
        base_url="https://sync.example.test",
    ) as client:
        response = client.get("/health")

    assert response.status_code == 204
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)

    assert len(spans) == 1
    span = spans[0]
    assert span.parent_span_id is None
    assert span.kind == SpanKind.CLIENT
    assert span.name == "HTTP GET sync.example.test"
    assert span.status == SpanStatus.OK
    assert span.attributes["http.url"] == "https://sync.example.test/health"
    assert span.attributes["http.status_code"] == 204
    assert span.attributes["http.client_class"] == "Client"


async def test_async_httpx_error_records_exception_and_restores_parent(tmp_path):
    upstream = FastAPI()

    @upstream.get("/boom")
    async def boom():
        raise RuntimeError("upstream boom")

    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "async_error.db"), instrument_httpx=True)

    async with tracewise.start_span("parent.work") as parent:
        with pytest.raises(RuntimeError, match="upstream boom"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=upstream),
                base_url="http://upstream",
            ) as client:
                await client.get("/boom")

        assert tracewise.get_current_span() is parent

    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    child = next(span for span in spans if span.kind == SpanKind.CLIENT)

    assert child.status == SpanStatus.ERROR
    assert child.attributes["error.message"] == "upstream boom"
    assert child.end_time is not None
    assert len(child.events) == 1
    assert child.events[0].name == "exception"
    assert child.events[0].attributes["exception.type"] == "RuntimeError"
    assert child.events[0].attributes["exception.message"] == "upstream boom"


async def test_httpx_instrumentation_is_idempotent(tmp_path):
    upstream = FastAPI()

    @upstream.get("/ping")
    async def ping():
        return {"ok": True}

    app1 = FastAPI()
    tracewise.init(app1, db_path=str(tmp_path / "idempotent.db"), instrument_httpx=True)

    app2 = FastAPI()
    tracewise.init(app2, db_path=str(tmp_path / "idempotent.db"), instrument_httpx=True)

    async with tracewise.start_span("parent.work"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upstream),
            base_url="http://upstream",
        ) as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    trace_id = tracewise._storage.list_traces()[0]
    spans = tracewise._storage.get_trace(trace_id)
    client_spans = [span for span in spans if span.kind == SpanKind.CLIENT]
    assert len(client_spans) == 1


def test_httpx_reset_unpatches_client_and_asyncclient_send(tmp_path):
    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send
    app = FastAPI()
    tracewise.init(app, db_path=str(tmp_path / "patched_then_reset.db"), instrument_httpx=True)

    assert httpx.AsyncClient.send is not original_async_send
    assert httpx.Client.send is not original_sync_send
    tracewise_httpx.reset_httpx_instrumentation()
    assert httpx.AsyncClient.send is original_async_send
    assert httpx.Client.send is original_sync_send
