import pytest

from tracewise.core.traceparent import TraceParent, parse_traceparent


def test_parse_traceparent_accepts_valid_version_00():
    value = "00-11111111111111111111111111111111-2222222222222222-01"

    assert parse_traceparent(value) == TraceParent(
        version="00",
        trace_id="11111111111111111111111111111111",
        parent_id="2222222222222222",
        trace_flags="01",
    )


def test_parse_traceparent_accepts_non_01_trace_flags():
    value = "00-11111111111111111111111111111111-2222222222222222-00"

    parsed = parse_traceparent(value)
    assert parsed is not None
    assert parsed.trace_flags == "00"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "not-a-valid-traceparent",
        "01-11111111111111111111111111111111-2222222222222222-01",
        "00-00000000000000000000000000000000-2222222222222222-01",
        "00-11111111111111111111111111111111-0000000000000000-01",
        "00-11111111111111111111111111111111-2222222222222222",
        "00-11111111111111111111111111111111-2222222222222222-01-extra",
        "00-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA-2222222222222222-01",
    ],
)
def test_parse_traceparent_rejects_invalid_values(value):
    assert parse_traceparent(value) is None
