import pytest
from datetime import datetime, timezone
from tracewise.core.models import Span, SpanKind, SpanStatus


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
