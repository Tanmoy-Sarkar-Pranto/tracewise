from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

import httpx

from tracewise.core.context import get_current_span, reset_span, set_current_span
from tracewise.core.models import Span, SpanKind, SpanStatus
from tracewise.instrumentation.middleware import _record_exception
from tracewise.storage.base import BaseStorage

_original_asyncclient_send = None
_should_trace_httpx: Callable[[], bool] = lambda: False
_get_storage: Callable[[], BaseStorage | None] = lambda: None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def install_async_httpx_instrumentation(
    *,
    should_trace_httpx: Callable[[], bool],
    get_storage: Callable[[], BaseStorage | None],
) -> None:
    global _original_asyncclient_send, _should_trace_httpx, _get_storage

    _should_trace_httpx = should_trace_httpx
    _get_storage = get_storage

    if _original_asyncclient_send is not None:
        return

    _original_asyncclient_send = httpx.AsyncClient.send

    async def _traced_send(client: httpx.AsyncClient, request: httpx.Request, *args, **kwargs):
        if not _should_trace_httpx():
            return await _original_asyncclient_send(client, request, *args, **kwargs)

        storage = _get_storage()
        if storage is None:
            return await _original_asyncclient_send(client, request, *args, **kwargs)

        parent = get_current_span()
        method = request.method.upper()
        host = request.url.host or "unknown"
        span = Span(
            trace_id=parent.trace_id if parent else uuid4().hex,
            span_id=uuid4().hex,
            parent_span_id=parent.span_id if parent else None,
            name=f"HTTP {method} {host}",
            kind=SpanKind.CLIENT,
            start_time=_utcnow(),
            end_time=None,
            status=SpanStatus.UNSET,
            attributes={
                "http.method": method,
                "http.url": str(request.url),
                "http.client_library": "httpx",
                "http.client_class": type(client).__name__,
            },
        )

        storage.save_span(span)
        token = set_current_span(span)
        try:
            response = await _original_asyncclient_send(client, request, *args, **kwargs)
            span.status = SpanStatus.OK
            span.attributes["http.status_code"] = response.status_code
            return response
        except Exception as exc:
            span.status = SpanStatus.ERROR
            span.attributes["error.message"] = str(exc)
            _record_exception(span, exc)
            raise
        finally:
            span.end_time = _utcnow()
            storage.update_span(span)
            reset_span(token)

    httpx.AsyncClient.send = _traced_send


def reset_async_httpx_instrumentation() -> None:
    global _original_asyncclient_send, _should_trace_httpx, _get_storage

    if _original_asyncclient_send is not None:
        httpx.AsyncClient.send = _original_asyncclient_send
        _original_asyncclient_send = None

    _should_trace_httpx = lambda: False
    _get_storage = lambda: None
