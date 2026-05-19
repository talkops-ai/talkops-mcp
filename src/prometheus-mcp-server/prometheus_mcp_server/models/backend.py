"""Prometheus backend models."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from prometheus_mcp_server.models.common import BasePrometheusModel


class BackendInfo(BasePrometheusModel):
    """Summary information about a Prometheus-compatible backend."""

    id: str
    type: Literal["prometheus", "thanos", "mimir", "cortex", "victoriametrics", "other"] = "prometheus"
    display_name: Optional[str] = None
    base_url: str
    labels: Dict[str, str] = Field(default_factory=dict)
    health: Literal["unknown", "healthy", "degraded", "unhealthy"] = "unknown"
    version: Optional[str] = None


class BackendCapabilities(BasePrometheusModel):
    """Detailed backend capabilities and runtime information."""

    backend: BackendInfo
    runtimeinfo: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, bool] = Field(
        default_factory=dict,
        description="Feature flags: supports_exemplars, supports_remote_write, etc.",
    )


class BackendsSummary(BasePrometheusModel):
    """Summary of all known backends."""

    backends: List[BackendInfo]
