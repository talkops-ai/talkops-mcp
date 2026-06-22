"""Diagnostics models."""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class DiagnosticFinding(BaseTempoModel):
    """A single diagnostic finding with actionable guidance."""

    category: str                    # "health", "config", "performance", "capacity"
    severity: str                    # "info", "warning", "error", "critical"
    message: str
    suggested_action: Optional[str] = None


class DiagnosticsOutput(BaseTempoModel):
    """Output of tempo_get_diagnostics tool."""

    status: str                      # "healthy", "degraded", "unhealthy"
    ready: bool = False
    build_info: Optional[Dict[str, Any]] = None
    services: Optional[Dict[str, str]] = None    # component -> status
    ring_checks: Optional[Dict[str, Any]] = None
    findings: List[DiagnosticFinding] = []
    issues: int = 0


class QueryPolicyOutput(BaseTempoModel):
    """Output of tempo_get_query_policies tool."""

    policies: Dict[str, Any] = {}
    backend_id: Optional[str] = None
