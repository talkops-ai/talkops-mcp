"""Service topology / dependency models.

Service graph metrics validated per research:
- traces_service_graph_request_total (counter with client, server labels)
- traces_service_graph_request_failed_total (error counter)
"""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class ServiceNode(BaseTempoModel):
    """A service in the dependency graph."""

    service: str
    namespace: Optional[str] = None
    cluster: Optional[str] = None


class ServiceEdge(BaseTempoModel):
    """An edge between two services."""

    client: str
    server: str
    request_rate: Optional[float] = None
    error_rate: Optional[float] = None
    p95_duration_ms: Optional[float] = None
    source_metric: str = "traces_service_graph_request_total"


class ServiceDependenciesOutput(BaseTempoModel):
    """Output of tempo_get_service_dependencies tool."""

    nodes: List[ServiceNode] = []
    edges: List[ServiceEdge] = []
    method: str = "service_graph_metrics"  # or "traceql_inference"
    summary: Optional[str] = None
