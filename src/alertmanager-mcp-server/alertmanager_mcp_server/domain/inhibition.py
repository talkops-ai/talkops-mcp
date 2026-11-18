"""Alertmanager `inhibit_rules` parser and live inhibition evaluator.

Implements Alertmanager `inhibit/inhibit.go` semantics:
1. A target alert must match a rule's `target_match` / `target_match_re` / `target_matchers`.
2. At least one currently firing source alert must match the rule's
   `source_match` / `source_match_re` / `source_matchers`.
3. For every label in `equal`, `source.labels.get(label, "") == target.labels.get(label, "")`.
4. An alert never inhibits itself (and a source alert that also satisfies the
   same rule's `target_matchers` with identical `equal` labels does not inhibit).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from alertmanager_mcp_server.domain.matchers import (
    CompiledMatcher,
    match_all,
    parse_route_matchers,
)


@dataclass(frozen=True)
class CompiledInhibitRule:
    """Pre-compiled Alertmanager inhibition rule."""

    index: int
    source_matchers: tuple[CompiledMatcher, ...]
    target_matchers: tuple[CompiledMatcher, ...]
    equal: tuple[str, ...] = ()

    def target_matches(self, labels: Mapping[str, str]) -> bool:
        """Return True if `labels` matches this rule's target matchers."""
        if not self.target_matchers:
            return False
        return match_all(self.target_matchers, labels)

    def source_matches(self, labels: Mapping[str, str]) -> bool:
        """Return True if `labels` matches this rule's source matchers."""
        if not self.source_matchers:
            return False
        return match_all(self.source_matchers, labels)

    def equal_labels_match(
        self,
        source_labels: Mapping[str, str],
        target_labels: Mapping[str, str],
    ) -> bool:
        """Return True if all `equal` labels have identical values on source and target."""
        for label_name in self.equal:
            if str(source_labels.get(label_name, "")) != str(
                target_labels.get(label_name, "")
            ):
                return False
        return True


@dataclass(frozen=True)
class InhibitionMatchDetail:
    """Details of an active inhibition or potential rule match."""

    rule_index: int
    source_matchers: list[str]
    target_matchers: list[str]
    equal_labels: list[str]
    equal_values: dict[str, str]
    inhibiting_source_fingerprints: list[str] = field(default_factory=list)
    inhibiting_source_alertnames: list[str] = field(default_factory=list)
    active_source_found: bool = False


@dataclass(frozen=True)
class InhibitionEvaluation:
    """Result of evaluating a target alert against all `inhibit_rules` and live alerts."""

    is_inhibited: bool
    inhibiting_Matches: list[InhibitionMatchDetail]
    potential_target_rule_Matches: list[InhibitionMatchDetail]

    @property
    def inhibited_by_fingerprints(self) -> list[str]:
        seen: list[str] = []
        for m in self.inhibiting_Matches:
            for fp in m.inhibiting_source_fingerprints:
                if fp not in seen:
                    seen.append(fp)
        return seen


def parse_inhibit_rules(raw_config: Mapping[str, Any]) -> list[CompiledInhibitRule]:
    """Parse and compile `inhibit_rules` from an Alertmanager configuration dict."""
    raw_rules = raw_config.get("inhibit_rules")
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
        return []

    compiled: list[CompiledInhibitRule] = []
    for idx, rule_dict in enumerate(raw_rules):
        if not isinstance(rule_dict, Mapping):
            continue
        source_matchers = tuple(
            parse_route_matchers(
                rule_dict,
                match_key="source_match",
                match_re_key="source_match_re",
                matchers_key="source_matchers",
            )
        )
        target_matchers = tuple(
            parse_route_matchers(
                rule_dict,
                match_key="target_match",
                match_re_key="target_match_re",
                matchers_key="target_matchers",
            )
        )
        raw_equal = rule_dict.get("equal")
        equal_tuple: tuple[str, ...] = ()
        if isinstance(raw_equal, Sequence) and not isinstance(raw_equal, (str, bytes)):
            equal_tuple = tuple(str(x) for x in raw_equal)

        compiled.append(
            CompiledInhibitRule(
                index=idx,
                source_matchers=source_matchers,
                target_matchers=target_matchers,
                equal=equal_tuple,
            )
        )
    return compiled


