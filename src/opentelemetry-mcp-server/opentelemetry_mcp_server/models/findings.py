"""Canonical FindingCode enum and structured Finding model.

Defines the contract between the MCP Execution Layer (which detects facts and
emits deterministic finding codes + evidence) and the Agent Skill Knowledge
Layer (which maps finding codes to root causes and remediation playbooks).
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    """Severity level for diagnostic and validation findings."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FindingCode(str, Enum):
    """Stable finding codes emitted by validation, diagnostic, and mutation tools."""

    # ── Configuration & Pipeline Invariants (CFG_*) ──
    CFG_UNDEFINED_COMPONENT_REF = "CFG_UNDEFINED_COMPONENT_REF"
    CFG_UNDECLARED_COMPONENT = "CFG_UNDEFINED_COMPONENT_REF"
    CFG_UNUSED_COMPONENT = "CFG_UNUSED_COMPONENT"
    CFG_MEMORY_LIMITER_NOT_FIRST = "CFG_MEMORY_LIMITER_NOT_FIRST"
    CFG_DOUBLE_BATCHING = "CFG_DOUBLE_BATCHING"
    CFG_NO_SENDING_QUEUE = "CFG_NO_SENDING_QUEUE"
    CFG_EXPORTER_NO_QUEUE_RETRY = "CFG_NO_SENDING_QUEUE"
    CFG_NO_RETRY = "CFG_NO_RETRY"
    CFG_DEPRECATED_TELEMETRY_ADDRESS = "CFG_DEPRECATED_TELEMETRY_ADDRESS"
    CFG_DEPRECATED_COMPONENT = "CFG_DEPRECATED_COMPONENT"
    CFG_K8SATTR_NO_NODE_FILTER = "CFG_K8SATTR_NO_NODE_FILTER"
    CFG_K8SATTR_MISSING_NODE_FILTER = "CFG_K8SATTR_NO_NODE_FILTER"
    CFG_K8SATTR_RBAC_MISSING = "CFG_K8SATTR_RBAC_MISSING"
    CFG_K8SATTR_MISSING_RBAC = "CFG_K8SATTR_RBAC_MISSING"
    CFG_FILELOG_NO_SELF_EXCLUDE = "CFG_FILELOG_NO_SELF_EXCLUDE"
    CFG_FILELOG_NO_SELF_EXCLUSION = "CFG_FILELOG_NO_SELF_EXCLUDE"
    CFG_FILELOG_EPHEMERAL_CHECKPOINT = "CFG_FILELOG_EPHEMERAL_CHECKPOINT"
    CFG_FILELOG_EPHEMERAL_STORAGE = "CFG_FILELOG_EPHEMERAL_CHECKPOINT"
    CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY = "CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY"
    CFG_SPANMETRICS_HIGH_CARD_DIMENSION = "CFG_SPANMETRICS_HIGH_CARD_DIMENSION"
    CFG_SPANMETRICS_HIGH_CARDINALITY = "CFG_SPANMETRICS_HIGH_CARD_DIMENSION"
    CFG_PROM_SCRAPE_DUPLICATION = "CFG_PROM_SCRAPE_DUPLICATION"
    CFG_PROMETHEUS_NO_TARGET_ALLOCATOR = "CFG_PROM_SCRAPE_DUPLICATION"
    CFG_NO_GOMEMLIMIT = "CFG_NO_GOMEMLIMIT"
    CFG_GOMEMLIMIT_MISMATCH = "CFG_NO_GOMEMLIMIT"
    CFG_DEBUG_EXPORTER_ONLY = "CFG_DEBUG_EXPORTER_ONLY"
    CFG_CONNECTOR_LOOP = "CFG_CONNECTOR_LOOP"

    # ── Runtime & Live Pipeline Diagnostics (RT_*) ──
    RT_HEALTHY = "RT_HEALTHY"
    RT_PODS_NOT_READY = "RT_PODS_NOT_READY"
    RT_OOMKILLED = "RT_OOMKILLED"
    RT_POD_OOMKILLED = "RT_OOMKILLED"
    RT_CRASHLOOP = "RT_CRASHLOOP"
    RT_POD_CRASHLOOP = "RT_CRASHLOOP"
    RT_NO_SERVICE_ENDPOINTS = "RT_NO_SERVICE_ENDPOINTS"
    RT_NO_READY_ENDPOINTS = "RT_NO_SERVICE_ENDPOINTS"
    RT_EXPORTER_SEND_FAILED = "RT_EXPORTER_SEND_FAILED"
    RT_QUEUE_SATURATED = "RT_QUEUE_SATURATED"
    RT_EXPORTER_QUEUE_SATURATED = "RT_QUEUE_SATURATED"
    RT_ENQUEUE_FAILED = "RT_ENQUEUE_FAILED"
    RT_RECEIVER_REFUSED = "RT_RECEIVER_REFUSED"
    RT_PROCESSOR_DROPPED = "RT_PROCESSOR_DROPPED"
    RT_PROCESSOR_REFUSED = "RT_PROCESSOR_DROPPED"
    RT_NO_DATA_RECEIVED = "RT_NO_DATA_RECEIVED"
    RT_NO_TELEMETRY_FLOW = "RT_NO_DATA_RECEIVED"
    RT_METRICS_UNREACHABLE = "RT_METRICS_UNREACHABLE"
    RT_LOG_AUTH_ERROR = "RT_LOG_AUTH_ERROR"
    RT_LOG_TLS_ERROR = "RT_LOG_TLS_ERROR"
    RT_LOG_DNS_ERROR = "RT_LOG_DNS_ERROR"

    # ── Operator & Auto-Instrumentation (OP_* / INST_*) ──
    OP_NOT_INSTALLED = "OP_NOT_INSTALLED"
    OP_WEBHOOK_CERT_ERROR = "OP_WEBHOOK_CERT_ERROR"
    OP_WEBHOOK_ERROR = "OP_WEBHOOK_CERT_ERROR"
    OP_MULTIPLE_INSTRUMENTATIONS = "OP_MULTIPLE_INSTRUMENTATIONS"
    OP_MULTIPLE_INSTRUMENTATION_CRS = "OP_MULTIPLE_INSTRUMENTATIONS"
    OP_LANGUAGE_DISABLED = "OP_LANGUAGE_DISABLED"
    INST_HEALTHY = "INST_HEALTHY"
    INST_ANNOTATION_NO_CR = "INST_ANNOTATION_NO_CR"
    INST_NO_CR_IN_NAMESPACE = "INST_ANNOTATION_NO_CR"
    INST_POD_PREDATES_INJECTION = "INST_POD_PREDATES_INJECTION"
    INST_POD_NOT_RESTARTED = "INST_POD_PREDATES_INJECTION"
    INST_CONFLICTING_ENV = "INST_CONFLICTING_ENV"
    INST_CONFLICTING_ENV_OVERRIDE = "INST_CONFLICTING_ENV"
    INST_PROTOCOL_PORT_MISMATCH = "INST_PROTOCOL_PORT_MISMATCH"
    INST_GO_TARGET_EXE_MISSING = "INST_GO_TARGET_EXE_MISSING"
    INST_GO_MISSING_TARGET_EXE = "INST_GO_TARGET_EXE_MISSING"
    INST_INIT_CONTAINER_FAILED = "INST_INIT_CONTAINER_FAILED"
    INST_WEBHOOK_BLOCKED = "INST_INIT_CONTAINER_FAILED"
    INST_CONTAINER_NAME_MISMATCH = "INST_CONTAINER_NAME_MISMATCH"
    INST_IMAGE_UNPINNED = "INST_IMAGE_UNPINNED"

    # ── Security & Governance (SEC_*) ──
    SEC_INLINE_SECRET = "SEC_INLINE_SECRET"
    SEC_TLS_VERIFY_DISABLED = "SEC_TLS_VERIFY_DISABLED"
    SEC_TLS_SKIP_VERIFY = "SEC_TLS_VERIFY_DISABLED"
    SEC_INSECURE_EXPORTER = "SEC_INSECURE_EXPORTER"
    SEC_SECRET_REF_MISSING = "SEC_SECRET_REF_MISSING"
    SEC_MISSING_SECRET_KEY = "SEC_SECRET_REF_MISSING"
    SEC_PRIVILEGED_CONTAINER = "SEC_PRIVILEGED_CONTAINER"
    SEC_EBPF_PRIVILEGED = "SEC_PRIVILEGED_CONTAINER"
    SEC_RUN_AS_ROOT = "SEC_RUN_AS_ROOT"
    SEC_POD_RUN_AS_ROOT = "SEC_RUN_AS_ROOT"
    SEC_HOSTPATH_WRITABLE = "SEC_HOSTPATH_WRITABLE"
    SEC_RBAC_WILDCARD = "SEC_RBAC_WILDCARD"
    SEC_EBPF_EXCESS_CAPS = "SEC_EBPF_EXCESS_CAPS"
    SEC_EBPF_SYS_ADMIN = "SEC_EBPF_EXCESS_CAPS"
    SEC_EBPF_HOST_PID = "SEC_EBPF_HOST_PID"
    SEC_PII_REDACTION_MISSING = "SEC_PII_REDACTION_MISSING"
    SEC_DEBUG_EXTENSION_EXPOSED = "SEC_DEBUG_EXTENSION_EXPOSED"

    # ── GitOps Ownership ──
    GITOPS_MANAGED = "GITOPS_MANAGED"


