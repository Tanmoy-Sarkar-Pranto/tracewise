from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from tracewise.core.context import reset_span, set_current_span
from tracewise.core.models import Span, SpanKind, SpanStatus
from tracewise.storage.base import BaseStorage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TraceWiseMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, storage: BaseStorage, **kwargs):
        super().__init__(app, **kwargs)
        self._storage = storage

    async def dispatch(self, request: Request, call_next) -> Response:
        span = Span(
            trace_id=uuid4().hex,
            span_id=uuid4().hex,
            parent_span_id=None,
            name=f"{request.method} {request.url.path}",
            kind=SpanKind.SERVER,
            start_time=_utcnow(),
            end_time=None,
            status=SpanStatus.UNSET,
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
            },
        )
        token = set_current_span(span)
        self._storage.save_span(span)
        try:
            response = await call_next(request)
            span.status = SpanStatus.OK
            span.attributes["http.status_code"] = response.status_code
            return response
        except Exception as exc:
            span.status = SpanStatus.ERROR
            span.attributes["error.message"] = str(exc)
            raise
        finally:
            span.end_time = _utcnow()
            self._storage.update_span(span)
            reset_span(token)
