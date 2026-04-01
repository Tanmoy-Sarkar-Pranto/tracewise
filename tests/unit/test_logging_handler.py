import logging
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from tracewise.core.context import reset_span, set_current_span
from tracewise.core.models import Span, SpanKind, SpanStatus
from tracewise.instrumentation.logging import TraceWiseLogHandler


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


@pytest.fixture
def logger_with_handler():
    """Returns (logger, handler) pair; removes handler after test."""
    handler = TraceWiseLogHandler()
    log = logging.getLogger(f"test.tracewise.{uuid4().hex}")
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    log.propagate = False
    yield log, handler
    log.removeHandler(handler)


def test_log_attaches_event_to_active_span(active_span, logger_with_handler):
    log, _ = logger_with_handler
    log.warning("something happened")
    assert len(active_span.events) == 1
    assert active_span.events[0].name == "log.WARNING"
    assert active_span.events[0].attributes["log.message"] == "something happened"


def test_log_event_captures_level(active_span, logger_with_handler):
    log, _ = logger_with_handler
    log.error("db failed")
    assert active_span.events[0].attributes["log.level"] == "ERROR"


def test_log_event_captures_logger_name(active_span, logger_with_handler):
    log, _ = logger_with_handler
    log.info("hello")
    assert active_span.events[0].attributes["log.logger"] == log.name


def test_log_event_timestamp_is_utc(active_span, logger_with_handler):
    log, _ = logger_with_handler
    log.warning("tick")
    ts = active_span.events[0].timestamp
    assert ts.tzinfo is not None


def test_log_noop_when_no_active_span(logger_with_handler):
    log, _ = logger_with_handler
    log.warning("nobody home")  # no span in context — must not raise


def test_multiple_logs_produce_multiple_events(active_span, logger_with_handler):
    log, _ = logger_with_handler
    log.info("first")
    log.warning("second")
    log.error("third")
    assert len(active_span.events) == 3
    assert active_span.events[0].name == "log.INFO"
    assert active_span.events[1].name == "log.WARNING"
    assert active_span.events[2].name == "log.ERROR"


def test_handler_level_filter(active_span):
    handler = TraceWiseLogHandler(level=logging.ERROR)
    log = logging.getLogger(f"test.level.{uuid4().hex}")
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    log.propagate = False

    log.warning("filtered out")   # WARNING < ERROR
    log.error("passes through")   # ERROR >= ERROR

    log.removeHandler(handler)

    assert len(active_span.events) == 1
    assert active_span.events[0].attributes["log.level"] == "ERROR"


def test_log_message_with_format_args(active_span, logger_with_handler):
    log, _ = logger_with_handler
    log.warning("user %s logged in", "alice")
    assert active_span.events[0].attributes["log.message"] == "user alice logged in"
