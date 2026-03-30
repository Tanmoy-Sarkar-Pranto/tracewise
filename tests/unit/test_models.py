from datetime import datetime, timezone
from tracewise.core.models import Span, SpanEvent, SpanKind, SpanStatus
from tests.conftest import utcnow


def test_span_defaults():
    span = Span(
        trace_id="abc123",
        span_id="def456",
        parent_span_id=None,
        name="GET /users",
        kind=SpanKind.SERVER,
        start_time=utcnow(),
        end_time=None,
        status=SpanStatus.UNSET,
    )
    assert span.trace_id == "abc123"
    assert span.parent_span_id is None
    assert span.end_time is None
    assert span.status == SpanStatus.UNSET
    assert span.attributes == {}
    assert span.events == []
    assert span._meta == {}


def test_span_with_attributes():
    span = Span(
        trace_id="t1",
        span_id="s1",
        parent_span_id=None,
        name="db.query",
        kind=SpanKind.INTERNAL,
        start_time=utcnow(),
        end_time=utcnow(),
        status=SpanStatus.OK,
        attributes={"db.statement": "SELECT * FROM users"},
    )
    assert span.attributes["db.statement"] == "SELECT * FROM users"


def test_span_event():
    event = SpanEvent(name="cache.miss", timestamp=utcnow())
    assert event.name == "cache.miss"
    assert event.attributes == {}


def test_span_kind_values():
    assert SpanKind.SERVER == "SERVER"
    assert SpanKind.CLIENT == "CLIENT"
    assert SpanKind.INTERNAL == "INTERNAL"
    assert SpanKind.PRODUCER == "PRODUCER"
    assert SpanKind.CONSUMER == "CONSUMER"


def test_span_status_values():
    assert SpanStatus.OK == "OK"
    assert SpanStatus.ERROR == "ERROR"
    assert SpanStatus.UNSET == "UNSET"


def test_span_mutable_defaults_are_independent():
    span_a = Span(
        trace_id="t1", span_id="s1", parent_span_id=None,
        name="a", kind=SpanKind.INTERNAL,
        start_time=utcnow(), end_time=None, status=SpanStatus.UNSET,
    )
    span_b = Span(
        trace_id="t2", span_id="s2", parent_span_id=None,
        name="b", kind=SpanKind.INTERNAL,
        start_time=utcnow(), end_time=None, status=SpanStatus.UNSET,
    )
    span_a.attributes["key"] = "val"
    assert "key" not in span_b.attributes
