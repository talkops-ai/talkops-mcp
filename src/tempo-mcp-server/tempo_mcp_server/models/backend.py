"""Backend-related Pydantic models."""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class BackendInfo(BaseTempoModel):
    """Summary information for a single Tempo backend."""

    id: str
    type: str
    display_name: Optional[str] = None
    base_url: str
    deployment_mode: str = "unknown"
    multi_tenant: bool = False
    health: str = "unknown"          # "ready", "not_ready", "unreachable"
    version: Optional[str] = None


class BackendCapabilities(BaseTempoModel):
    """Detailed backend profile with capabilities."""

    id: str
    type: str
    display_name: Optional[str] = None
    base_url: str
    deployment_mode: str = "unknown"
    multi_tenant: bool = False
    health: str = "unknown"
    version: Optional[str] = None
    build_info: Optional[Dict[str, Any]] = None
    capabilities: List[str] = []     # e.g. ["search", "metrics", "traceql"]
    retention: Optional[str] = None
    query_defaults: Optional[Dict[str, Any]] = None
    tenant_requirements: Optional[str] = None  # "required" | "optional" | "not_applicable"
    services: Optional[Dict[str, str]] = None  # component -> status
    endpoints: Optional[List[str]] = None


class BackendsSummary(BaseTempoModel):
    """Summary of all backends."""

    backends: List[BackendInfo]
    total: int
    healthy: int
    unhealthy: int
