"""Alertmanager HTTP API v2 client service."""

import asyncio
import logging
import re
import yaml
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Literal

import httpx

from alertmanager_mcp_server.config import BackendConfig, ServerConfig
from alertmanager_mcp_server.models.alert import AlertGroup, AlertMatcher, GettableAlert
from alertmanager_mcp_server.models.backend import BackendDescriptor
from alertmanager_mcp_server.models.config import (
    AlertmanagerConfigSnapshot, InhibitionRule, ReceiverConfig,
    RoutingExplanation, RoutingRoute, RoutingSimulationResult,
    RoutingTreeNode, SilenceChange,
)
from alertmanager_mcp_server.models.silence import GettableSilence, PostableSilence, SilenceEffectPreview

logger = logging.getLogger(__name__)

# Keys that should be redacted from receiver configs and status payloads.
_REDACT_KEYS = frozenset({
    "secret", "password", "token", "api_key", "api_url",
    "routing_key", "service_key", "webhook_url", "url",
    "auth_password", "auth_username", "auth_secret",
    "pagerduty_url", "opsgenie_api_url",
})

# Map receiver config keys to their type name.
_RECEIVER_TYPE_MAP = {
    "slack_configs": "slack",
    "pagerduty_configs": "pagerduty",
    "email_configs": "email",
    "webhook_configs": "webhook",
    "opsgenie_configs": "opsgenie",
    "victorops_configs": "victorops",
    "pushover_configs": "pushover",
    "wechat_configs": "wechat",
    "sns_configs": "sns",
    "telegram_configs": "telegram",
    "msteams_configs": "msteams",
    "discord_configs": "discord",
    "webex_configs": "webex",
}


