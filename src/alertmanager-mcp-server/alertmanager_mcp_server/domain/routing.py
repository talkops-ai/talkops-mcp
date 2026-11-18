"""Alertmanager routing tree parser and depth-first `Route.Match` evaluator.

Implements exact Alertmanager `dispatch/route.go` semantics:
- Nested tree structure preserving parent -> child hierarchy
- Inheritance of `receiver`, `group_by`, `group_wait`, `group_interval`, and
  `repeat_interval` from parent routes when omitted on child routes
- Simultaneous support for `match`, `match_re`, and `matchers`
- Exact `continue: false` (stop after first matching child subtree) vs
  `continue: true` (fan-out to subsequent sibling routes)
- Fallback to parent route only when no child route matches
- Evaluation of `mute_time_intervals` and `active_time_intervals` per matched route.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from alertmanager_mcp_server.domain.matchers import (
    CompiledMatcher,
    match_all,
    parse_route_matchers,
)
from alertmanager_mcp_server.domain.time_intervals import TimeIntervalCatalog


@dataclass(frozen=True)
class RouteNode:
    """A single node in the Alertmanager routing tree with inherited settings resolved."""

    path: str
    receiver: str
    matchers: tuple[CompiledMatcher, ...] = ()
    continue_routing: bool = False
    group_by: tuple[str, ...] = ()
    group_wait: str = "30s"
    group_interval: str = "5m"
    repeat_interval: str = "4h"
    mute_time_intervals: tuple[str, ...] = ()
    active_time_intervals: tuple[str, ...] = ()
    children: tuple["RouteNode", ...] = ()
    is_root: bool = False

    def matches_labels(self, labels: Mapping[str, str]) -> bool:
        """Return True if this node's own matchers match `labels`."""
        if self.is_root and not self.matchers:
            return True
        return match_all(self.matchers, labels)


@dataclass(frozen=True)
class RouteStepTrace:
    """Audit trace of one route node visited during routing evaluation."""

    path: str
    receiver: str
    matchers: list[str]
    matched: bool
    continue_routing: bool
    selected: bool
    muted: bool = False
    mute_reasons: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class MatchedRouteDelivery:
    """Details of a single matched terminal route that would receive the alert."""

    path: str
    receiver: str
    group_by: list[str]
    group_wait: str
    group_interval: str
    repeat_interval: str
    muted: bool
    mute_reasons: list[str]
    is_default_route: bool


@dataclass(frozen=True)
class RoutingEvaluation:
    """Complete result of evaluating an alert's labels against a `RouteTree`."""

    matched_routes: list[MatchedRouteDelivery]
    receivers: list[str]
    active_receivers: list[str]
    muted_receivers: list[str]
    fell_back_to_default: bool
    default_receiver: str
    trace: list[RouteStepTrace]


def _normalize_str_tuple(raw: Any, fallback: tuple[str, ...] = ()) -> tuple[str, ...]:
    if raw is None:
        return fallback
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return tuple(str(x) for x in raw)
    return fallback


def build_route_node(
    raw_route: Mapping[str, Any],
    *,
    path: str = "root",
    parent: RouteNode | None = None,
) -> RouteNode:
    """Recursively construct a `RouteNode` with parent parameter inheritance."""
    is_root = parent is None

    receiver = str(
        raw_route.get("receiver")
        or (parent.receiver if parent is not None else "default")
    )

    if "group_by" in raw_route and raw_route.get("group_by") is not None:
        group_by = _normalize_str_tuple(raw_route.get("group_by"))
    elif parent is not None:
        group_by = parent.group_by
    else:
        group_by = ()

    group_wait = str(
        raw_route.get("group_wait")
        or (parent.group_wait if parent is not None else "30s")
    )
    group_interval = str(
        raw_route.get("group_interval")
        or (parent.group_interval if parent is not None else "5m")
    )
    repeat_interval = str(
        raw_route.get("repeat_interval")
        or (parent.repeat_interval if parent is not None else "4h")
    )

    continue_routing = bool(raw_route.get("continue", False))
    mute_intervals = _normalize_str_tuple(raw_route.get("mute_time_intervals"))
    active_intervals = _normalize_str_tuple(raw_route.get("active_time_intervals"))
    matchers = tuple(parse_route_matchers(raw_route))

    temp_node = RouteNode(
        path=path,
        receiver=receiver,
        matchers=matchers,
        continue_routing=continue_routing,
        group_by=group_by,
        group_wait=group_wait,
        group_interval=group_interval,
        repeat_interval=repeat_interval,
        mute_time_intervals=mute_intervals,
        active_time_intervals=active_intervals,
        children=(),
        is_root=is_root,
    )

    raw_children = raw_route.get("routes")
    children: list[RouteNode] = []
    if isinstance(raw_children, Sequence) and not isinstance(raw_children, (str, bytes)):
        for idx, child_dict in enumerate(raw_children):
            if isinstance(child_dict, Mapping):
                child_path = f"{path}/{idx}"
                children.append(
                    build_route_node(
                        child_dict,
                        path=child_path,
                        parent=temp_node,
                    )
                )

    return RouteNode(
        path=temp_node.path,
        receiver=temp_node.receiver,
        matchers=temp_node.matchers,
        continue_routing=temp_node.continue_routing,
        group_by=temp_node.group_by,
        group_wait=temp_node.group_wait,
        group_interval=temp_node.group_interval,
        repeat_interval=temp_node.repeat_interval,
        mute_time_intervals=temp_node.mute_time_intervals,
        active_time_intervals=temp_node.active_time_intervals,
        children=tuple(children),
        is_root=temp_node.is_root,
    )


