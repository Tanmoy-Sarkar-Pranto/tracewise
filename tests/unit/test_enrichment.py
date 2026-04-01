import pytest
from datetime import datetime, timezone
from uuid import uuid4

import tracewise
from tracewise.core.context import reset_span, set_current_span
from tracewise.core.models import Span, SpanKind, SpanStatus


@pytest.fixture
def active_span():
    span = Span(
        trace_id=uuid4().hex,
        span_id=uuid4().hex,
        parent_span_id=None,
        name="GET /test",
        kind=SpanKind.SERVER,
        start_time=datetime.now(timezone.utc),
        end_time=None,
        status=SpanStatus.UNSET,
    )
    token = set_current_span(span)
    yield span
    reset_span(token)


def test_set_attribute_adds_to_current_span(active_span):
    tracewise.set_attribute("user.id", "abc-123")
    assert active_span.attributes["user.id"] == "abc-123"


def test_set_attribute_overwrites_existing(active_span):
    tracewise.set_attribute("user.id", "old")
    tracewise.set_attribute("user.id", "new")
    assert active_span.attributes["user.id"] == "new"


def test_set_attribute_noop_when_no_span():
    # No span in context — must not raise
    tracewise.set_attribute("key", "val")


def test_set_attributes_bulk(active_span):
    tracewise.set_attributes({"a": 1, "b": "two", "c": True})
    assert active_span.attributes["a"] == 1
    assert active_span.attributes["b"] == "two"
    assert active_span.attributes["c"] is True


def test_set_attributes_noop_when_no_span():
    tracewise.set_attributes({"key": "val"})


def test_add_event_appends_to_current_span(active_span):
    tracewise.add_event("cache.miss", key="users:123")
    assert len(active_span.events) == 1
    assert active_span.events[0].name == "cache.miss"
    assert active_span.events[0].attributes["key"] == "users:123"


def test_add_event_timestamp_is_utc(active_span):
    tracewise.add_event("tick")
    ts = active_span.events[0].timestamp
    assert ts.tzinfo is not None


def test_add_event_multiple_events_ordered(active_span):
    tracewise.add_event("first")
    tracewise.add_event("second")
    assert active_span.events[0].name == "first"
    assert active_span.events[1].name == "second"


def test_add_event_noop_when_no_span():
    tracewise.add_event("something")
