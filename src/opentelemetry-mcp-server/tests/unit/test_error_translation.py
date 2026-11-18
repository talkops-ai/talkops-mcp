"""T-U10: Unit tests for translate_error returning FastMCP ToolError with recovery hints (S4 fix)."""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from opentelemetry_mcp_server.exceptions import (
    OtelConfigParseError,
    OtelConnectionError,
    OtelResourceNotFoundError,
    OtelValidationError,
)
from opentelemetry_mcp_server.tools.base import translate_error


def test_translate_error_returns_tool_error_with_recovery_hints():
    err_404 = translate_error(
        OtelResourceNotFoundError("Collector 'main' not found"),
        tool_name="otel_patch_collector",
        namespace="prod",
        resource_name="main",
    )
    assert isinstance(err_404, ToolError)
    assert "otel://collectors/prod" in str(err_404)
    assert "otel_list_workloads" in str(err_404)

    err_val = translate_error(
        OtelValidationError("Invalid mode 'foo'"),
        tool_name="otel_provision_collector",
    )
    assert isinstance(err_val, ToolError)
    assert "Invalid mode" in str(err_val)

    err_yaml = translate_error(
        OtelConfigParseError("Invalid YAML indentation"),
        tool_name="otel_validate_collector_config",
    )
    assert isinstance(err_yaml, ToolError)
    assert "YAML" in str(err_yaml)

    err_conn = translate_error(
        OtelConnectionError("Forbidden 403"),
        tool_name="otel_survey_cluster",
    )
    assert isinstance(err_conn, ToolError)
    assert "Forbidden 403" in str(err_conn)
