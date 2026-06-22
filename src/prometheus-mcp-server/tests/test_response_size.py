"""Tests for the response size truncation utility."""

import json
from prometheus_mcp_server.utils.response_size import enforce_structured_size_limit


def test_small_response_passes_through():
    """Test that a response under the limit is not modified."""
    data = {
        "status": "success",
        "result": [
            {"metric": {"id": "1"}, "value": [1000, "1"]},
            {"metric": {"id": "2"}, "value": [1000, "2"]},
        ]
    }
    
    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=1000)
    assert len(result["result"]) == 2
    assert "truncated" not in result


def test_large_response_truncated():
    """Test that a large response is truncated to fit under the limit."""
    data = {
        "status": "success",
        "result": [
            {"metric": {"id": str(i) * 100}, "value": [1000, str(i)]}
            for i in range(100)
        ]
    }
    
    # Each item is ~130 bytes. With 100 items the total is ~13KB.
    # Set a generous max_bytes to allow room for truncation metadata
    # (total_count, _truncation_advice) which add ~300 bytes.
    
    def serializer(obj):
        return json.dumps(obj).encode("utf-8")
        
    result = enforce_structured_size_limit(
        data, 
        truncatable_key="result", 
        max_bytes=2000,
        serializer=serializer
    )
    
    assert 0 < len(result["result"]) < 100
    assert result["truncated"] is True
    assert result["truncated_at"] == len(result["result"])
    assert result["total_count"] == 100
    assert "_truncation_advice" in result
    # The final serialized result (including metadata) fits within budget
    assert len(serializer(result)) <= 2000


def test_truncation_advice_contains_guidance():
    """Test that truncation advice includes actionable PromQL suggestions."""
    data = {
        "status": "success",
        "result": [
            {"metric": {"id": str(i) * 200}, "value": [1000, str(i)]}
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
        query_hint="http_server_duration_milliseconds_bucket",
    )
    
    assert result["truncated"] is True
    advice = result["_truncation_advice"]
    assert "truncated" in advice.lower()
    # Should include histogram-specific advice for bucket queries
    assert "histogram_quantile" in advice


def test_truncation_advice_generic_for_non_bucket():
    """Test that non-bucket queries get generic advice."""
    data = {
        "status": "success",
        "result": [
            {"metric": {"id": str(i) * 200}, "value": [1000, str(i)]}
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
        query_hint="up",
    )
    
    assert result["truncated"] is True
    advice = result["_truncation_advice"]
    assert "topk" in advice
    assert "histogram_quantile" not in advice


def test_missing_truncatable_key():
    """Test that missing key safely returns unchanged."""
    data = {"status": "success", "other_key": [1, 2, 3]}
    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=10)
    assert result == data


def test_empty_array_handled():
    """Test that empty array is handled safely."""
    data = {"status": "success", "result": []}
    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=10)
    assert result == data


def test_not_an_array_handled():
    """Test that non-array is handled safely."""
    data = {"status": "success", "result": "not an array"}
    result = enforce_structured_size_limit(data, truncatable_key="result", max_bytes=10)
    assert result == data
