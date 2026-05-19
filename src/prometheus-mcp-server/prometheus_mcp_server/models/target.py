"""Prometheus target and topology models."""

from typing import Dict, List, Literal, Optional

from pydantic import Field

from prometheus_mcp_server.models.common import BasePrometheusModel
from prometheus_mcp_server.models.metadata import MetricMetadata


class TargetInfo(BasePrometheusModel):
    """Information about a single scrape target."""

    job: str
    instance: str
    health: Literal["up", "down", "unknown"] = "unknown"
    labels: Dict[str, str] = Field(default_factory=dict)
    last_scrape: Optional[float] = None
    last_scrape_duration: Optional[float] = None
    last_error: Optional[str] = None
    scrape_pool: Optional[str] = None


class ServiceInfo(BasePrometheusModel):
    """Logical service derived from scrape targets."""

    service_id: str
    display_name: Optional[str] = None
    backend_id: str
    job: str
    namespace: Optional[str] = None
    environment: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    targets_up: int = 0
    targets_total: int = 0


class FailedTarget(BasePrometheusModel):
    """A scrape target that is currently failing."""

    backend_id: str
    job: str
    instance: str
    last_scrape: Optional[float] = None
    last_scrape_error: Optional[str] = None
    health: str = "down"


class ServiceTopology(BasePrometheusModel):
    """Service catalog derived from targets."""

    services: List[ServiceInfo] = Field(default_factory=list)


class FailedTargetsSummary(BasePrometheusModel):
    """Summary of all failed scrape targets."""

    failed_targets: List[FailedTarget] = Field(default_factory=list)


class ServiceMetricsList(BasePrometheusModel):
    """Metrics emitted by a specific service/job, from /api/v1/targets/metadata."""

    job: str
    backend_id: str
    metrics: List[MetricMetadata] = Field(default_factory=list)
    total_count: int = 0
