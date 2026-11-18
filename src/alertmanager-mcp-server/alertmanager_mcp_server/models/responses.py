"""Typed Pydantic response models for all 14 Alertmanager MCP tools.

Ensures FastMCP generates complete `outputSchema` and `structuredContent`
for every tool in the execution layer.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OncallSummaryResponse(BaseModel):
    """Structured output for `am_summarize_oncall`."""

    backend_id: str
    total_active_alerts: int
    total_suppressed_alerts: int = 0
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_env: Dict[str, int] = Field(default_factory=dict)
    by_service: Dict[str, int] = Field(default_factory=dict)
    by_team: Dict[str, int] = Field(default_factory=dict)
    top_alertnames: Dict[str, int] = Field(default_factory=dict)
    top_alert_groups: List[Dict[str, Any]] = Field(default_factory=list)
    watchdog_status: str = "missing"
    active_silences_count: int = 0
    summary_text: str


class AlertListResponse(BaseModel):
    """Structured output for `am_list_alerts`."""

    backend_id: str
    total: int
    offset: int
    limit: int
    has_more: bool
    alerts: List[Dict[str, Any]] = Field(default_factory=list)


class AlertGroupsResponse(BaseModel):
    """Structured output for `am_list_alert_groups`."""

    backend_id: str
    total_groups: int
    offset: int = 0
    limit: int = 50
    has_more: bool = False
    groups: List[Dict[str, Any]] = Field(default_factory=list)


class NotificationHealthResponse(BaseModel):
    """Structured output for `am_check_notification_health`."""

    backend_id: str
    healthy: bool
    ready: bool
    status: str
    version: Optional[str] = None
    uptime: Optional[str] = None
    cluster: Dict[str, Any] = Field(default_factory=dict)
    config_reload_successful: Optional[bool] = None
    config_last_reload_timestamp: Optional[str] = None
    metrics_available: bool = False
    total_notifications: int = 0
    total_failed_notifications: int = 0
    degraded_integrations: List[str] = Field(default_factory=list)
    integrations: Dict[str, Any] = Field(default_factory=dict)
    configured_receivers: List[Dict[str, Any]] = Field(default_factory=list)
    summary_text: str = ""


class RoutingExplanationResponse(BaseModel):
    """Structured output for `am_explain_routing`."""

    backend_id: str
    fingerprint: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    matched_route: str
    matched_routes: List[Dict[str, Any]] = Field(default_factory=list)
    receivers: List[str] = Field(default_factory=list)
    active_receivers: List[str] = Field(default_factory=list)
    muted_receivers: List[str] = Field(default_factory=list)
    group_labels: List[str] = Field(default_factory=list)
    fell_back_to_default: bool = False
    is_inhibited: bool = False
    inhibited_by: List[str] = Field(default_factory=list)
    inhibition_details: List[Dict[str, Any]] = Field(default_factory=list)
    potential_inhibition_rules: List[Dict[str, Any]] = Field(default_factory=list)
    matching_silences: List[Dict[str, Any]] = Field(default_factory=list)
    route_trace: List[Dict[str, Any]] = Field(default_factory=list)
    explanation: str


class SilenceListResponse(BaseModel):
    """Structured output for `am_list_silences`."""

    backend_id: str
    total: int
    offset: int
    limit: int
    has_more: bool
    silences: List[Dict[str, Any]] = Field(default_factory=list)


class SilencePreviewResponse(BaseModel):
    """Structured output for `am_preview_silence`."""

    backend_id: str
    valid: bool
    policy: Dict[str, Any] = Field(default_factory=dict)
    affected_alert_count: int = 0
    affected_critical_count: int = 0
    affected_alerts_preview: List[Dict[str, Any]] = Field(default_factory=list)
    affected_receivers: List[str] = Field(default_factory=list)
    overlapping_silences: List[Dict[str, Any]] = Field(default_factory=list)
    warning_flag: bool = False
    requires_confirmation: bool = False
    warning_message: Optional[str] = None


class AlertHygieneAuditResponse(BaseModel):
    """Structured output for `am_audit_alert_hygiene`."""

    backend_id: str
    total_active_alerts: int
    default_receiver: str
    default_route_count: int
    default_route_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_matchers: Dict[str, int] = Field(default_factory=dict)
    missing_annotations_count: int = 0
    missing_annotations_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    invalid_severity_count: int = 0
    invalid_severity_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    long_firing_count: int = 0
    long_firing_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    watchdog_status: str = "missing"
    summary_text: str = ""


class SilenceGovernanceAuditResponse(BaseModel):
    """Structured output for `am_audit_silences`."""

    backend_id: str
    since_minutes: int
    total_changes: int
    created_count: int
    expired_count: int
    updated_count: int = 0
    changes: List[Dict[str, Any]] = Field(default_factory=list)
    active_silences_count: int = 0
    policy_violations_count: int = 0
    non_compliant_silences: List[Dict[str, Any]] = Field(default_factory=list)
    stale_zero_match_silences: List[Dict[str, Any]] = Field(default_factory=list)
    expiring_soon_silences: List[Dict[str, Any]] = Field(default_factory=list)
    long_running_silences: List[Dict[str, Any]] = Field(default_factory=list)
    summary_text: str = ""


class SilenceMutationResponse(BaseModel):
    """Structured output for `am_create_silence`, `am_silence_alert`, and `am_update_silence`."""

    backend_id: str
    silence_id: str
    deduped: bool = False
    previous_silence_id: Optional[str] = None
    scope: Optional[str] = None
    matchers: List[Dict[str, Any]] = Field(default_factory=list)
    starts_at: str
    ends_at: str
    duration_minutes: float
    created_by: str
    comment: str
    affected_alert_count: int = 0
    policy_warnings: List[Dict[str, str]] = Field(default_factory=list)
    message: str


class ExpireSilenceResponse(BaseModel):
    """Structured output for `am_expire_silence`."""

    backend_id: str
    silence_id: str
    status: str = "expired"
    expired_by: str = ""
    reason: str = ""
    reactivated_alert_count: int = 0
    reactivated_alerts_preview: List[Dict[str, Any]] = Field(default_factory=list)
    message: str


class PushTestAlertResponse(BaseModel):
    """Structured output for `am_push_test_alert`."""

    backend_id: str
    status: str = "sent"
    alertname: str
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    starts_at: str
    ends_at: str
    resolve_after_minutes: int
    routing_preview: Dict[str, Any] = Field(default_factory=dict)
    message: str