def _extract_alert_labels_and_fp(
    alert: Any,
) -> tuple[dict[str, str], str, str]:
    """Extract `(labels, fingerprint, state)` from a dict or `GettableAlert` model."""
    if hasattr(alert, "model_dump"):
        data = getattr(alert, "model_dump")(by_alias=True)
    elif isinstance(alert, Mapping):
        data = dict(alert)
    else:
        return {}, "", "active"

    raw_labels = data.get("labels") or {}
    labels = {str(k): str(v) for k, v in raw_labels.items()} if isinstance(raw_labels, Mapping) else {}
    fp = str(data.get("fingerprint") or "")
    status = data.get("status")
    state = "active"
    if isinstance(status, Mapping) and status.get("state"):
        state = str(status["state"])
    return labels, fp, state


def evaluate_inhibition(
    target_labels: Mapping[str, str],
    rules: Sequence[CompiledInhibitRule],
    active_alerts: Sequence[Mapping[str, Any] | Any] = (),
    *,
    target_fingerprint: str | None = None,
) -> InhibitionEvaluation:
    """Evaluate whether `target_labels` is currently inhibited by any live source alert.

    Args:
        target_labels: Labels of the candidate target alert.
        rules: Compiled `inhibit_rules` from Alertmanager config.
        active_alerts: Currently active/firing alerts from `/api/v2/alerts`.
        target_fingerprint: Optional fingerprint of the target alert to prevent self-match.
    """
    norm_target = {str(k): str(v) for k, v in target_labels.items()}
    active_Matches: list[InhibitionMatchDetail] = []
    potential_Matches: list[InhibitionMatchDetail] = []

    for rule in rules:
        if not rule.target_matches(norm_target):
            continue

        source_fps: list[str] = []
        source_names: list[str] = []

        for alert in active_alerts:
            src_labels, src_fp, _src_state = _extract_alert_labels_and_fp(alert)
            if not src_labels:
                continue

            # An alert never inhibits itself
            if target_fingerprint and src_fp and src_fp == target_fingerprint:
                continue
            if src_labels == norm_target:
                continue

            if not rule.source_matches(src_labels):
                continue

            if not rule.equal_labels_match(src_labels, norm_target):
                continue

            # Alertmanager `inhibit.go`: if the candidate source alert ALSO
            # matches this rule's target_matchers (and equal labels already match),
            # it cannot inhibit the target.
            if rule.target_matches(src_labels):
                continue

            fp_label = src_fp or f"alert:{src_labels.get('alertname', 'unknown')}"
            if fp_label not in source_fps:
                source_fps.append(fp_label)
            alertname = src_labels.get("alertname", "unknown")
            if alertname not in source_names:
                source_names.append(alertname)

        equal_values = {
            lbl: norm_target.get(lbl, "") for lbl in rule.equal
        }
        detail = InhibitionMatchDetail(
            rule_index=rule.index,
            source_matchers=[m.to_filter_string() for m in rule.source_matchers],
            target_matchers=[m.to_filter_string() for m in rule.target_matchers],
            equal_labels=list(rule.equal),
            equal_values=equal_values,
            inhibiting_source_fingerprints=source_fps,
            inhibiting_source_alertnames=source_names,
            active_source_found=len(source_fps) > 0,
        )
        potential_Matches.append(detail)
        if source_fps:
            active_Matches.append(detail)

    return InhibitionEvaluation(
        is_inhibited=len(active_Matches) > 0,
        inhibiting_Matches=active_Matches,
        potential_target_rule_Matches=potential_Matches,
    )
