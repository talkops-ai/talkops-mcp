"""Tests for the response size truncation utility."""

import json
from loki_mcp_server.utils.response_size import enforce_structured_size_limit


def test_small_response_passes_through():
    """Test that a response under the limit is not modified."""
    data = {
        "result_type": "streams",
        "result": [
            {"stream": {"app": "foo"}, "entries": [{"ts": "1", "line": "hello"}]},
            {"stream": {"app": "bar"}, "entries": [{"ts": "2", "line": "world"}]},
        ]
    }

    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=1000)
    assert len(result["result"]) == 2
    assert "truncated" not in result


def test_large_response_truncated():
    """Test that a large response is truncated to fit under the limit."""
    data = {
        "result_type": "streams",
        "result": [
            {"stream": {"app": f"svc-{i}"}, "entries": [{"ts": str(j), "line": f"log line {i}-{j} " * 20} for j in range(5)]}
            for i in range(50)
        ]
    }

    def serializer(obj):
        return json.dumps(obj).encode("utf-8")

    result = enforce_structured_size_limit(
        data,
        truncatable_key="result",
        max_bytes=2000,
        serializer=serializer
    )

    assert 0 < len(result["result"]) < 50
    assert result["truncated"] is True
    assert result["truncated_at"] == len(result["result"])
    assert result["total_count"] == 50
    assert "_truncation_advice" in result
    assert len(serializer(result)) <= 2000


def test_truncation_advice_contains_logql_guidance():
    """Test that truncation advice includes actionable LogQL suggestions."""
    data = {
        "result_type": "streams",
        "result": [
            {"stream": {"app": f"svc-{i}"}, "entries": [{"ts": "1", "line": "x" * 200}]}
            for i in range(50)
        ]
    }

    def serializer(obj):
        return json.dumps(obj).encode("utf-8")

    result = enforce_structured_size_limit(
        data,
        truncatable_key="result",
        max_bytes=2000,
        serializer=serializer,
        query_hint='rate({app="checkout"}[5m])',
    )

    assert result["truncated"] is True
    advice = result["_truncation_advice"]
    assert "truncated" in advice.lower()
    # Should include rate-specific advice
    assert "topk" in advice


def test_truncation_advice_generic_for_non_rate():
    """Test that non-rate queries get generic advice."""
    data = {
        "result_type": "streams",
        "result": [
            {"stream": {"app": f"svc-{i}"}, "entries": [{"ts": "1", "line": "x" * 200}]}
            for i in range(50)
        ]
    }

    def serializer(obj):
        return json.dumps(obj).encode("utf-8")

    result = enforce_structured_size_limit(
        data,
        truncatable_key="result",
        max_bytes=2000,
        serializer=serializer,
        query_hint='{app="checkout"}',
    )

    assert result["truncated"] is True
    advice = result["_truncation_advice"]
    assert "label filters" in advice
    assert "topk" not in advice


def test_missing_truncatable_key():
    """Test that missing key safely returns unchanged."""
    data = {"result_type": "streams", "other_key": [1, 2, 3]}
    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=10)
    assert result == data


def test_empty_array_handled():
    """Test that empty array is handled safely."""
    data = {"result_type": "streams", "result": []}
    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=10)
    assert result == data


def test_not_an_array_handled():
    """Test that non-array is handled safely."""
    data = {"result_type": "streams", "result": "not an array"}
    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=10)
    assert result == data


def test_series_key_truncation():
    """Test truncation works with 'series' key (for metric query responses)."""
    data = {
        "result_type": "matrix",
        "series": [
            {"metric": {"app": f"svc-{i}"}, "values": [[1000 + j, str(j)] for j in range(20)]}
            for i in range(50)
        ],
        "total_series": 50,
        "truncated_series": False,
        "warnings": [],
    }

    def serializer(obj):
        return json.dumps(obj).encode("utf-8")

    result = enforce_structured_size_limit(
        data,
        truncatable_key="series",
        max_bytes=5000,
        serializer=serializer,
    )

    assert result["truncated"] is True
    assert 0 < len(result["series"]) < 50
    assert result["total_count"] == 50
    assert len(serializer(result)) <= 5000


def test_streams_key_truncation():
    """Test truncation works with 'streams' key (for range log responses)."""
    data = {
        "result_type": "streams",
        "streams": [
            {"stream": {"app": f"svc-{i}"}, "entries": [{"ts": str(j), "line": f"log {i}-{j} " * 30} for j in range(10)]}
            for i in range(30)
        ],
        "total_lines": 300,
        "truncated": False,
        "warnings": [],
    }

    def serializer(obj):
        return json.dumps(obj).encode("utf-8")

    result = enforce_structured_size_limit(
        data,
        truncatable_key="streams",
        max_bytes=5000,
        serializer=serializer,
    )

    assert result["truncated"] is True
    assert 0 < len(result["streams"]) < 30
    assert result["total_count"] == 30
    assert len(serializer(result)) <= 5000
