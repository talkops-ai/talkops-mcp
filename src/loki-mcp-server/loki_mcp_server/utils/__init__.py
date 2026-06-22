"""Utils module."""

from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.logql_helpers import (
    detect_high_cardinality_in_selector,
    format_log_entries,
    suggest_pattern_from_lines,
    validate_stream_selector,
)
from loki_mcp_server.utils.pagination import (
    decode_cursor,
    encode_cursor,
    paginate,
)
from loki_mcp_server.utils.time_utils import (
    ensure_rfc3339,
    parse_relative_time,
    validate_time_window,
)

__all__ = [
    # Error handling
    "tool_error_boundary",
    # Pagination
    "encode_cursor",
    "decode_cursor",
    "paginate",
    # Time
    "parse_relative_time",
    "validate_time_window",
    "ensure_rfc3339",
    # LogQL
    "validate_stream_selector",
    "detect_high_cardinality_in_selector",
    "format_log_entries",
    "suggest_pattern_from_lines",
]

