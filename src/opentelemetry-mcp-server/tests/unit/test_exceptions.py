"""Unit tests for custom exception hierarchy.

Verifies that all custom exceptions inherit from the correct
FastMCP base exceptions, as required for proper MCP error propagation.
"""

import pytest

from opentelemetry_mcp_server.exceptions import (
    OtelConfigParseError,
    OtelConnectionError,
    OtelOperationError,
    OtelResourceError,
    OtelResourceNotFoundError,
    OtelValidationError,
)
from fastmcp.exceptions import (
    NotFoundError,
    ResourceError,
    ToolError,
    ValidationError,
)


class TestExceptionHierarchy:
    """Verify all custom exceptions inherit correctly."""

    def test_operation_error_inherits_tool_error(self):
        assert issubclass(OtelOperationError, ToolError)

    def test_resource_error_inherits_resource_error(self):
        assert issubclass(OtelResourceError, ResourceError)

    def test_resource_not_found_inherits_not_found_error(self):
        assert issubclass(OtelResourceNotFoundError, NotFoundError)

    def test_validation_error_inherits_validation_error(self):
        assert issubclass(OtelValidationError, ValidationError)

    def test_connection_error_inherits_tool_error(self):
        assert issubclass(OtelConnectionError, ToolError)

    def test_config_parse_error_inherits_tool_error(self):
        assert issubclass(OtelConfigParseError, ToolError)


class TestExceptionMessages:
    """Verify exceptions carry messages correctly."""

    def test_operation_error_message(self):
        exc = OtelOperationError("Failed to list collectors")
        assert "Failed to list collectors" in str(exc)

    def test_resource_not_found_message(self):
        exc = OtelResourceNotFoundError("Collector 'x' not found")
        assert "Collector 'x' not found" in str(exc)

    def test_validation_error_message(self):
        exc = OtelValidationError("Invalid language: 'cobol'")
        assert "Invalid language" in str(exc)

    def test_connection_error_message(self):
        exc = OtelConnectionError("Kubernetes client not available")
        assert "Kubernetes client" in str(exc)

    def test_config_parse_error_message(self):
        exc = OtelConfigParseError("Malformed YAML")
        assert "Malformed YAML" in str(exc)


class TestExceptionRaising:
    """Verify exceptions can be raised and caught by their base types."""

    def test_catch_operation_error_as_tool_error(self):
        with pytest.raises(ToolError):
            raise OtelOperationError("test")

    def test_catch_resource_not_found_as_not_found(self):
        with pytest.raises(NotFoundError):
            raise OtelResourceNotFoundError("test")

    def test_catch_validation_error_as_validation(self):
        with pytest.raises(ValidationError):
            raise OtelValidationError("test")

    def test_catch_resource_error_as_resource(self):
        with pytest.raises(ResourceError):
            raise OtelResourceError("test")
