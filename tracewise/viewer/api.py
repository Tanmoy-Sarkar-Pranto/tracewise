from __future__ import annotations

from fastapi import APIRouter, HTTPException
from tracewise.storage.base import BaseStorage


def _build_span_node(span, all_spans: list) -> dict:
    children = [
        _build_span_node(s, all_spans)
        for s in all_spans
        if s.parent_span_id == span.span_id
    ]
    duration_ms = None
    if span.end_time and span.start_time:
        duration_ms = (span.end_time - span.start_time).total_seconds() * 1000

    return {
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "kind": span.kind.value,
        "status": span.status.value,
        "start_time": span.start_time.isoformat() if span.start_time else None,
        "end_time": span.end_time.isoformat() if span.end_time else None,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "attributes": span.attributes,
        "events": [
            {
                "name": e.name,
                "timestamp": e.timestamp.isoformat(),
                "attributes": e.attributes,
            }
            for e in span.events
        ],
        "children": children,
    }


def create_router(storage: BaseStorage) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/traces")
    def list_traces(limit: int = 50):
        trace_ids = storage.list_traces(limit=limit)
        result = []
        for trace_id in trace_ids:
            spans = storage.get_trace(trace_id)
            if not spans:
                continue
            root = next((s for s in spans if s.parent_span_id is None), spans[0])
            result.append({
                "trace_id": trace_id,
                "root": _build_span_node(root, spans),
            })
        return result

    @router.get("/traces/{trace_id}")
    def get_trace(trace_id: str):
        spans = storage.get_trace(trace_id)
        if not spans:
            raise HTTPException(status_code=404, detail="Trace not found")
        root = next((s for s in spans if s.parent_span_id is None), spans[0])
        return {
            "trace_id": trace_id,
            "root": _build_span_node(root, spans),
        }

    @router.delete("/traces")
    def clear_traces():
        storage.clear()
        return {"deleted": True}

    return router
