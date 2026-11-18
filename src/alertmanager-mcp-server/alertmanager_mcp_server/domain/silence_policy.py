"""Alertmanager Silence Safety & Governance Policy Engine (`SP001`–`SP010`).

Evaluates silence requests and active silences against operational safety rules:
- SP001: Non-empty matcher list required
- SP002: At least one positive matcher that does not match empty string (`""`)
- SP003: No wildcard regex matchers (`.*`, `.+`, `^.*$`)
- SP004: Cannot scope a silence solely by broad environment/severity/cluster labels
- SP005: Cannot silence the dead-man's-switch / Watchdog heartbeat alert
- SP006: Valid RFC3339 timestamps with explicit timezone offsets and `ends_at > starts_at`
- SP007: Total duration `(ends_at - starts_at)` <= `max_duration_minutes`
- SP008: Explicit non-placeholder `created_by` attribution required
- SP009: Actionable `comment` required (plus optional `comment_pattern` regex check)
- SP010: High blast-radius / unscoped critical silence confirmation gate
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Sequence

from alertmanager_mcp_server.domain.matchers import (
    CompiledMatcher,
    MatcherValidationError,
    parse_matcher_set,
)
from alertmanager_mcp_server.domain.timeparse import (
    TimeValidationError,
    format_rfc3339_utc,
    resolve_silence_window,
)

PolicySeverity = Literal["error", "warning"]

DEFAULT_FORBIDDEN_SOLE_LABELS: tuple[str, ...] = (
    "severity",
    "env",
    "environment",
    "cluster",
    "region",
    "datacenter",
)

DEFAULT_WATCHDOG_NAMES: tuple[str, ...] = (
    "Watchdog",
    "DeadMansSwitch",
    "AlertmanagerWatchdog",
)

_PLACEHOLDER_AUTHORS = frozenset({"", "mcp", "anonymous", "unknown", "default", "none"})
_TICKET_HINT_RE = re.compile(
    r"(?:[A-Z][A-Z0-9]+-\d+|INC\d+|CHG\d+|PR-\d+|#\d+|https?://)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PolicyViolation:
    """Single silence policy violation or warning."""

    rule_id: str
    severity: PolicySeverity
    message: str
    remediation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class SilencePolicyResult:
    """Result of evaluating a silence against `SilencePolicy`."""

    valid: bool
    requires_confirmation: bool
    confirmation_reasons: list[str]
    violations: list[PolicyViolation]
    warnings: list[PolicyViolation]
    compiled_matchers: list[CompiledMatcher] = field(default_factory=list)
    starts_at_utc: str | None = None
    ends_at_utc: str | None = None
    duration_minutes: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_reasons": list(self.confirmation_reasons),
            "violations": [v.to_dict() for v in self.violations],
            "warnings": [w.to_dict() for w in self.warnings],
            "matchers": [m.to_api_dict() for m in self.compiled_matchers],
            "starts_at": self.starts_at_utc,
            "ends_at": self.ends_at_utc,
            "duration_minutes": (
                round(self.duration_minutes, 2)
                if self.duration_minutes is not None
                else None
            ),
        }


@dataclass(frozen=True)
class SilencePolicy:
    """Configurable silence policy evaluator."""

    max_duration_minutes: int = 1440
    confirm_threshold: int = 50
    forbidden_sole_labels: tuple[str, ...] = DEFAULT_FORBIDDEN_SOLE_LABELS
    watchdog_alertname: str = "Watchdog"
    comment_pattern: str | None = None

    def evaluate(
        self,
        *,
        matchers: str | Sequence[Any] | Mapping[str, Any] | None,
        starts_at: str | datetime | None = None,
        ends_at: str | datetime | None = None,
        duration_minutes: int | None = None,
        created_by: str | None = None,
        comment: str | None = None,
        matched_alert_count: int = 0,
        matched_critical_count: int = 0,
        now: datetime | None = None,
        validate_window: bool = True,
    ) -> SilencePolicyResult:
        """Evaluate a silence candidate and return structured errors, warnings, and gates."""
        errors: list[PolicyViolation] = []
        warnings: list[PolicyViolation] = []
        confirmation_reasons: list[str] = []
        compiled: list[CompiledMatcher] = []

        # 1. Parse and validate matchers (SP001 - SP005)
        try:
            compiled = parse_matcher_set(matchers)
        except MatcherValidationError as exc:
            errors.append(
                PolicyViolation(
                    rule_id="SP001",
                    severity="error",
                    message=str(exc),
                    remediation=(
                        "Provide valid Alertmanager matchers with label names matching "
                        "[a-zA-Z_][a-zA-Z0-9_]* and RE2-compatible regular expressions."
                    ),
                )
            )

        if not compiled and not errors:
            errors.append(
                PolicyViolation(
                    rule_id="SP001",
                    severity="error",
                    message="Silence must contain at least one label matcher.",
                    remediation=(
                        "Add at least one specific positive matcher such as "
                        "alertname=\"HighErrorRate\" or service=\"checkout\"."
                    ),
                )
            )

        if compiled:
            # SP003: Wildcard regex check
            for m in compiled:
                if m.is_wildcard_regex():
                    errors.append(
                        PolicyViolation(
                            rule_id="SP003",
                            severity="error",
                            message=(
                                f"Matcher '{m.to_filter_string()}' uses an unanchored wildcard "
                                "regex that matches every value."
                            ),
                            remediation=(
                                f"Replace '{m.to_filter_string()}' with an explicit value or "
                                f"bounded alternation (e.g. {m.name}=~\"svc-a|svc-b\")."
                            ),
                        )
                    )

            # SP002: At least one matcher must be positive and not match empty string
            non_empty_positive = [
                m for m in compiled if m.is_equal and not m.matches_empty()
            ]
            if not non_empty_positive:
                errors.append(
                    PolicyViolation(
                        rule_id="SP002",
                        severity="error",
                        message=(
                            "Silence has no positive matcher that excludes empty label values. "
                            "Alertmanager rejects silences where all matchers can match ''."
                        ),
                        remediation=(
                            "Include at least one positive matcher (= or =~) that does not "
                            "match the empty string, such as alertname or service."
                        ),
                    )
                )

            # SP004: Forbidden sole broad labels
            if non_empty_positive:
                forbidden_set = {lbl.lower() for lbl in self.forbidden_sole_labels}
                pos_names = {m.name.lower() for m in non_empty_positive}
                if pos_names.issubset(forbidden_set):
                    errors.append(
                        PolicyViolation(
                            rule_id="SP004",
                            severity="error",
                            message=(
                                "Silence is scoped solely by broad organizational labels "
                                f"({sorted(pos_names)}), which would mute an entire environment, "
                                "cluster, or severity tier."
                            ),
                            remediation=(
                                "Add a narrowing matcher such as 'alertname', 'service', "
                                "'instance', 'job', or 'namespace'."
                            ),
                        )
                    )

            # SP005: Watchdog / DeadMansSwitch protection
            watchdog_candidates = tuple(
                dict.fromkeys(
                    name
                    for name in (*DEFAULT_WATCHDOG_NAMES, self.watchdog_alertname)
                    if name
                )
            )
            watchdog_lower = {name.lower() for name in watchdog_candidates}
            for m in compiled:
                if m.name == "alertname" and m.is_equal and not m.is_wildcard_regex():
                    if not m.is_regex and m.value.lower() in watchdog_lower:
                        errors.append(
                            PolicyViolation(
                                rule_id="SP005",
                                severity="error",
                                message=(
                                    f"Silencing heartbeat alert '{m.value}' is prohibited "
                                    "because it masks dead-man's-switch pipeline failures."
                                ),
                                remediation=(
                                    "Never silence the Watchdog/DeadMansSwitch alert. "
                                    'Exclude it with alertname!="Watchdog" if needed.'
                                ),
                            )
                        )
                    elif m.is_regex and any(
                        m.matches_value(wd) or m.matches_value(wd.lower())
                        for wd in watchdog_candidates
                    ):
                        errors.append(
                            PolicyViolation(
                                rule_id="SP005",
                                severity="error",
                                message=(
                                    f"Regex matcher '{m.to_filter_string()}' matches "
                                    f"heartbeat alert '{self.watchdog_alertname}'."
                                ),
                                remediation=(
                                    "Narrow the alertname regex so it does not match "
                                    f"'{self.watchdog_alertname}'."
                                ),
                            )
                        )

        # 2. Validate time window and duration cap (SP006 & SP007)
        starts_utc: str | None = None
        ends_utc: str | None = None
        total_minutes: float | None = None

        if validate_window:
            try:
                start_dt, end_dt, total_minutes = resolve_silence_window(
                    starts_at=starts_at,
                    ends_at=ends_at,
                    duration_minutes=duration_minutes,
                    now=now,
                )
                starts_utc = format_rfc3339_utc(start_dt)
                ends_utc = format_rfc3339_utc(end_dt)

                if total_minutes > self.max_duration_minutes:
                    errors.append(
                        PolicyViolation(
                            rule_id="SP007",
                            severity="error",
                            message=(
                                f"Silence duration ({total_minutes:.1f} minutes) exceeds maximum "
                                f"allowed duration ({self.max_duration_minutes} minutes)."
                            ),
                            remediation=(
                                f"Reduce duration_minutes or ends_at so the total window is "
                                f"at most {self.max_duration_minutes} minutes. For long-term "
                                "suppression, update routing mute_time_intervals or alert rules."
                            ),
                        )
                    )
            except TimeValidationError as exc:
                errors.append(
                    PolicyViolation(
                        rule_id="SP006",
                        severity="error",
                        message=str(exc),
                        remediation=(
                            "Provide valid RFC3339 timestamps with explicit timezone offsets "
                            "(e.g. '2026-03-29T10:00:00Z') where ends_at > starts_at and "
                            "ends_at is in the future."
                        ),
                    )
                )

        # 3. Validate author attribution (SP008)
        author_clean = (created_by or "").strip()
        if author_clean.lower() in _PLACEHOLDER_AUTHORS:
            errors.append(
                PolicyViolation(
                    rule_id="SP008",
                    severity="error",
                    message=(
                        "Silence requires explicit author attribution in 'created_by' "
                        f"(got '{created_by or ''}')."
                    ),
                    remediation=(
                        "Pass the operator identity, email, or incident responder handle "
                        "in 'created_by' (e.g. 'oncall-sre@example.com')."
                    ),
                )
            )

        # 4. Validate comment / ticket reference (SP009)
        comment_clean = (comment or "").strip()
        if len(comment_clean) < 3:
            errors.append(
                PolicyViolation(
                    rule_id="SP009",
                    severity="error",
                    message="Silence requires a descriptive 'comment' (minimum 3 characters).",
                    remediation=(
                        "Provide the maintenance ticket ID, incident link, or operational "
                        "reason in 'comment' (e.g. 'CHG-1042: Planned DB replica upgrade')."
                    ),
                )
            )
        elif self.comment_pattern:
            if not re.search(self.comment_pattern, comment_clean):
                errors.append(
                    PolicyViolation(
                        rule_id="SP009",
                        severity="error",
                        message=(
                            f"Silence comment '{comment_clean}' does not match required "
                            f"governance pattern '{self.comment_pattern}'."
                        ),
                        remediation=(
                            f"Include a matching ticket or change reference satisfying "
                            f"'{self.comment_pattern}'."
                        ),
                    )
                )
        elif not _TICKET_HINT_RE.search(comment_clean):
            warnings.append(
                PolicyViolation(
                    rule_id="SP009",
                    severity="warning",
                    message=(
                        "Silence comment does not reference an incident, change, or ticket ID "
                        "(e.g. JIRA-123, INC001, CHG-42, #123)."
                    ),
                    remediation=(
                        "Consider including a ticket ID or runbook/incident URL in the "
                        "silence comment for post-incident auditability."
                    ),
                )
            )

        # 5. Blast-radius & critical-scope confirmation gate (SP010)
        if matched_alert_count >= self.confirm_threshold:
            reason = (
                f"Silence matches {matched_alert_count} active alerts, which meets or "
                f"exceeds the blast-radius confirmation threshold ({self.confirm_threshold})."
            )
            confirmation_reasons.append(reason)
            warnings.append(
                PolicyViolation(
                    rule_id="SP010",
                    severity="warning",
                    message=reason,
                    remediation=(
                        "Verify the affected alert list via am_preview_silence and confirm "
                        "execution (or narrow the matchers to specific instances)."
                    ),
                )
            )

        has_narrow_scope = any(
            m.is_equal and m.name in ("instance", "pod", "alertname")
            for m in compiled
        )
        if matched_critical_count > 0 and not has_narrow_scope:
            reason = (
                f"Silence mutes {matched_critical_count} active critical alert(s) without "
                "scoping to a specific 'alertname', 'instance', or 'pod'."
            )
            confirmation_reasons.append(reason)
            warnings.append(
                PolicyViolation(
                    rule_id="SP010",
                    severity="warning",
                    message=reason,
                    remediation=(
                        "Scope critical alert silences by 'alertname' or 'instance', or "
                        "explicitly confirm the broad critical silence."
                    ),
                )
            )

        return SilencePolicyResult(
            valid=len(errors) == 0,
            requires_confirmation=len(confirmation_reasons) > 0,
            confirmation_reasons=confirmation_reasons,
            violations=errors,
            warnings=warnings,
            compiled_matchers=compiled,
            starts_at_utc=starts_utc,
            ends_at_utc=ends_utc,
            duration_minutes=total_minutes,
        )