FINDING_CODE_DEFAULT_SEVERITY: Dict[FindingCode, FindingSeverity] = {
    FindingCode.CFG_UNDEFINED_COMPONENT_REF: FindingSeverity.ERROR,
    FindingCode.CFG_UNUSED_COMPONENT: FindingSeverity.WARNING,
    FindingCode.CFG_MEMORY_LIMITER_NOT_FIRST: FindingSeverity.WARNING,
    FindingCode.CFG_DOUBLE_BATCHING: FindingSeverity.WARNING,
    FindingCode.CFG_NO_SENDING_QUEUE: FindingSeverity.WARNING,
    FindingCode.CFG_NO_RETRY: FindingSeverity.WARNING,
    FindingCode.CFG_DEPRECATED_TELEMETRY_ADDRESS: FindingSeverity.WARNING,
    FindingCode.CFG_DEPRECATED_COMPONENT: FindingSeverity.WARNING,
    FindingCode.CFG_K8SATTR_NO_NODE_FILTER: FindingSeverity.WARNING,
    FindingCode.CFG_K8SATTR_RBAC_MISSING: FindingSeverity.WARNING,
    FindingCode.CFG_FILELOG_NO_SELF_EXCLUDE: FindingSeverity.ERROR,
    FindingCode.CFG_FILELOG_EPHEMERAL_CHECKPOINT: FindingSeverity.WARNING,
    FindingCode.CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY: FindingSeverity.ERROR,
    FindingCode.CFG_SPANMETRICS_HIGH_CARD_DIMENSION: FindingSeverity.WARNING,
    FindingCode.CFG_PROM_SCRAPE_DUPLICATION: FindingSeverity.WARNING,
    FindingCode.CFG_NO_GOMEMLIMIT: FindingSeverity.INFO,
    FindingCode.CFG_DEBUG_EXPORTER_ONLY: FindingSeverity.WARNING,
    FindingCode.CFG_CONNECTOR_LOOP: FindingSeverity.ERROR,
    FindingCode.RT_HEALTHY: FindingSeverity.INFO,
    FindingCode.RT_PODS_NOT_READY: FindingSeverity.ERROR,
    FindingCode.RT_OOMKILLED: FindingSeverity.ERROR,
    FindingCode.RT_CRASHLOOP: FindingSeverity.ERROR,
    FindingCode.RT_NO_SERVICE_ENDPOINTS: FindingSeverity.ERROR,
    FindingCode.RT_EXPORTER_SEND_FAILED: FindingSeverity.ERROR,
    FindingCode.RT_QUEUE_SATURATED: FindingSeverity.WARNING,
    FindingCode.RT_ENQUEUE_FAILED: FindingSeverity.ERROR,
    FindingCode.RT_RECEIVER_REFUSED: FindingSeverity.ERROR,
    FindingCode.RT_PROCESSOR_DROPPED: FindingSeverity.WARNING,
    FindingCode.RT_NO_DATA_RECEIVED: FindingSeverity.WARNING,
    FindingCode.RT_METRICS_UNREACHABLE: FindingSeverity.WARNING,
    FindingCode.RT_LOG_AUTH_ERROR: FindingSeverity.ERROR,
    FindingCode.RT_LOG_TLS_ERROR: FindingSeverity.ERROR,
    FindingCode.RT_LOG_DNS_ERROR: FindingSeverity.ERROR,
    FindingCode.OP_NOT_INSTALLED: FindingSeverity.ERROR,
    FindingCode.OP_WEBHOOK_CERT_ERROR: FindingSeverity.ERROR,
    FindingCode.OP_MULTIPLE_INSTRUMENTATIONS: FindingSeverity.ERROR,
    FindingCode.OP_LANGUAGE_DISABLED: FindingSeverity.ERROR,
    FindingCode.INST_HEALTHY: FindingSeverity.INFO,
    FindingCode.INST_ANNOTATION_NO_CR: FindingSeverity.ERROR,
    FindingCode.INST_POD_PREDATES_INJECTION: FindingSeverity.WARNING,
    FindingCode.INST_CONFLICTING_ENV: FindingSeverity.WARNING,
    FindingCode.INST_PROTOCOL_PORT_MISMATCH: FindingSeverity.ERROR,
    FindingCode.INST_GO_TARGET_EXE_MISSING: FindingSeverity.ERROR,
    FindingCode.INST_INIT_CONTAINER_FAILED: FindingSeverity.ERROR,
    FindingCode.INST_CONTAINER_NAME_MISMATCH: FindingSeverity.WARNING,
    FindingCode.INST_IMAGE_UNPINNED: FindingSeverity.WARNING,
    FindingCode.SEC_INLINE_SECRET: FindingSeverity.ERROR,
    FindingCode.SEC_TLS_VERIFY_DISABLED: FindingSeverity.WARNING,
    FindingCode.SEC_INSECURE_EXPORTER: FindingSeverity.WARNING,
    FindingCode.SEC_SECRET_REF_MISSING: FindingSeverity.ERROR,
    FindingCode.SEC_PRIVILEGED_CONTAINER: FindingSeverity.ERROR,
    FindingCode.SEC_RUN_AS_ROOT: FindingSeverity.WARNING,
    FindingCode.SEC_HOSTPATH_WRITABLE: FindingSeverity.WARNING,
    FindingCode.SEC_RBAC_WILDCARD: FindingSeverity.ERROR,
    FindingCode.SEC_EBPF_EXCESS_CAPS: FindingSeverity.ERROR,
    FindingCode.SEC_EBPF_HOST_PID: FindingSeverity.WARNING,
    FindingCode.SEC_PII_REDACTION_MISSING: FindingSeverity.WARNING,
    FindingCode.SEC_DEBUG_EXTENSION_EXPOSED: FindingSeverity.WARNING,
    FindingCode.GITOPS_MANAGED: FindingSeverity.WARNING,
}