def _redact_dict(data: Any) -> Any:
    """Recursively redact sensitive keys from dicts."""
    if isinstance(data, dict):
        return {
            k: "***REDACTED***" if k.lower() in _REDACT_KEYS else _redact_dict(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_redact_dict(item) for item in data]
    return data


class AlertmanagerService:
    """Async wrapper around the Alertmanager HTTP API v2."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._backends: Dict[str, BackendConfig] = {b.id: b for b in config.backends}
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._max_retries = 2
        self._retry_backoff = 0.5

    def _get_backend(self, backend_id: str) -> BackendConfig:
        backend = self._backends.get(backend_id)
        if not backend:
            raise ValueError(f"Unknown backend_id '{backend_id}'. Available: {list(self._backends.keys())}")
        return backend

    def _get_default_backend(self) -> BackendConfig:
        """Return the default backend or the first one."""
        for b in self._backends.values():
            if b.is_default:
                return b
        if self._backends:
            return next(iter(self._backends.values()))
        raise ValueError("No Alertmanager backends configured")

    def _ensure_client(self, backend_id: str) -> httpx.AsyncClient:
        if backend_id not in self._clients or self._clients[backend_id].is_closed:
            backend = self._get_backend(backend_id)
            self._clients[backend_id] = httpx.AsyncClient(
                base_url=backend.base_url.rstrip("/"),
                verify=backend.verify_ssl,
                timeout=backend.timeout,
            )
        return self._clients[backend_id]

    def _headers(self, backend: BackendConfig) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if backend.auth_header:
            headers["Authorization"] = backend.auth_header
        return headers

    async def _request(self, method: str, backend_id: str, path: str, **kwargs: Any) -> httpx.Response:
        """Make an HTTP request with retry logic and exponential backoff on 5xx errors."""
        backend = self._get_backend(backend_id)
        client = self._ensure_client(backend_id)
        headers = self._headers(backend)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.request(method, path, headers=headers, **kwargs)

                # Retry on 5xx server errors
                if resp.status_code >= 500 and attempt < self._max_retries:
                    logger.warning(
                        "Alertmanager %s %s returned %d, retrying (%d/%d)",
                        method, path, resp.status_code, attempt + 1, self._max_retries,
                    )
                    await asyncio.sleep(self._retry_backoff * (attempt + 1))
                    continue

                if resp.status_code >= 400:
                    raise RuntimeError(f"Alertmanager API error {resp.status_code}: {resp.text[:500]}")
                return resp
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    raise
                logger.warning(
                    "Alertmanager %s %s failed with %s, retrying (%d/%d)",
                    method, path, type(exc).__name__, attempt + 1, self._max_retries,
                )
                await asyncio.sleep(self._retry_backoff * (attempt + 1))

        assert last_exc is not None
        raise last_exc

    async def close(self) -> None:
        """Gracefully close all HTTP clients."""
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()
        logger.info("All Alertmanager HTTP clients closed.")

    # ---- Backend Discovery ----

    def list_backends(self) -> List[BackendDescriptor]:
        return [
            BackendDescriptor(
                id=b.id, display_name=b.display_name or b.id,
                base_url=b.base_url, labels=b.labels, is_default=b.is_default,
            )
            for b in self._backends.values()
        ]

    async def check_health(self, backend_id: str) -> Literal["unknown", "healthy", "degraded", "unhealthy"]:
        try:
            resp = await self._request("GET", backend_id, "/-/healthy")
            return "healthy" if resp.status_code == 200 else "degraded"
        except Exception:
            return "unhealthy"

    async def get_status(self, backend_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", backend_id, "/api/v2/status")
        return resp.json()

    # ---- Alerts ----

    async def list_alerts(
        self, backend_id: str,
        matchers: Optional[List[AlertMatcher]] = None,
        active: Optional[bool] = True, silenced: Optional[bool] = None,
        inhibited: Optional[bool] = None, unprocessed: Optional[bool] = None,
        receiver: Optional[str] = None, limit: int = 50, offset: int = 0,
    ) -> Tuple[List[GettableAlert], bool, Optional[int]]:
        params: Dict[str, Any] = {}
        if matchers:
            filters = []
            for m in matchers:
                op = "=~" if m.isRegex else "="
                if not m.isEqual:
                    op = "!~" if m.isRegex else "!="
                filters.append(f'{m.name}{op}"{m.value}"')
            params["filter"] = filters
        if active is not None:
            params["active"] = str(active).lower()
        if silenced is not None:
            params["silenced"] = str(silenced).lower()
        if inhibited is not None:
            params["inhibited"] = str(inhibited).lower()
        if unprocessed is not None:
            params["unprocessed"] = str(unprocessed).lower()
        if receiver:
            params["receiver"] = receiver

        resp = await self._request("GET", backend_id, "/api/v2/alerts", params=params)
        raw = resp.json()
        page = raw[offset: offset + limit]
        has_more = offset + limit < len(raw)
        next_offset = offset + limit if has_more else None
        alerts = [GettableAlert(**a) for a in page]
        return alerts, has_more, next_offset

    async def list_alert_groups(self, backend_id: str, max_alerts_per_group: int = 20) -> List[AlertGroup]:
        """List alert groups with a cap on alerts per group to protect context."""
        resp = await self._request("GET", backend_id, "/api/v2/alerts/groups")
        data = resp.json()
        return [
            AlertGroup(
                labels=g.get("labels", {}),
                alerts=[GettableAlert(**a) for a in g.get("alerts", [])[:max_alerts_per_group]],
            )
            for g in data
        ]

    async def push_alerts(self, backend_id: str, alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
        resp = await self._request("POST", backend_id, "/api/v2/alerts", json=alerts)
        return resp.json() if resp.content else {}

    # ---- Silences ----

    async def list_silences(
        self, backend_id: str, state: Optional[str] = None,
        limit: int = 50, offset: int = 0,
    ) -> Tuple[List[GettableSilence], bool, Optional[int]]:
        """List silences with optional state filter and pagination."""
        params: Dict[str, Any] = {}
        if state:
            # Alertmanager v2 doesn't natively support status filter in query;
            # we filter server-side after fetching all silences.
            pass
        resp = await self._request("GET", backend_id, "/api/v2/silences", params=params)
        raw_silences = resp.json()

        # Server-side state filtering
        if state:
            raw_silences = [s for s in raw_silences if s.get("status", {}).get("state") == state]

        # Pagination
        page = raw_silences[offset: offset + limit]
        has_more = offset + limit < len(raw_silences)
        next_offset = offset + limit if has_more else None
        silences = [GettableSilence(**s) for s in page]
        return silences, has_more, next_offset

    async def get_silence(self, backend_id: str, silence_id: str) -> GettableSilence:
        resp = await self._request("GET", backend_id, f"/api/v2/silence/{silence_id}")
        return GettableSilence(**resp.json())

    async def find_duplicate_silence(
        self, backend_id: str, matchers: List[AlertMatcher],
    ) -> Optional[GettableSilence]:
        """Check if an equivalent active silence already exists (dedup)."""
        silences, _, _ = await self.list_silences(backend_id, state="active", limit=500)
        matcher_set = {(m.name, m.value, m.isRegex, m.isEqual) for m in matchers}
        for s in silences:
            existing_set = {(m.name, m.value, m.isRegex, m.isEqual) for m in s.matchers}
            if existing_set == matcher_set:
                return s
        return None

    async def create_silence(self, backend_id: str, silence: PostableSilence) -> GettableSilence:
        payload = silence.model_dump(mode="json")
        resp = await self._request("POST", backend_id, "/api/v2/silences", json=payload)
        created = resp.json()
        if isinstance(created, dict):
            silence_id = created.get("silenceID") or created.get("id")
            if silence_id:
                return await self.get_silence(backend_id, silence_id)
        return GettableSilence(**created)

    async def delete_silence(self, backend_id: str, silence_id: str) -> None:
        await self._request("DELETE", backend_id, f"/api/v2/silence/{silence_id}")

    # ---- Receivers / Config ----

    async def get_receivers(self, backend_id: str) -> List[ReceiverConfig]:
        """Get receivers with type inference and secret redaction.

        Parses the full YAML configuration from /api/v2/status to extract
        receiver integration configs (slack_configs, pagerduty_configs, etc.).
        The bare /api/v2/receivers endpoint only returns names, so we use
        the config source for rich type inference and redacted details.
        """
        # Step 1: Parse the full config YAML to get receiver definitions
        receiver_configs: Dict[str, Dict[str, Any]] = {}
        try:
            status = await self.get_status(backend_id)
            config_raw = status.get("config", {})
            config_str = config_raw.get("original", "") if isinstance(config_raw, dict) else ""
            if config_str:
                parsed = yaml.safe_load(config_str)
                if parsed and isinstance(parsed, dict):
                    for rcv in parsed.get("receivers", []) or []:
                        if isinstance(rcv, dict) and "name" in rcv:
                            receiver_configs[rcv["name"]] = rcv
        except Exception as exc:
            logger.warning("Failed to parse receivers from config YAML: %s", exc)

        # Step 2: Get receiver names from the API (guaranteed list)
        resp = await self._request("GET", backend_id, "/api/v2/receivers")
        api_receivers = resp.json()

        # Step 3: Merge — enrich API names with config details
        receivers: List[ReceiverConfig] = []
        for r in api_receivers:
            name = r.get("name", "unknown")
            # Prefer config YAML data for this receiver if available
            source: Dict[str, Any] = receiver_configs.get(name) or r

            # Infer receiver type from config keys
            r_type: Optional[str] = None
            for config_key, type_name in _RECEIVER_TYPE_MAP.items():
                if config_key in source and source[config_key]:
                    r_type = type_name
                    break

            # Redact sensitive fields from config details
            details = _redact_dict({
                k: v for k, v in source.items() if k != "name"
            })
            receivers.append(ReceiverConfig(name=name, type=r_type, details=details))
        return receivers

    async def get_config_snapshot(self, backend_id: str) -> AlertmanagerConfigSnapshot:
        """Parse the active config from /api/v2/status into routes and inhibitions."""
        status = await self.get_status(backend_id)
        routes: List[RoutingRoute] = []
        inhibitions: List[InhibitionRule] = []

        try:
            # The config can be in 'config.original' (YAML string) or 'configJSON'
            config_raw = status.get("config", {})
            config_str = config_raw.get("original", "") if isinstance(config_raw, dict) else ""

            if config_str:
                parsed = yaml.safe_load(config_str)
                if parsed and isinstance(parsed, dict):
                    # Parse routing tree
                    route_section = parsed.get("route", {})
                    routes = self._parse_routes(route_section)

                    # Parse inhibition rules
                    inhibit_rules = parsed.get("inhibit_rules", [])
                    for rule in (inhibit_rules or []):
                        inhibitions.append(InhibitionRule(
                            source_matchers=self._parse_matchers_from_config(rule.get("source_matchers", rule.get("source_match", {}))),
                            target_matchers=self._parse_matchers_from_config(rule.get("target_matchers", rule.get("target_match", {}))),
                            equal=rule.get("equal", []),
                        ))
        except Exception as exc:
            logger.warning("Failed to parse Alertmanager config: %s", exc)

        return AlertmanagerConfigSnapshot(routes=routes, inhibitions=inhibitions)

    def _parse_routes(self, route_data: Dict[str, Any], depth: int = 0) -> List[RoutingRoute]:
        """Recursively parse the routing tree into flat RoutingRoute list."""
        if not route_data or not isinstance(route_data, dict):
            return []

        routes: List[RoutingRoute] = []
        matchers = self._parse_matchers_from_config(
            route_data.get("matchers", route_data.get("match", {}))
        )
        routes.append(RoutingRoute(
            matchers=matchers,
            receiver=route_data.get("receiver"),
            group_by=route_data.get("group_by", []),
            group_wait=route_data.get("group_wait"),
            group_interval=route_data.get("group_interval"),
            repeat_interval=route_data.get("repeat_interval"),
        ))

        # Recurse into child routes
        for child in route_data.get("routes", []) or []:
            routes.extend(self._parse_routes(child, depth + 1))

        return routes

    @staticmethod
    def _parse_matchers_from_config(match_data: Any) -> List[AlertMatcher]:
        """Parse matchers from various Alertmanager config formats."""
        if not match_data:
            return []

        matchers: List[AlertMatcher] = []

        # Format 1: dict of key=value (old match/match_re style)
        if isinstance(match_data, dict):
            for k, v in match_data.items():
                matchers.append(AlertMatcher(name=k, value=str(v), isRegex=False, isEqual=True))
            return matchers

        # Format 2: list of matcher strings like 'alertname="foo"' or 'env=~"prod.*"'
        if isinstance(match_data, list):
            for m in match_data:
                if isinstance(m, str):
                    parsed = AlertmanagerService._parse_matcher_string(m)
                    if parsed:
                        matchers.append(parsed)
                elif isinstance(m, dict):
                    matchers.append(AlertMatcher(
                        name=m.get("name", ""),
                        value=m.get("value", ""),
                        isRegex=m.get("isRegex", False),
                        isEqual=m.get("isEqual", True),
                    ))
        return matchers

    @staticmethod
    def _parse_matcher_string(s: str) -> Optional[AlertMatcher]:
        """Parse a single matcher string like 'alertname="Watchdog"' or 'env=~"prod.*"'."""
        # Match patterns: name=~"val", name!~"val", name="val", name!="val"
        pattern = r'^(\w+)\s*(=~|!~|!=|=)\s*"?([^"]*)"?$'
        match = re.match(pattern, s.strip())
        if not match:
            return None
        name, op, value = match.groups()
        return AlertMatcher(
            name=name,
            value=value,
            isRegex=op in ("=~", "!~"),
            isEqual=op in ("=", "=~"),
        )

    async def simulate_routing(self, backend_id: str, alert_labels: Dict[str, str]) -> RoutingSimulationResult:
        """Best-effort routing simulation based on config snapshot.

        NOTE: This is an approximation of Alertmanager's internal routing engine.
        For authoritative end-to-end validation, use push_test_alert.
        """
        config = await self.get_config_snapshot(backend_id)

        matched_receivers: List[str] = []
        route_path_parts: List[str] = []
        inhibited_by: List[str] = []

        # Walk routes and find matching receivers
        if config.routes:
            self._walk_routes(config.routes, alert_labels, matched_receivers, route_path_parts)

        # If nothing matched, fall back to root receiver
        if not matched_receivers and config.routes:
            root = config.routes[0]
            if root.receiver:
                matched_receivers.append(root.receiver)
                route_path_parts.append(f"root({root.receiver})")

        # Check inhibition rules
        for rule in config.inhibitions:
            target_matches = all(
                self._label_matches_matcher(alert_labels, m) for m in rule.target_matchers
            ) if rule.target_matchers else False
            if target_matches:
                inhibited_by.append(
                    f"inhibited by rule targeting {[m.name + '=' + m.value for m in rule.target_matchers]} "
                    f"when source {[m.name + '=' + m.value for m in rule.source_matchers]} fires"
                )

        route_path = " -> ".join(route_path_parts) if route_path_parts else "no matching route"

        return RoutingSimulationResult(
            receivers=matched_receivers or ["<no-match>"],
            route_path=route_path,
            inhibited_by=inhibited_by,
        )

    def _walk_routes(
        self,
        routes: List[RoutingRoute],
        labels: Dict[str, str],
        receivers: List[str],
        path_parts: List[str],
    ) -> None:
        """Walk the routing tree and collect matching receivers."""
        for route in routes:
            if route.matchers:
                if all(self._label_matches_matcher(labels, m) for m in route.matchers):
                    if route.receiver and route.receiver not in receivers:
                        receivers.append(route.receiver)
                        matcher_desc = ", ".join(f"{m.name}={m.value}" for m in route.matchers)
                        path_parts.append(f"match({matcher_desc}) -> {route.receiver}")
            elif route.receiver:
                # Root route (no matchers) — always matches as fallback
                if not receivers:
                    receivers.append(route.receiver)
                    path_parts.append(f"root({route.receiver})")

    @staticmethod
    def _label_matches_matcher(labels: Dict[str, str], matcher: AlertMatcher) -> bool:
        """Check if a label set matches a single matcher."""
        val = labels.get(matcher.name, "")
        if matcher.isRegex:
            match = bool(re.match(f"^{matcher.value}$", val))
        else:
            match = val == matcher.value
        return match if matcher.isEqual else not match

    # ---- v3: Routing Introspection ----

    async def get_routing_tree_nested(self, backend_id: str) -> RoutingTreeNode:
        """Return the full nested routing tree preserving the tree structure."""
        status = await self.get_status(backend_id)
        config_raw = status.get("config", {})
        config_str = config_raw.get("original", "") if isinstance(config_raw, dict) else ""
        if not config_str:
            return RoutingTreeNode()
        parsed = yaml.safe_load(config_str)
        if not parsed or not isinstance(parsed, dict):
            return RoutingTreeNode()
        route_section = parsed.get("route", {})
        return self._build_routing_tree_node(route_section)

    def _build_routing_tree_node(self, route_data: Dict[str, Any]) -> RoutingTreeNode:
        """Recursively build a nested RoutingTreeNode from config data."""
        if not route_data or not isinstance(route_data, dict):
            return RoutingTreeNode()
        matchers = self._parse_matchers_from_config(
            route_data.get("matchers", route_data.get("match", {}))
        )
        children = [
            self._build_routing_tree_node(child)
            for child in (route_data.get("routes", []) or [])
        ]
        return RoutingTreeNode(
            receiver=route_data.get("receiver"),
            matchers=matchers,
            group_by=route_data.get("group_by", []),
            group_wait=route_data.get("group_wait"),
            group_interval=route_data.get("group_interval"),
            repeat_interval=route_data.get("repeat_interval"),
            continue_routing=route_data.get("continue", False),
            routes=children,
        )

    async def explain_routing_for_alert(
        self, backend_id: str, alert_labels: Dict[str, str],
    ) -> RoutingExplanation:
        """Rich routing explanation with human-readable reasoning."""
        config = await self.get_config_snapshot(backend_id)
        matched_receivers: List[str] = []
        route_path_parts: List[str] = []
        inhibited_by: List[str] = []
        group_labels: List[str] = []

        # Walk routes
        if config.routes:
            self._walk_routes(config.routes, alert_labels, matched_receivers, route_path_parts)
            # Get group_by from the first matching route
            for route in config.routes:
                if route.matchers:
                    if all(self._label_matches_matcher(alert_labels, m) for m in route.matchers):
                        group_labels = route.group_by
                        break
                elif route.group_by:
                    group_labels = route.group_by

        # Fallback to root
        if not matched_receivers and config.routes:
            root = config.routes[0]
            if root.receiver:
                matched_receivers.append(root.receiver)
                route_path_parts.append(f"root({root.receiver})")
                group_labels = root.group_by

        # Check inhibitions
        for rule in config.inhibitions:
            target_matches = all(
                self._label_matches_matcher(alert_labels, m) for m in rule.target_matchers
            ) if rule.target_matchers else False
            if target_matches:
                inhibited_by.append(
                    f"inhibited by rule targeting {[m.name + '=' + m.value for m in rule.target_matchers]} "
                    f"when source {[m.name + '=' + m.value for m in rule.source_matchers]} fires"
                )

        matched_route = " -> ".join(route_path_parts) if route_path_parts else "no matching route"

        # Build human-readable explanation
        label_str = ", ".join(f"{k}={v}" for k, v in alert_labels.items())
        explanation_parts = [f"Alert with labels [{label_str}]:"]
        if matched_receivers:
            explanation_parts.append(f"  Routes to receiver(s): {', '.join(matched_receivers)}")
        else:
            explanation_parts.append("  No receivers matched — alert may be dropped.")
        if group_labels:
            explanation_parts.append(f"  Grouped by: {', '.join(group_labels)}")
        if inhibited_by:
            explanation_parts.append(f"  ⚠️ May be suppressed by inhibition rules:")
            for inh in inhibited_by:
                explanation_parts.append(f"    - {inh}")
        explanation_parts.append(f"  Route path: {matched_route}")

        return RoutingExplanation(
            matched_route=matched_route,
            receivers=matched_receivers or ["<no-match>"],
            group_labels=group_labels,
            inhibited_by=inhibited_by,
            explanation="\n".join(explanation_parts),
        )

    async def get_default_route_alerts(self, backend_id: str) -> List[GettableAlert]:
        """List alerts that are routing to the default/fallback receiver.

        Uses the full routing simulation engine (explain_routing_for_alert) per
        alert to correctly handle nested routes, continue flags, and regex
        matchers — instead of a naive flat loop over top-level routes.
        """
        config = await self.get_config_snapshot(backend_id)
        if not config.routes:
            return []
        root_receiver = config.routes[0].receiver
        if not root_receiver:
            return []

        alerts, _, _ = await self.list_alerts(
            backend_id, active=True, limit=500, offset=0,
        )
        default_alerts = []
        for alert in alerts:
            explanation = await self.explain_routing_for_alert(backend_id, alert.labels)
            # Alert hits the default route if its matched route is the root fallback
            if explanation.matched_route == f"root({root_receiver})":
                default_alerts.append(alert)
        return default_alerts

    async def export_config_yaml(self, backend_id: str) -> str:
        """Return the raw YAML config string from /api/v2/status."""
        status = await self.get_status(backend_id)
        config_raw = status.get("config", {})
        return config_raw.get("original", "") if isinstance(config_raw, dict) else ""

    async def get_recent_silence_changes(
        self, backend_id: str, hours: int = 24,
    ) -> List[SilenceChange]:
        """Get recent silence create/expire/update events within a time range."""
        silences, _, _ = await self.list_silences(backend_id, limit=500, offset=0)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        changes: List[SilenceChange] = []
        for s in silences:
            updated = s.updatedAt or s.startsAt
            if updated and updated >= cutoff:
                matchers_str = ", ".join(f"{m.name}={m.value}" for m in s.matchers)
                action = "expired" if s.status and s.status.state == "expired" else "created"
                changes.append(SilenceChange(
                    silence_id=s.id,
                    action=action,
                    matchers_summary=matchers_str,
                    created_by=s.createdBy,
                    comment=s.comment,
                    timestamp=updated,
                ))
        changes.sort(key=lambda c: c.timestamp, reverse=True)
        return changes