@dataclass(frozen=True)
class RouteTree:
    """Parsed Alertmanager routing tree and time interval catalog."""

    root: RouteNode
    time_intervals: TimeIntervalCatalog = field(default_factory=TimeIntervalCatalog)

    @classmethod
    def from_config(cls, raw_config: Mapping[str, Any]) -> "RouteTree":
        """Build a `RouteTree` from a parsed Alertmanager configuration dict."""
        raw_root = raw_config.get("route")
        if not isinstance(raw_root, Mapping):
            raw_root = {"receiver": "default"}
        root_node = build_route_node(raw_root, path="root", parent=None)
        intervals = TimeIntervalCatalog.from_config(raw_config)
        return cls(root=root_node, time_intervals=intervals)

    def evaluate(
        self,
        labels: Mapping[str, str],
        *,
        at_time: datetime | None = None,
    ) -> RoutingEvaluation:
        """Evaluate `labels` against the routing tree using Alertmanager `Route.Match`."""
        eval_time = (
            at_time.astimezone(timezone.utc)
            if at_time is not None and at_time.tzinfo is not None
            else (
                at_time.replace(tzinfo=timezone.utc)
                if at_time is not None
                else datetime.now(timezone.utc)
            )
        )

        raw_steps: list[tuple[RouteNode, bool, str]] = []

        def _match_node(node: RouteNode) -> list[RouteNode]:
            matched_self = node.matches_labels(labels)
            if not matched_self:
                raw_steps.append(
                    (
                        node,
                        False,
                        "Matchers did not match alert labels; subtree skipped.",
                    )
                )
                return []

            step_idx = len(raw_steps)
            raw_steps.append((node, True, "Matchers matched; evaluating child routes."))

            child_matches: list[RouteNode] = []
            for child in node.children:
                sub = _match_node(child)
                if sub:
                    child_matches.extend(sub)
                    if not child.continue_routing:
                        break

            if not child_matches:
                reason = (
                    "Matched root default route (no child route matched)."
                    if node.is_root
                    else "Matched route (no deeper child route matched)."
                )
                raw_steps[step_idx] = (node, True, reason)
                return [node]

            raw_steps[step_idx] = (
                node,
                True,
                f"Matched parent route; delegated to {len(child_matches)} child route(s).",
            )
            return child_matches

        selected_nodes = _match_node(self.root)
        selected_paths = {n.path for n in selected_nodes}

        node_mute_map: dict[str, tuple[bool, list[str]]] = {}
        for node in selected_nodes:
            is_muted, reasons = self.time_intervals.evaluate_route_intervals(
                active_time_intervals=node.active_time_intervals,
                mute_time_intervals=node.mute_time_intervals,
                at_time=eval_time,
            )
            node_mute_map[node.path] = (is_muted, reasons)

        trace: list[RouteStepTrace] = []
        for node, matched, reason in raw_steps:
            selected = node.path in selected_paths
            muted, mute_reasons = node_mute_map.get(node.path, (False, []))
            trace.append(
                RouteStepTrace(
                    path=node.path,
                    receiver=node.receiver,
                    matchers=[m.to_filter_string() for m in node.matchers],
                    matched=matched,
                    continue_routing=node.continue_routing,
                    selected=selected,
                    muted=muted,
                    mute_reasons=mute_reasons,
                    reason=reason,
                )
            )

        deliveries: list[MatchedRouteDelivery] = []
        receivers: list[str] = []
        active_receivers: list[str] = []
        muted_receivers: list[str] = []

        for node in selected_nodes:
            muted, mute_reasons = node_mute_map[node.path]
            deliveries.append(
                MatchedRouteDelivery(
                    path=node.path,
                    receiver=node.receiver,
                    group_by=list(node.group_by),
                    group_wait=node.group_wait,
                    group_interval=node.group_interval,
                    repeat_interval=node.repeat_interval,
                    muted=muted,
                    mute_reasons=mute_reasons,
                    is_default_route=node.is_root,
                )
            )
            if node.receiver not in receivers:
                receivers.append(node.receiver)
            if muted:
                if node.receiver not in muted_receivers:
                    muted_receivers.append(node.receiver)
            else:
                if node.receiver not in active_receivers:
                    active_receivers.append(node.receiver)

        fell_back = len(selected_nodes) == 1 and selected_nodes[0].is_root

        return RoutingEvaluation(
            matched_routes=deliveries,
            receivers=receivers,
            active_receivers=active_receivers,
            muted_receivers=muted_receivers,
            fell_back_to_default=fell_back,
            default_receiver=self.root.receiver,
            trace=trace,
        )
