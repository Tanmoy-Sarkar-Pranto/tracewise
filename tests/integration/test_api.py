import importlib
import sys

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


async def test_viewer_root_serves_selection_based_shell(viewer):
    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/")

    assert resp.status_code == 200
    assert 'id="detail-workspace"' in resp.text
    assert 'id="trace-tree"' in resp.text
    assert 'id="span-detail"' in resp.text


async def test_viewer_root_serves_mobile_trace_drawer_shell(viewer):
    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/")

    assert resp.status_code == 200
    assert 'id="detail-topbar"' in resp.text
    assert 'id="trace-drawer-toggle"' in resp.text
    assert 'id="drawer-backdrop"' in resp.text


async def test_duration_ms_in_trace_list(viewer, storage, make_span):
    root = make_span(trace_id="t1", span_id="r", name="GET /x")
    root.end_time = root.start_time + timedelta(milliseconds=120)
    root.status = SpanStatus.OK
    storage.save_span(root)

    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces")

    data = resp.json()
    assert abs(data[0]["root"]["duration_ms"] - 120) < 5


async def test_get_trace_preserves_db_metadata_for_viewer_detail(viewer, storage, make_span):
    root = make_span(trace_id="t1", span_id="root", name="GET /db-users")
    child = make_span(
        trace_id="t1",
        span_id="child",
        parent_span_id="root",
        name="SQL SELECT",
        kind=SpanKind.CLIENT,
    )
    root.end_time = utcnow()
    child.end_time = utcnow()
    child.attributes = {
        "db.operation": "SELECT",
        "db.statement": "SELECT id, name FROM demo_users ORDER BY id",
        "db.system": "sqlite",
    }
    storage.save_span(root)
    storage.save_span(child)

    async with AsyncClient(transport=ASGITransport(app=viewer), base_url="http://test") as client:
        resp = await client.get("/api/traces/t1")

    data = resp.json()
    db_child = data["root"]["children"][0]
    assert db_child["name"] == "SQL SELECT"
    assert db_child["attributes"]["db.operation"] == "SELECT"
    assert db_child["attributes"]["db.statement"].startswith("SELECT id, name")


async def test_testapp_db_users_routes_seed_and_trace_sqlalchemy(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    sys.modules.pop("tests.testapp.main", None)
    module = importlib.import_module("tests.testapp.main")

    try:
        async with AsyncClient(transport=ASGITransport(app=module.app), base_url="http://test") as client:
            response = await client.get("/db-users")
            assert response.status_code == 200
            assert response.json() == {
                "users": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                ]
            }

            response = await client.post("/db-users", json={"name": "Charlie"})
            assert response.status_code == 200
            assert response.json() == {"created": "Charlie"}

            response = await client.get("/db-users")
            assert response.status_code == 200
            assert response.json() == {
                "users": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                    {"id": 3, "name": "Charlie"},
                ]
            }

        storage = getattr(module.app.state, "_tracewise_storage")
        trace_ids = storage.list_traces(limit=10)

        get_trace_count = 0
        post_trace_count = 0
        for trace_id in trace_ids:
            spans = storage.get_trace(trace_id)
            request_span = next(
                span
                for span in spans
                if span.kind == SpanKind.SERVER and span.attributes.get("http.route") == "/db-users"
            )
            db_children = [
                span
                for span in spans
                if span.parent_span_id == request_span.span_id
                and span.kind == SpanKind.CLIENT
                and "db.statement" in span.attributes
            ]

            if request_span.name == "GET /db-users":
                get_trace_count += 1
                assert any(
                    child.name == "SQL SELECT"
                    and child.attributes["db.operation"] == "SELECT"
                    for child in db_children
                )

            if request_span.name == "POST /db-users":
                post_trace_count += 1
                insert_child = next(
                    child
                    for child in db_children
                    if child.name == "SQL INSERT"
                    and child.attributes["db.operation"] == "INSERT"
                )
                assert "Charlie" not in insert_child.attributes["db.statement"]

        assert get_trace_count == 2
        assert post_trace_count == 1
    finally:
        async_engine = getattr(module, "async_db_engine", None)
        if async_engine is not None:
            await async_engine.dispose()

        sync_engine = getattr(module, "sync_db_engine", None)
        if sync_engine is not None:
            sync_engine.dispose()
