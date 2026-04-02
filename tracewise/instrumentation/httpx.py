from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from functools import wraps
from typing import Any

import httpx

from tracewise.core.context import get_current_span, reset_span, set_current_span
from tracewise.core.ids import generate_span_id, generate_trace_id
from tracewise.core.models import Span, SpanKind, SpanStatus
from tracewise.instrumentation.middleware import _record_exception
from tracewise.storage.base import BaseStorage

_original_asyncclient_send = None
_original_client_send = None
_should_trace_httpx: Callable[[], bool] = lambda: False
_get_storage: Callable[[], BaseStorage | None] = lambda: None
_TRACEPARENT_VERSION = "00"
_TRACEPARENT_FLAGS = "01"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_client_span(request: httpx.Request, client_class: str) -> Span:
    parent = get_current_span()
    method = request.method.upper()
    host = request.url.host or "unknown"
    return Span(
        trace_id=parent.trace_id if parent else generate_trace_id(),
        span_id=generate_span_id(),
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
            "http.client_class": client_class,
        },
    )


def _build_traceparent(span: Span) -> str:
    return f"{_TRACEPARENT_VERSION}-{span.trace_id}-{span.span_id}-{_TRACEPARENT_FLAGS}"


def _inject_traceparent_if_missing(request: httpx.Request, span: Span) -> None:
    # Preserve caller-supplied propagation exactly; wire-level traceparent may
    # intentionally differ from this locally recorded CLIENT span context.
    if "traceparent" in request.headers:
        return
    request.headers["traceparent"] = _build_traceparent(span)


def _begin_client_span(
    request: httpx.Request,
    client_class: str,
) -> tuple[BaseStorage | None, Span | None, object | None]:
    if not _should_trace_httpx():
        return None, None, None

    storage = _get_storage()
    if storage is None:
        return None, None, None

    span = _build_client_span(request, client_class)
    storage.save_span(span)
    token = set_current_span(span)
    return storage, span, token


def _mark_client_span_success(span: Span, response: httpx.Response) -> None:
    span.status = SpanStatus.OK
    span.attributes["http.status_code"] = response.status_code


def _mark_client_span_error(span: Span, exc: Exception) -> None:
    span.status = SpanStatus.ERROR
    span.attributes["error.message"] = str(exc)
    _record_exception(span, exc)


def _finish_client_span(storage: BaseStorage, span: Span, token: object) -> None:
    span.end_time = _utcnow()
    storage.update_span(span)
    reset_span(token)


def install_httpx_instrumentation(
    *,
    should_trace_httpx: Callable[[], bool],
    get_storage: Callable[[], BaseStorage | None],
) -> None:
    global _original_asyncclient_send, _original_client_send, _should_trace_httpx, _get_storage

    _should_trace_httpx = should_trace_httpx
    _get_storage = get_storage

    if _original_asyncclient_send is None:
        original_async_send = httpx.AsyncClient.send
        _original_asyncclient_send = original_async_send

        @wraps(original_async_send)
        async def _traced_async_send(
            client: httpx.AsyncClient,
            request: httpx.Request,
            *args: Any,
            **kwargs: Any,
        ) -> httpx.Response:
            storage, span, token = _begin_client_span(request, "AsyncClient")
            if storage is None or span is None or token is None:
                return await original_async_send(client, request, *args, **kwargs)

            _inject_traceparent_if_missing(request, span)

            try:
                response = await original_async_send(client, request, *args, **kwargs)
                _mark_client_span_success(span, response)
                return response
            except Exception as exc:
                _mark_client_span_error(span, exc)
                raise
            finally:
                _finish_client_span(storage, span, token)

        httpx.AsyncClient.send = _traced_async_send

    if _original_client_send is None:
        original_client_send = httpx.Client.send
        _original_client_send = original_client_send

        @wraps(original_client_send)
        def _traced_client_send(
            client: httpx.Client,
            request: httpx.Request,
            *args: Any,
            **kwargs: Any,
        ) -> httpx.Response:
            storage, span, token = _begin_client_span(request, "Client")
            if storage is None or span is None or token is None:
                return original_client_send(client, request, *args, **kwargs)

            _inject_traceparent_if_missing(request, span)

            try:
                response = original_client_send(client, request, *args, **kwargs)
                _mark_client_span_success(span, response)
                return response
            except Exception as exc:
                _mark_client_span_error(span, exc)
                raise
            finally:
                _finish_client_span(storage, span, token)

        httpx.Client.send = _traced_client_send


def install_async_httpx_instrumentation(
    *,
    should_trace_httpx: Callable[[], bool],
    get_storage: Callable[[], BaseStorage | None],
) -> None:
    install_httpx_instrumentation(
        should_trace_httpx=should_trace_httpx,
        get_storage=get_storage,
    )


def reset_httpx_instrumentation() -> None:
    global _original_asyncclient_send, _original_client_send, _should_trace_httpx, _get_storage

    if _original_asyncclient_send is not None:
        httpx.AsyncClient.send = _original_asyncclient_send
        _original_asyncclient_send = None

    if _original_client_send is not None:
        httpx.Client.send = _original_client_send
        _original_client_send = None

    _should_trace_httpx = lambda: False
    _get_storage = lambda: None


def reset_async_httpx_instrumentation() -> None:
    reset_httpx_instrumentation()
