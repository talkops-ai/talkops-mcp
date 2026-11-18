"""Tests for the response size truncation utility (facts-only truncation metadata)."""

import json
from tempo_mcp_server.utils.response_size import enforce_structured_size_limit


def test_small_response_passes_through():
    """Test that a response under the limit is not modified."""
    data = {
        "status": "success",
        "traces": [
            {"trace_id": "abc123", "duration_ms": 100},
            {"trace_id": "def456", "duration_ms": 200},
        ],
    }

    result = enforce_structured_size_limit(data, truncatable_key="traces", max_bytes=1000)
    assert len(result["traces"]) == 2
    assert "truncated" not in result


def test_large_response_truncated_without_procedural_advice():
    """Test that a large response is truncated with facts-only metadata and no _truncation_advice."""
    data = {
        "status": "success",
        "traces": [
            {"trace_id": str(i) * 100, "duration_ms": i * 10, "service": f"svc-{i}"}
            for i in range(100)
        ],
    }

    def serializer(obj):
        return json.dumps(obj).encode("utf-8")

    result = enforce_structured_size_limit(
        data,
        truncatable_key="traces",
        max_bytes=2000,
        serializer=serializer,
    )

    assert 0 < len(result["traces"]) < 100
    assert result["truncated"] is True
    assert result["truncated_at"] == len(result["traces"])
    assert result["total_count"] == 100
    assert "_truncation_advice" not in result
    assert len(serializer(result)) <= 2000


def test_missing_truncatable_key():
    """Test that missing key safely returns unchanged."""
    data = {"status": "success", "other_key": [1, 2, 3]}
    result = enforce_structured_size_limit(data, truncatable_key="traces", max_bytes=10)
    assert result == data


def test_empty_array_handled():
    """Test that empty array is handled safely."""
    data = {"status": "success", "traces": []}
    result = enforce_structured_size_limit(data, truncatable_key="traces", max_bytes=10)
    assert result == data


def test_not_an_array_handled():
    """Test that non-array is handled safely."""
    data = {"status": "success", "traces": "not an array"}
    result = enforce_structured_size_limit(data, truncatable_key="traces", max_bytes=10)
    assert result == data


def test_series_key_truncation():
    """Test truncation works with 'series' key (for metrics tools)."""
    data = {
        "effective_query": "{ } | rate()",
        "result_type": "matrix",
        "series": [
            {
                "labels": {"service": f"svc-{i}"},
                "points": [{"ts": 1000 + j, "value": str(j)} for j in range(20)],
            }
            for i in range(50)
        ],
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
    assert "_truncation_advice" not in result
    assert len(serializer(result)) <= 5000
