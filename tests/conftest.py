import pytest
from datetime import datetime, timezone
from tracewise.core.models import Span, SpanKind, SpanStatus
import tracewise
from tracewise.instrumentation import decorators as _decorators
from tracewise.instrumentation import httpx as _httpx_instrumentation


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def make_span():
    """Factory fixture. Call make_span(trace_id=..., span_id=...) in tests."""
    def _make(
        trace_id: str = "trace-1",
        span_id: str = "span-1",
        parent_span_id: str | None = None,
        name: str = "GET /test",
        kind: SpanKind = SpanKind.SERVER,
        status: SpanStatus = SpanStatus.UNSET,
        end_time: datetime | None = None,
        start_time: datetime | None = None,
        **attributes,
    ) -> Span:
        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            start_time=start_time or utcnow(),
            end_time=end_time,
            status=status,
            attributes=dict(attributes),
        )
    return _make


@pytest.fixture(autouse=True)
def reset_tracewise_private_state():
    yield
    tracewise._storage = None
    tracewise._httpx_instrumentation_enabled = False
    _decorators._storage = None
    _httpx_instrumentation.reset_async_httpx_instrumentation()
