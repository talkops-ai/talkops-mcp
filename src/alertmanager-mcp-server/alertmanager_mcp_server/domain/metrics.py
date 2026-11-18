"""Prometheus text exposition parser for Alertmanager `/metrics` telemetry.

Extracts operational health signals that are NOT exposed by `/api/v2/status`:
- `alertmanager_notifications_total{integration="..."}`
- `alertmanager_notifications_failed_total{integration="...", reason="..."}`
- `alertmanager_config_last_reload_successful`
- `alertmanager_config_last_reload_success_timestamp_seconds`
- `alertmanager_cluster_members`
- `alertmanager_cluster_failed_peers`
- `alertmanager_alerts_invalid_total`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_METRIC_LINE_RE = re.compile(
    r"^\s*([a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{([^}]*)\})?\s+"
    r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|NaN|[+-]Inf)"
    r"(?:\s+\d+)?\s*$"
)

_LABEL_PAIR_RE = re.compile(
    r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"((?:\\.|[^"\\])*)"'
)


@dataclass
class IntegrationDeliveryStats:
    """Notification delivery counters for a single receiver integration type."""

    integration: str
    notifications_total: float = 0.0
    notifications_failed_total: float = 0.0
    failures_by_reason: dict[str, float] = field(default_factory=dict)

    @property
    def failure_rate(self) -> float:
        if self.notifications_failed_total <= 0:
            return 0.0
        denom = (
            self.notifications_total
            if self.notifications_total >= self.notifications_failed_total
            else self.notifications_total + self.notifications_failed_total
        )
        if denom <= 0:
            return 1.0
        return round(self.notifications_failed_total / denom, 4)

    @property
    def healthy(self) -> bool:
        return self.notifications_failed_total == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "integration": self.integration,
            "notifications_total": int(self.notifications_total),
            "notifications_failed_total": int(self.notifications_failed_total),
            "failure_rate": self.failure_rate,
            "healthy": self.healthy,
            "failures_by_reason": {
                k: int(v) for k, v in sorted(self.failures_by_reason.items())
            },
        }


@dataclass
class AlertmanagerMetricsSummary:
    """Structured summary of Alertmanager `/metrics` exposition."""

    config_last_reload_successful: bool | None = None
    config_last_reload_timestamp: str | None = None
    cluster_members: int | None = None
    cluster_failed_peers: int | None = None
    invalid_alerts_total: int = 0
    integrations: dict[str, IntegrationDeliveryStats] = field(default_factory=dict)

    @property
    def total_notifications(self) -> int:
        return int(
            sum(s.notifications_total for s in self.integrations.values())
        )

    @property
    def total_failed_notifications(self) -> int:
        return int(
            sum(s.notifications_failed_total for s in self.integrations.values())
        )

    @property
    def degraded_integrations(self) -> list[str]:
        return sorted(
            name
            for name, stats in self.integrations.items()
            if not stats.healthy
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_last_reload_successful": self.config_last_reload_successful,
            "config_last_reload_timestamp": self.config_last_reload_timestamp,
            "cluster_members": self.cluster_members,
            "cluster_failed_peers": self.cluster_failed_peers,
            "invalid_alerts_total": self.invalid_alerts_total,
            "total_notifications": self.total_notifications,
            "total_failed_notifications": self.total_failed_notifications,
            "degraded_integrations": self.degraded_integrations,
            "integrations": {
                k: v.to_dict() for k, v in sorted(self.integrations.items())
            },
        }


def _parse_labels(raw_labels: str | None) -> dict[str, str]:
    if not raw_labels:
        return {}
    return {
        m.group(1): m.group(2).replace('\\"', '"').replace("\\\\", "\\")
        for m in _LABEL_PAIR_RE.finditer(raw_labels)
    }


def parse_prometheus_metrics(text: str) -> AlertmanagerMetricsSummary:
    """Parse Prometheus text exposition output from Alertmanager `/metrics`."""
    summary = AlertmanagerMetricsSummary()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _METRIC_LINE_RE.match(line)
        if not m:
            continue

        metric_name, raw_labels, raw_val = m.group(1), m.group(2), m.group(3)
        try:
            value = float(raw_val)
        except ValueError:
            continue

        labels = _parse_labels(raw_labels)

        if metric_name == "alertmanager_notifications_total":
            integration = labels.get("integration", "unknown")
            stats = summary.integrations.setdefault(
                integration, IntegrationDeliveryStats(integration=integration)
            )
            stats.notifications_total += value

        elif metric_name == "alertmanager_notifications_failed_total":
            integration = labels.get("integration", "unknown")
            reason = labels.get("reason")
            stats = summary.integrations.setdefault(
                integration, IntegrationDeliveryStats(integration=integration)
            )
            stats.notifications_failed_total += value
            if reason:
                stats.failures_by_reason[reason] = (
                    stats.failures_by_reason.get(reason, 0.0) + value
                )

        elif metric_name == "alertmanager_config_last_reload_successful":
            summary.config_last_reload_successful = value >= 1.0

        elif (
            metric_name
            == "alertmanager_config_last_reload_success_timestamp_seconds"
        ):
            if value > 0:
                dt = datetime.fromtimestamp(value, tz=timezone.utc)
                summary.config_last_reload_timestamp = dt.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )

        elif metric_name == "alertmanager_cluster_members":
            summary.cluster_members = int(value)

        elif metric_name == "alertmanager_cluster_failed_peers":
            summary.cluster_failed_peers = int(value)

        elif metric_name == "alertmanager_alerts_invalid_total":
            summary.invalid_alerts_total = int(value)

    return summary
