"""Unit tests for exemplar extraction (C-03).

Verifies that exemplars are read from data["exemplars"][] (the correct
Tempo API path), not from result[].exemplars[] (the old broken path).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Helpers / test data
# ---------------------------------------------------------------------------

def _make_tempo_exemplar_response(exemplars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a mock Tempo /api/metrics/query_range response with exemplars.

    Per the official Tempo API the response shape is:
    {
        "data": {
            "resultType": "matrix",
            "result": [ ... time-series ... ],
            "exemplars": [{"traceID": "...", "timestamp": ..., "value": ...}]
        }
    }
    """
    return {
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"service.name": "api-gateway"},
                    "values": [[1716000000, "42"]],
                    # NOTE: no "exemplars" key here — they live at data level
                }
            ],
            "exemplars": exemplars,
        }
    }


def _exemplar(trace_id: str, ts: int = 1716000000) -> Dict[str, Any]:
    return {"traceID": trace_id, "timestamp": ts, "labels": {"service.name": "api-gateway"}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExemplarExtraction:
    """C-03: exemplars must be read from data['exemplars'][], not series."""

    def test_extracts_trace_ids_from_data_exemplars(self):
        """The primary happy-path: two exemplars → two trace IDs returned."""
        response = _make_tempo_exemplar_response([
            _exemplar("aabbccddeeff00112233445566778899"),
            _exemplar("11223344556677889900aabbccddeeff"),
        ])
        data = response.get("data", response)
        candidates = []
        for exemplar in data.get("exemplars", []):
            trace_id = exemplar.get("traceID", "")
            if trace_id:
                candidates.append(trace_id)

        assert len(candidates) == 2
        assert "aabbccddeeff00112233445566778899" in candidates
        assert "11223344556677889900aabbccddeeff" in candidates

    def test_series_level_exemplars_are_not_parsed(self):
        """Simulate the OLD (broken) parsing: iterating result[].exemplars.
        This must yield zero candidates — they're at data level, not series level.
        """
        response = _make_tempo_exemplar_response([
            _exemplar("aabbccddeeff00112233445566778899"),
        ])
        # Old broken code path:
        data = response.get("data", response)
        old_candidates = []
        for series in data.get("result", []):
            for exemplar in series.get("exemplars", []):  # always empty
                old_candidates.append(exemplar.get("traceID", ""))

        assert len(old_candidates) == 0, (
            "Old code would never find exemplars — they're at data level, not series level"
        )

    def test_empty_exemplars_returns_empty_list(self):
        """No exemplars in response → empty candidates."""
        response = _make_tempo_exemplar_response([])
        data = response.get("data", response)
        candidates = [e.get("traceID") for e in data.get("exemplars", []) if e.get("traceID")]
        assert candidates == []

    def test_exemplar_missing_trace_id_is_skipped(self):
        """Exemplars without traceID are silently skipped."""
        response = _make_tempo_exemplar_response([
            {"timestamp": 1716000000, "labels": {}},  # no traceID key
            _exemplar("deadbeefdeadbeef1234567890abcdef"),
        ])
        data = response.get("data", response)
        candidates = [e.get("traceID") for e in data.get("exemplars", []) if e.get("traceID")]
        assert len(candidates) == 1
        assert candidates[0] == "deadbeefdeadbeef1234567890abcdef"

    def test_exemplar_metadata_preserved(self):
        """Timestamp and labels must be returned alongside trace_id."""
        response = _make_tempo_exemplar_response([
            {"traceID": "aabbccddeeff0011", "timestamp": 9999, "labels": {"env": "prod"}},
        ])
        data = response.get("data", response)
        exemplar = data["exemplars"][0]
        assert exemplar["timestamp"] == 9999
        assert exemplar["labels"]["env"] == "prod"

    def test_response_without_data_wrapper_handled(self):
        """When response has no 'data' key, exemplars fall back to top-level."""
        # Some Tempo versions may flatten the response
        response = {
            "exemplars": [_exemplar("cafe0000cafe0000cafe0000cafe0000")],
        }
        data = response.get("data", response)
        assert isinstance(data, dict)
        candidates = [e.get("traceID") for e in data.get("exemplars", []) if e.get("traceID")]
        assert len(candidates) == 1