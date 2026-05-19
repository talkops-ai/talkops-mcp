"""Alertmanager matcher utility functions."""

import re
from typing import Dict, List
from datetime import datetime, timedelta, timezone

from alertmanager_mcp_server.models.alert import AlertMatcher


def matches_alert(alert_labels: Dict[str, str], matcher: AlertMatcher) -> bool:
    """Check if an alert's labels match a single matcher."""
    val = alert_labels.get(matcher.name, "")
    if matcher.isRegex:
        pattern = f"^{matcher.value}$"
        match = bool(re.match(pattern, val))
    else:
        match = val == matcher.value
    return match if matcher.isEqual else not match


def all_matchers_match(alert_labels: Dict[str, str], matchers: List[AlertMatcher]) -> bool:
    """Check if an alert's labels match ALL matchers."""
    return all(matches_alert(alert_labels, m) for m in matchers)


def compute_silence_window(
    duration_minutes: int | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Compute silence start/end timestamps from duration or explicit window."""
    if now is None:
        now = datetime.now(timezone.utc)

    if duration_minutes is not None:
        return now, now + timedelta(minutes=duration_minutes)

    if starts_at and ends_at:
        return starts_at, ends_at

    raise ValueError("Either duration_minutes or starts_at/ends_at must be provided")


def derive_matchers_from_labels(
    labels: Dict[str, str],
    priority_keys: tuple[str, ...] = ("alertname", "service", "env"),
) -> List[AlertMatcher]:
    """Derive narrow silence matchers from alert labels.

    Uses priority_keys to select the most specific matchers,
    falling back to all labels if no priority keys are found.
    """
    matchers: List[AlertMatcher] = []
    for key in priority_keys:
        if key in labels:
            matchers.append(AlertMatcher(name=key, value=labels[key], isRegex=False, isEqual=True))

    if not matchers:
        # Fallback: use all labels
        for k, v in labels.items():
            matchers.append(AlertMatcher(name=k, value=v, isRegex=False, isEqual=True))

    if not matchers:
        raise ValueError("Cannot derive safe matchers from empty labels")

    return matchers