class Finding(BaseModel):
    """Structured diagnostic or validation finding emitted by the server."""

    code: FindingCode = Field(..., description="Canonical finding code")
    severity: FindingSeverity = Field(
        ...,
        description="Severity level: 'error' blocks apply, 'warning' or 'info' is advisory",
    )
    component: Optional[str] = Field(
        default=None,
        description="Component or resource path where the finding was detected",
    )
    field_path: Optional[str] = Field(
        default=None,
        description="Field path where the finding was detected",
    )
    message: str = Field(
        ..., description="Concise factual summary of the detected condition"
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured evidence dictionary (keys, metrics, paths)",
    )
    next_tool_hint: Optional[str] = Field(
        default=None,
        description="One-line hint pointing the model to the next MCP tool or remediation",
    )
    remediation: Optional[str] = Field(
        default=None,
        description="Actionable remediation guidance",
    )

    @classmethod
    def create(
        cls,
        code: FindingCode,
        message: str,
        *,
        component: Optional[str] = None,
        field_path: Optional[str] = None,
        severity: Optional[FindingSeverity | str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        next_tool_hint: Optional[str] = None,
        remediation: Optional[str] = None,
    ) -> "Finding":
        """Create a Finding using the default severity for the code unless overridden."""
        if isinstance(severity, str):
            resolved_severity = FindingSeverity(severity)
        else:
            resolved_severity = severity or FINDING_CODE_DEFAULT_SEVERITY.get(
                code, FindingSeverity.WARNING
            )
        comp = component or field_path
        hint = next_tool_hint or remediation
        return cls(
            code=code,
            severity=resolved_severity,
            component=comp,
            field_path=field_path or comp,
            message=message,
            evidence=evidence or {},
            next_tool_hint=hint,
            remediation=remediation or hint,
        )
