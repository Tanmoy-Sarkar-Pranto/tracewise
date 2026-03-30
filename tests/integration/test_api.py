import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tracewise.core.models import SpanKind, SpanStatus
from tracewise.storage.sqlite import SQLiteStorage
from tracewise.viewer.app import create_viewer_app


def utcnow():
    return datetime.now(timezone.utc)


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=tmp_path / "viewer.db")


@pytest.fixture
def viewer(storage):
    return create_viewer_app(storage=storage)


async def test_list_traces_empty(viewer):
    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_traces_returns_root_span_name(viewer, storage, make_span):
    root = make_span(trace_id="t1", span_id="root", name="GET /users", status=SpanStatus.OK)
    root.end_time = utcnow()
    storage.save_span(root)

    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces")

    data = resp.json()
    assert len(data) == 1
    assert data[0]["trace_id"] == "t1"
    assert data[0]["root"]["name"] == "GET /users"
    assert data[0]["root"]["status"] == "OK"


async def test_get_trace_returns_span_tree(viewer, storage, make_span):
    root = make_span(trace_id="t1", span_id="root", name="GET /users")
    child = make_span(trace_id="t1", span_id="child", parent_span_id="root", name="db.query")
    root.end_time = utcnow()
    child.end_time = utcnow()
    storage.save_span(root)
    storage.save_span(child)

    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces/t1")

    data = resp.json()
    assert data["trace_id"] == "t1"
    assert data["root"]["span_id"] == "root"
    assert len(data["root"]["children"]) == 1
    assert data["root"]["children"][0]["span_id"] == "child"
    assert data["root"]["children"][0]["name"] == "db.query"


async def test_get_trace_nested_children(viewer, storage, make_span):
    root = make_span(trace_id="t1", span_id="r", name="root")
    child = make_span(trace_id="t1", span_id="c", parent_span_id="r", name="child")
    grandchild = make_span(trace_id="t1", span_id="gc", parent_span_id="c", name="grandchild")
    for s in [root, child, grandchild]:
        s.end_time = utcnow()
        storage.save_span(s)

    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces/t1")

    data = resp.json()
    assert data["root"]["children"][0]["children"][0]["name"] == "grandchild"


async def test_get_trace_404_for_unknown(viewer):
    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces/nonexistent")
    assert resp.status_code == 404


async def test_delete_traces_clears_all(viewer, storage, make_span):
    storage.save_span(make_span(trace_id="t1", span_id="s1"))
    storage.save_span(make_span(trace_id="t2", span_id="s2"))

    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.delete("/api/traces")

    assert resp.status_code == 200
    assert storage.list_traces() == []


async def test_duration_ms_in_trace_list(viewer, storage, make_span):
    root = make_span(trace_id="t1", span_id="r", name="GET /x")
    root.end_time = root.start_time + timedelta(milliseconds=120)
    root.status = SpanStatus.OK
    storage.save_span(root)

    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces")

    data = resp.json()
    assert abs(data[0]["root"]["duration_ms"] - 120) < 5
