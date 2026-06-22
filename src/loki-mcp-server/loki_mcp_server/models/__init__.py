"""Models module initialization.

Re-exports all Pydantic models for convenient imports.
"""

from loki_mcp_server.models.common import (
    PaginatedResponse,
    QueryDirection,
    TimeRange,
)
from loki_mcp_server.models.detected_fields import (
    LokiDetectedField,
    LokiDetectedFieldsResult,
)
from loki_mcp_server.models.patterns import (
    LokiPattern,
    LokiPatternResult,
)
from loki_mcp_server.models.query import (
    LokiLogEntry,
    LokiLogQueryResult,
    LokiMetricQueryResult,
    LokiMetricSample,
    LokiMetricSeries,
    LokiStream,
)
from loki_mcp_server.models.schema import (
    LokiCardinalityReport,
    LokiLabelCardinality,
    LokiSeriesInfo,
)
from loki_mcp_server.models.stats import (
    LokiIndexStats,
)

__all__ = [
    # Common
    "TimeRange",
    "QueryDirection",
    "PaginatedResponse",
    # Query
    "LokiLogEntry",
    "LokiStream",
    "LokiLogQueryResult",
    "LokiMetricSample",
    "LokiMetricSeries",
    "LokiMetricQueryResult",
    # Schema
    "LokiLabelCardinality",
    "LokiCardinalityReport",
    "LokiSeriesInfo",
    # Stats
    "LokiIndexStats",
    # Patterns
    "LokiPattern",
    "LokiPatternResult",
    # Detected Fields
    "LokiDetectedField",
    "LokiDetectedFieldsResult",
]
