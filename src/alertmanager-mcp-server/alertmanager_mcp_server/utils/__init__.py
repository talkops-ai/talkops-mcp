"""Alertmanager matcher and time window utility helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from alertmanager_mcp_server.domain.matchers import CompiledMatcher
from alertmanager_mcp_server.domain.timeparse import resolve_silence_window
from alertmanager_mcp_server.models.alert import AlertMatcher


def matches_alert(alert_labels: Dict[str, str], matcher: AlertMatcher) -> bool:
    """Check if an alert's labels match a single matcher using `CompiledMatcher`."""
    compiled = CompiledMatcher(
        name=matcher.name,
        value=matcher.value,
        is_regex=matcher.isRegex,
        is_equal=matcher.isEqual,
    )
    return compiled.matches(alert_labels)


def all_matchers_match(
    alert_labels: Dict[str, str], matchers: List[AlertMatcher]
) -> bool:
    """Check if an alert's labels match ALL matchers."""
    return all(matches_alert(alert_labels, m) for m in matchers)


def compute_silence_window(
    duration_minutes: int | None,
    starts_at: datetime | str | None,
    ends_at: datetime | str | None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Compute and validate silence start/end timestamps in UTC."""
    if duration_minutes is None and starts_at is None and ends_at is None:
        raise ValueError(
            "Either duration_minutes or starts_at/ends_at must be provided"
        )
    start_dt, end_dt, _ = resolve_silence_window(
        starts_at=starts_at,
        ends_at=ends_at,
        duration_minutes=duration_minutes,
        now=now,
    )
    return start_dt, end_dt


def derive_matchers_from_labels(
    labels: Dict[str, str],
    priority_keys: tuple[str, ...] = ("alertname", "service", "env"),
) -> List[AlertMatcher]:
    """Derive narrow silence matchers from alert labels."""
    matchers: List[AlertMatcher] = []
    for key in priority_keys:
        if key in labels:
            matchers.append(
                AlertMatcher(
                    name=key,
                    value=labels[key],
                    isRegex=False,
                    isEqual=True,
                )
            )

    if not matchers:
        for k, v in labels.items():
            matchers.append(
                AlertMatcher(
                    name=k, value=v, isRegex=False, isEqual=True
                )
            )

    if not matchers:
        raise ValueError("Cannot derive safe matchers from empty labels")

    return matchers
