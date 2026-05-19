"""Rule management data models."""

from typing import Any, Dict, List, Optional

from prometheus_mcp_server.models.common import BasePrometheusModel


class AlertRule(BasePrometheusModel):
    """A single alerting rule."""
    alert: str
    expr: str
    for_duration: Optional[str] = None
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    state: Optional[str] = None  # firing, pending, inactive
    health: Optional[str] = None


class RecordingRule(BasePrometheusModel):
    """A single recording rule."""
    record: str
    expr: str
    labels: Dict[str, str] = {}
    health: Optional[str] = None


class RuleGroup(BasePrometheusModel):
    """A named group of alerting/recording rules."""
    name: str
    file: Optional[str] = None
    interval: Optional[str] = None
    rules: List[Dict[str, Any]] = []
    alert_count: int = 0
    recording_count: int = 0


class RuleGroupList(BasePrometheusModel):
    """List of rule groups from a backend."""
    groups: List[RuleGroup] = []
    total_groups: int = 0
    total_alert_rules: int = 0
    total_recording_rules: int = 0


class RuleValidationResult(BasePrometheusModel):
    """Result of promtool rule validation."""
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    rules_checked: int = 0


class RuleTestResult(BasePrometheusModel):
    """Result of promtool rule unit test."""
    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    errors: List[str] = []
    output: str = ""


class FiringSimulationResult(BasePrometheusModel):
    """Result of alert firing simulation."""
    would_fire: bool
    firing_windows: List[Dict[str, Any]] = []
    pending_windows: List[Dict[str, Any]] = []
    total_firing_duration_seconds: float = 0
    explanation: str = ""


class FiringHistoryAnalysis(BasePrometheusModel):
    """Analysis of alert firing history."""
    alert_name: str
    total_firings: int = 0
    avg_firing_duration_seconds: float = 0
    max_firing_duration_seconds: float = 0
    firing_frequency_per_day: float = 0
    recommendation: str = ""


class DraftAlertRule(BasePrometheusModel):
    """A drafted alert rule with YAML."""
    rule_group_yaml: str
    alert_name: str
    expr: str
    for_duration: str
    severity: str
    annotations: Dict[str, str] = {}
    rationale: str = ""
