from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import wraps
from typing import Callable
from uuid import uuid4

from tracewise.core.context import get_current_span, reset_span, set_current_span
from tracewise.core.models import Span, SpanKind, SpanStatus
from tracewise.instrumentation.middleware import _record_exception

# Set by tracewise.init()
_storage = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def trace_span(name: str, attributes: dict | Callable | None = None):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if _storage is None:
                return await func(*args, **kwargs)
            parent = get_current_span()
            if callable(attributes):
                resolved_attrs = attributes(*args, **kwargs)
            elif attributes:
                resolved_attrs = dict(attributes)
            else:
                resolved_attrs = {}
            span = Span(
                trace_id=parent.trace_id if parent else uuid4().hex,
                span_id=uuid4().hex,
                parent_span_id=parent.span_id if parent else None,
                name=name,
                kind=SpanKind.INTERNAL,
                start_time=_utcnow(),
                end_time=None,
                status=SpanStatus.UNSET,
                attributes=resolved_attrs,
            )
            _storage.save_span(span)
            token = set_current_span(span)
            try:
                result = await func(*args, **kwargs)
                span.status = SpanStatus.OK
                return result
            except Exception as exc:
                span.status = SpanStatus.ERROR
                span.attributes["error.message"] = str(exc)
                _record_exception(span, exc)
                raise
            finally:
                span.end_time = _utcnow()
                _storage.update_span(span)
                reset_span(token)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if _storage is None:
                return func(*args, **kwargs)
            parent = get_current_span()
            if callable(attributes):
                resolved_attrs = attributes(*args, **kwargs)
            elif attributes:
                resolved_attrs = dict(attributes)
            else:
                resolved_attrs = {}
            span = Span(
                trace_id=parent.trace_id if parent else uuid4().hex,
                span_id=uuid4().hex,
                parent_span_id=parent.span_id if parent else None,
                name=name,
                kind=SpanKind.INTERNAL,
                start_time=_utcnow(),
                end_time=None,
                status=SpanStatus.UNSET,
                attributes=resolved_attrs,
            )
            _storage.save_span(span)
            token = set_current_span(span)
            try:
                result = func(*args, **kwargs)
                span.status = SpanStatus.OK
                return result
            except Exception as exc:
                span.status = SpanStatus.ERROR
                span.attributes["error.message"] = str(exc)
                _record_exception(span, exc)
                raise
            finally:
                span.end_time = _utcnow()
                _storage.update_span(span)
                reset_span(token)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
