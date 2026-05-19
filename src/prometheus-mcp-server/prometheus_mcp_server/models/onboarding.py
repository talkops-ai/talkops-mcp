"""Application onboarding and instrumentation models."""

from typing import List, Literal, Optional

from pydantic import Field

from prometheus_mcp_server.models.common import BasePrometheusModel


class InstrumentationStrategy(BasePrometheusModel):
    """Recommended instrumentation strategy for a workload."""

    strategy: Literal["direct_instrumentation", "exporter", "builtin_metrics"]
    rationale: str
    recommended_exporter_type: Optional[str] = None
    recommended_client_library: Optional[str] = None


class InstrumentationSnippet(BasePrometheusModel):
    """Generated code snippet for instrumenting an application."""

    snippet: str
    instructions: str = ""
    dependencies: List[str] = Field(default_factory=list)


class ScrapeEndpointTestResult(BasePrometheusModel):
    """Result of testing a /metrics endpoint for Prometheus compatibility."""

    ok: bool
    status_code: int = 0
    metrics_found: List[str] = Field(default_factory=list)
    format: Literal["openmetrics", "prometheus", "unknown"] = "unknown"
    errors: List[str] = Field(default_factory=list)
