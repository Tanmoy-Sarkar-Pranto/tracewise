from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SpanKind(str, Enum):
    SERVER = "SERVER"
    CLIENT = "CLIENT"
    INTERNAL = "INTERNAL"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


class SpanStatus(str, Enum):
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


@dataclass
class SpanEvent:
    name: str
    timestamp: datetime
    attributes: dict = field(default_factory=dict)


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: SpanKind
    start_time: datetime
    end_time: datetime | None
    status: SpanStatus
    attributes: dict = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    _meta: dict = field(default_factory=dict)
