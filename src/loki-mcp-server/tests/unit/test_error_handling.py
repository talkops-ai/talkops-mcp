"""Unit tests for the generic tool_error_boundary decorator.

Validates that all known Loki exceptions are caught and converted
to structured JSON responses that AI agents can read and self-correct from.
"""

import pytest

from loki_mcp_server.exceptions import (
    LokiConnectionError,
    LokiQueryError,
    LokiQueryTooExpensiveError,
    LokiResourceNotFoundError,
    LokiValidationError,
)
from loki_mcp_server.utils.error_handling import tool_error_boundary


# ──────────────────────────────────────────────
# Helper: build a fake tool that raises a specific exception
# ──────────────────────────────────────────────


def _make_tool(exc: Exception):
    """Create a decorated async tool function that raises the given exception."""

    @tool_error_boundary
    async def tool_fn(**kwargs):
        raise exc

    return tool_fn


def _make_success_tool(result):
    """Create a decorated async tool function that returns a result."""

    @tool_error_boundary
    async def tool_fn(**kwargs):
        return result

    return tool_fn


# ──────────────────────────────────────────────
# Standard Error Response Structure
# ──────────────────────────────────────────────


class TestErrorResponseStructure:
    """All error responses must have the same keys."""

    @pytest.mark.asyncio
    async def test_has_required_keys(self):
        """Error response must include success, error, error_type, suggestion."""
        tool = _make_tool(LokiQueryError("bad query"))
        result = await tool()

        assert "success" in result
        assert "error" in result
        assert "error_type" in result
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_success_is_false(self):
        """Error responses must have success=False."""
        tool = _make_tool(LokiQueryError("bad query"))
        result = await tool()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_success_passthrough(self):
        """Successful returns pass through unchanged."""
        expected = {"data": [1, 2, 3], "count": 3}
        tool = _make_success_tool(expected)
        result = await tool()

        assert result == expected


# ──────────────────────────────────────────────
# Exception-specific mapping
# ──────────────────────────────────────────────


class TestExceptionMapping:
    """Each exception type maps to the correct error_type."""

    @pytest.mark.asyncio
    async def test_validation_error(self):
        """LokiValidationError → error_type: 'validation_error'."""
        tool = _make_tool(
            LokiValidationError("Invalid time expression: 'invalid-time'")
        )
        result = await tool()

        assert result["error_type"] == "validation_error"
        assert "invalid-time" in result["error"]
        assert result["suggestion"]  # non-empty

    @pytest.mark.asyncio
    async def test_query_error(self):
        """LokiQueryError → error_type: 'query_error'."""
        tool = _make_tool(
            LokiQueryError(
                "Loki bad request (400): parse error at line 1, col 22: "
                "syntax error: unexpected PIPE"
            )
        )
        result = await tool()

        assert result["error_type"] == "query_error"
        assert "400" in result["error"]
        assert "LogQL" in result["suggestion"]

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """LokiConnectionError → error_type: 'connection_error'."""
        tool = _make_tool(
            LokiConnectionError("Cannot connect to Loki at http://loki:3100")
        )
        result = await tool()

        assert result["error_type"] == "connection_error"
        assert "Cannot connect" in result["error"]

    @pytest.mark.asyncio
    async def test_query_too_expensive(self):
        """LokiQueryTooExpensiveError → error_type: 'query_too_expensive'."""
        tool = _make_tool(
            LokiQueryTooExpensiveError(
                "Query would scan 15.2 GB (limit: 10.0 GB)"
            )
        )
        result = await tool()

        assert result["error_type"] == "query_too_expensive"
        assert "15.2 GB" in result["error"]
        assert "Narrow" in result["suggestion"]

    @pytest.mark.asyncio
    async def test_resource_not_found(self):
        """LokiResourceNotFoundError → error_type: 'not_found'."""
        tool = _make_tool(
            LokiResourceNotFoundError("Loki endpoint not found: /patterns")
        )
        result = await tool()

        assert result["error_type"] == "not_found"
        assert "not found" in result["error"]


# ──────────────────────────────────────────────
# Edge cases: unknown exceptions bubble up
# ──────────────────────────────────────────────


class TestUnknownExceptions:
    """Exceptions NOT in the known set must re-raise (not be swallowed)."""

    @pytest.mark.asyncio
    async def test_value_error_reraises(self):
        """Unrecognized exception types must not be caught."""
        tool = _make_tool(ValueError("something unexpected"))

        with pytest.raises(ValueError, match="something unexpected"):
            await tool()

    @pytest.mark.asyncio
    async def test_runtime_error_reraises(self):
        """RuntimeError must not be caught."""
        tool = _make_tool(RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await tool()


# ──────────────────────────────────────────────
# Practical edge case scenarios from QA
# ──────────────────────────────────────────────


class TestQaEdgeCases:
    """Real-world scenarios from the QA audit report."""

    @pytest.mark.asyncio
    async def test_malformed_logql_dangling_pipe(self):
        """Simulates: '{app=\"checkout\"} | json | ' → Loki 400."""
        tool = _make_tool(
            LokiQueryError(
                "Loki bad request (400) for "
                "http://loki:3100/loki/api/v1/query_range: "
                "parse error at line 1, col 28: "
                "syntax error: unexpected $end, expecting IDENTIFIER"
            )
        )
        result = await tool()

        assert result["success"] is False
        assert result["error_type"] == "query_error"
        assert "parse error" in result["error"]
        # AI can read this and fix the query
        assert result["suggestion"]

    @pytest.mark.asyncio
    async def test_invalid_time_expression(self):
        """Simulates: start='invalid-time' → LokiValidationError."""
        tool = _make_tool(
            LokiValidationError(
                "Invalid time expression: 'invalid-time'. "
                "Use RFC3339 (e.g., '2024-01-01T00:00:00Z'), "
                "epoch (e.g., '1700000000'), or relative (e.g., 'now-1h')."
            )
        )
        result = await tool()

        assert result["success"] is False
        assert result["error_type"] == "validation_error"
        assert "invalid-time" in result["error"]
        # Suggestion tells the AI exactly what formats are valid
        assert "RFC3339" in result["suggestion"]
