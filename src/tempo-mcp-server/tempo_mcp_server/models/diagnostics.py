"""Diagnostics and observation models (facts-only, zero procedural leakage)."""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel

ALL_OBSERVATION_CODES: tuple[str, ...] = (
    "BACKEND_UNREACHABLE",
    "BUILD_INFO_UNAVAILABLE",
    "COMPONENT_NOT_RUNNING",
    "RING_CHECK_FAILED",
    "RING_MEMBER_UNHEALTHY",
    "PARTITION_LAG_OBSERVED",
    "SPANS_DISCARDED",
    "METRICS_GENERATOR_PROCESSOR_ABSENT",
    "OVERRIDES_API_DISABLED",
    "INGESTION_METRICS_UNREACHABLE",
    "DEPLOYMENT_MODE_UNKNOWN",
    "TRACE_TIME_GAPS",
    "SPAN_ERRORS_PRESENT",
    "OPERATOR_CR_NOT_READY",
    "TENANT_HEADER_REQUIRED",
)

# Alias for skill/test cross-referencing
ALL_DIAGNOSIS_CODES = ALL_OBSERVATION_CODES


class ObservationFinding(BaseTempoModel):
    """A factual diagnostic observation with structured evidence (no severity or remediation)."""

    code: str
    component: str
    message: str
    evidence: Dict[str, Any] = {}


# Keep alias for backwards import compatibility
DiagnosticFinding = ObservationFinding


class DiagnosticsOutput(BaseTempoModel):
    """Output of tempo_get_diagnostics tool."""

    ready: bool = False
    tempo_major_version: Optional[int] = None
    architecture_generation: str = "unknown"  # "2.x", "3.x", or "unknown"
    deployment_mode: str = "unknown"
    build_info: Optional[Dict[str, Any]] = None
    services: Optional[Dict[str, str]] = None
    ring_checks: Optional[Dict[str, Any]] = None
    discarded_spans: Optional[Dict[str, float]] = None
    max_partition_lag_seconds: Optional[float] = None
    config_facts: Optional[Dict[str, Any]] = None
    findings: List[ObservationFinding] = []
    observation_codes: List[str] = []


class QueryPolicyOutput(BaseTempoModel):
    """Output of server query policy guardrails."""

    policies: Dict[str, Any] = {}
    backend_id: Optional[str] = None
