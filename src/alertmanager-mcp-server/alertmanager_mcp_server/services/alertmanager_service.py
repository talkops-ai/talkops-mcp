"""Domain-backed Alertmanager HTTP API v2 service layer."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

import httpx
import yaml

from alertmanager_mcp_server.config import BackendConfig, ServerConfig
from alertmanager_mcp_server.domain.inhibition import (
    evaluate_inhibition,
    parse_inhibit_rules,
)
from alertmanager_mcp_server.domain.matchers import (
    CompiledMatcher,
    MatcherOperator,
    format_filter_param,
    match_all,
    parse_matcher,
    parse_matcher_set,
    parse_route_matchers,
)
from alertmanager_mcp_server.domain.metrics import (
    AlertmanagerMetricsSummary,
    parse_prometheus_metrics,
)
from alertmanager_mcp_server.domain.redaction import redact_config_data
from alertmanager_mcp_server.domain.routing import RouteNode, RouteTree
from alertmanager_mcp_server.domain.silence_policy import (
    SilencePolicy,
    SilencePolicyResult,
)
from alertmanager_mcp_server.domain.timeparse import (
    format_rfc3339_utc,
    parse_rfc3339,
    utc_now,
)
from alertmanager_mcp_server.exceptions import (
    AlertmanagerConnectionError,
    AlertmanagerNotFoundError,
    AlertmanagerOperationError,
    AlertmanagerValidationError,
    SilenceSafetyError,
)
from alertmanager_mcp_server.models.alert import (
    AlertGroup,
    AlertMatcher,
    GettableAlert,
)
from alertmanager_mcp_server.models.backend import BackendDescriptor
from alertmanager_mcp_server.models.config import (
    AlertmanagerConfigSnapshot,
    InhibitionRule,
    ReceiverConfig,
    RoutingExplanation,
    RoutingRoute,
    RoutingSimulationResult,
    RoutingTreeNode,
    SilenceChange,
)
from alertmanager_mcp_server.models.silence import (
    GettableSilence,
    PostableSilence,
)

logger = logging.getLogger(__name__)

_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})

# Map receiver config keys to their integration type name.
_RECEIVER_TYPE_MAP: Dict[str, str] = {
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
    """Recursively redact sensitive keys and credentials from dicts/lists."""
    return redact_config_data(data)


def _compiled_to_model(m: CompiledMatcher) -> AlertMatcher:
    return AlertMatcher(
        name=m.name,
        value=m.value,
        isRegex=m.is_regex,
        isEqual=m.is_equal,
    )


class AlertmanagerService:
    """Async wrapper around Alertmanager HTTP API v2 and domain engines."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._backends: Dict[str, BackendConfig] = {
            b.id: b for b in config.backends
        }
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._max_retries = 2
        self._retry_backoff = 0.5

    @property
    def config(self) -> ServerConfig:
        return self._config

    @property
    def silence_policy(self) -> SilencePolicy:
        return SilencePolicy(
            max_duration_minutes=self._config.max_silence_duration_minutes,
            confirm_threshold=self._config.silence_confirm_threshold,
            forbidden_sole_labels=tuple(
                self._config.silence_forbidden_sole_labels
            ),
            watchdog_alertname=self._config.watchdog_alertname,
            comment_pattern=self._config.silence_comment_pattern,
        )

    def resolve_backend_id(self, backend_id: Optional[str] = None) -> str:
        """Resolve `backend_id` or return the default backend ID."""
        if not backend_id:
            return self._get_default_backend().id
        return self._get_backend(backend_id).id

    def _get_backend(self, backend_id: str) -> BackendConfig:
        backend = self._backends.get(backend_id)
        if not backend:
            available = list(self._backends.keys())
            raise AlertmanagerNotFoundError(
                f"Unknown backend_id '{backend_id}'. Available: {available}. "
                "Read resource 'am://backends' to list configured backends."
            )
        return backend

    def _get_default_backend(self) -> BackendConfig:
        """Return the default backend or the first one."""
        for b in self._backends.values():
            if b.is_default:
                return b
        if self._backends:
            return next(iter(self._backends.values()))
        raise AlertmanagerValidationError("No Alertmanager backends configured")

    def _ensure_client(self, backend_id: str) -> httpx.AsyncClient:
        if (
            backend_id not in self._clients
            or self._clients[backend_id].is_closed
        ):
            backend = self._get_backend(backend_id)
            basic_auth = backend.resolve_basic_auth()
            client_kwargs: Dict[str, Any] = {
                "base_url": backend.api_base_url,
                "verify": backend.verify_ssl,
                "timeout": backend.timeout,
            }
            if basic_auth is not None:
                client_kwargs["auth"] = basic_auth
            self._clients[backend_id] = httpx.AsyncClient(**client_kwargs)
        return self._clients[backend_id]

    def _headers(self, backend: BackendConfig) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        headers.update(backend.build_request_headers())
        return headers

    async def _request(
        self,
        method: str,
        backend_id: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with idempotency-safe retry logic."""
        method_upper = method.strip().upper()
        is_idempotent = method_upper in _IDEMPOTENT_METHODS
        backend = self._get_backend(backend_id)
        client = self._ensure_client(backend_id)
        headers = self._headers(backend)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.request(
                    method_upper, path, headers=headers, **kwargs
                )

                # Retry on 5xx server errors ONLY for idempotent methods
                if (
                    resp.status_code >= 500
                    and is_idempotent
                    and attempt < self._max_retries
                ):
                    logger.warning(
                        "Alertmanager %s %s returned %d, retrying (%d/%d)",
                        method_upper,
                        path,
                        resp.status_code,
                        attempt + 1,
                        self._max_retries,
                    )
                    await asyncio.sleep(self._retry_backoff * (attempt + 1))
                    continue

                if resp.status_code == 404:
                    raise AlertmanagerNotFoundError(
                        f"Alertmanager API error 404 ({method_upper} {path} on "
                        f"'{backend_id}'): {resp.text[:500]}"
                    )
                if resp.status_code in (400, 422):
                    raise AlertmanagerValidationError(
                        f"Alertmanager API error {resp.status_code} ({method_upper} "
                        f"{path} on '{backend_id}'): {resp.text[:500]}"
                    )
                if resp.status_code >= 400:
                    raise AlertmanagerOperationError(
                        f"Alertmanager API error {resp.status_code}: {resp.text[:500]}"
                    )
                return resp

            except httpx.ConnectError as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    raise AlertmanagerConnectionError(
                        f"Failed to connect to Alertmanager backend '{backend_id}' "
                        f"({method_upper} {path}): {exc}"
                    ) from exc
                logger.warning(
                    "Alertmanager %s %s failed with ConnectError, retrying (%d/%d)",
                    method_upper,
                    path,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(self._retry_backoff * (attempt + 1))

            except httpx.TimeoutException as exc:
                last_exc = exc
                # Do NOT retry POST/non-idempotent requests on timeout
                if not is_idempotent or attempt >= self._max_retries:
                    raise AlertmanagerConnectionError(
                        f"Alertmanager request timed out on backend '{backend_id}' "
                        f"({method_upper} {path}): {exc}"
                    ) from exc
                logger.warning(
                    "Alertmanager %s %s timed out, retrying (%d/%d)",
                    method_upper,
                    path,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(self._retry_backoff * (attempt + 1))

        assert last_exc is not None
        raise AlertmanagerConnectionError(str(last_exc))

    async def close(self) -> None:
        """Gracefully close all HTTP clients."""
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()
        logger.info("All Alertmanager HTTP clients closed.")

    # ---- Backend Discovery & Telemetry ----

    def list_backends(self) -> List[BackendDescriptor]:
        return [
            BackendDescriptor(
                id=b.id,
                display_name=b.display_name or b.id,
                base_url=b.base_url,
                labels=b.labels,
                is_default=b.is_default,
            )
            for b in self._backends.values()
        ]

    async def check_health(
        self, backend_id: str
    ) -> Literal["unknown", "healthy", "degraded", "unhealthy"]:
        try:
            resp = await self._request("GET", backend_id, "/-/healthy")
            return "healthy" if resp.status_code == 200 else "degraded"
        except Exception:
            return "unhealthy"

    async def check_ready(self, backend_id: str) -> bool:
        try:
            resp = await self._request("GET", backend_id, "/-/ready")
            return resp.status_code == 200
        except Exception:
            return False

    async def get_status(self, backend_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", backend_id, "/api/v2/status")
        return resp.json()

    async def get_metrics(
        self, backend_id: str
    ) -> Optional[AlertmanagerMetricsSummary]:
        """Scrape and parse Prometheus `/metrics` from the backend if available."""
        backend = self._get_backend(backend_id)
        try:
            resp = await self._request(
                "GET",
                backend_id,
                backend.metrics_path,
                headers={"Accept": "text/plain"},
            )
            return parse_prometheus_metrics(resp.text)
        except Exception as exc:
            logger.debug(
                "Metrics endpoint %s unavailable on backend '%s': %s",
                backend.metrics_path,
                backend_id,
                exc,
            )
            return None

    async def check_notification_health(
        self,
        backend_id: str,
        *,
        integration: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Comprehensive health check of Alertmanager cluster, config reload, and receiver delivery."""
        bid = self.resolve_backend_id(backend_id)
        health = await self.check_health(bid)
        ready = await self.check_ready(bid)

        version: Optional[str] = None
        uptime: Optional[str] = None
        cluster_info: Dict[str, Any] = {}
        try:
            status_data = await self.get_status(bid)
            version_info = status_data.get("versionInfo") or {}
            version = version_info.get("version")
            uptime = status_data.get("uptime")
            cluster_info = dict(status_data.get("cluster") or {})
        except Exception as exc:
            logger.warning("Failed to fetch /api/v2/status on '%s': %s", bid, exc)

        metrics = await self.get_metrics(bid)
        receivers: List[Dict[str, Any]] = []
        try:
            rcv_models = await self.get_receivers(bid)
            receivers = [r.model_dump() for r in rcv_models]
        except Exception as exc:
            logger.warning("Failed to list receivers on '%s': %s", bid, exc)

        metrics_dict = metrics.to_dict() if metrics is not None else {}
        integrations_map: Dict[str, Any] = dict(
            metrics_dict.get("integrations") or {}
        )
        if integration:
            int_lower = integration.strip().lower()
            integrations_map = {
                k: v
                for k, v in integrations_map.items()
                if k.lower() == int_lower
            }

        degraded_list = (
            list(metrics.degraded_integrations) if metrics is not None else []
        )
        config_reload_ok = (
            metrics.config_last_reload_successful if metrics is not None else None
        )

        overall_status = health
        if (
            overall_status == "healthy"
            and (
                not ready
                or degraded_list
                or config_reload_ok is False
                or cluster_info.get("status") not in (None, "ready", "disabled")
            )
        ):
            overall_status = "degraded"

        summary_parts = [
            f"Backend '{bid}' is {overall_status} (ready={ready}, version={version or 'unknown'})."
        ]
        if config_reload_ok is False:
            summary_parts.append(
                "WARNING: Last configuration reload failed (alertmanager_config_last_reload_successful=0)."
            )
        if degraded_list:
            summary_parts.append(
                f"Degraded notification integrations with failed deliveries: {', '.join(degraded_list)}."
            )
        elif metrics is not None:
            summary_parts.append(
                f"Notification telemetry healthy ({metrics.total_notifications} sent, 0 failed)."
            )

        return {
            "backend_id": bid,
            "healthy": overall_status == "healthy",
            "ready": ready,
            "status": overall_status,
            "version": version,
            "uptime": uptime,
            "cluster": cluster_info,
            "config_reload_successful": config_reload_ok,
            "config_last_reload_timestamp": (
                metrics.config_last_reload_timestamp if metrics else None
            ),
            "metrics_available": metrics is not None,
            "total_notifications": (
                metrics.total_notifications if metrics else 0
            ),
            "total_failed_notifications": (
                metrics.total_failed_notifications if metrics else 0
            ),
            "degraded_integrations": degraded_list,
            "integrations": integrations_map,
            "configured_receivers": receivers,
            "summary_text": " ".join(summary_parts),
        }

    # ---- Alerts ----

    async def list_alerts_with_total(
        self,
        backend_id: str,
        matchers: Optional[List[AlertMatcher]] = None,
        active: Optional[bool] = True,
        silenced: Optional[bool] = None,
        inhibited: Optional[bool] = None,
        unprocessed: Optional[bool] = None,
        receiver: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[GettableAlert], int, bool, Optional[int]]:
        """List alerts and return `(page_alerts, total_count, has_more, next_offset)`."""
        params: Dict[str, Any] = {}
        if matchers:
            filters: List[str] = []
            for m in matchers:
                op: MatcherOperator = "=~" if m.isRegex else "="
                if not m.isEqual:
                    op = "!~" if m.isRegex else "!="
                filters.append(format_filter_param(m.name, m.value, op))
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
        total = len(raw)
        page = raw[offset : offset + limit]
        has_more = offset + limit < total
        next_offset = offset + limit if has_more else None
        alerts = [GettableAlert(**a) for a in page]
        return alerts, total, has_more, next_offset

    async def list_alerts(
        self,
        backend_id: str,
        matchers: Optional[List[AlertMatcher]] = None,
        active: Optional[bool] = True,
        silenced: Optional[bool] = None,
        inhibited: Optional[bool] = None,
        unprocessed: Optional[bool] = None,
        receiver: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[GettableAlert], bool, Optional[int]]:
        alerts, _total, has_more, next_offset = await self.list_alerts_with_total(
            backend_id,
            matchers=matchers,
            active=active,
            silenced=silenced,
            inhibited=inhibited,
            unprocessed=unprocessed,
            receiver=receiver,
            limit=limit,
            offset=offset,
        )
        return alerts, has_more, next_offset

    async def get_alert_by_fingerprint(
        self, backend_id: str, fingerprint: str
    ) -> GettableAlert:
        """Fetch an alert by fingerprint across all states (`active`, `silenced`, `inhibited`)."""
        alerts, _, _ = await self.list_alerts(
            backend_id,
            active=True,
            silenced=True,
            inhibited=True,
            unprocessed=True,
            limit=2000,
            offset=0,
        )
        fp_clean = fingerprint.strip()
        for alert in alerts:
            if alert.fingerprint == fp_clean:
                return alert
        if len(fp_clean) >= 7:
            prefix_matches = [
                a for a in alerts if a.fingerprint and a.fingerprint.startswith(fp_clean)
            ]
            if len(prefix_matches) == 1:
                return prefix_matches[0]
        raise AlertmanagerNotFoundError(
            f"Alert with fingerprint '{fingerprint}' not found on backend '{backend_id}'. "
            "Use am_list_alerts to find active alert fingerprints."
        )

    async def list_alert_groups(
        self,
        backend_id: str,
        max_alerts_per_group: int = 20,
        *,
        active: Optional[bool] = None,
        silenced: Optional[bool] = None,
        inhibited: Optional[bool] = None,
        receiver: Optional[str] = None,
    ) -> List[AlertGroup]:
        """List alert groups with optional query filters and per-group alert cap."""
        params: Dict[str, Any] = {}
        if active is not None:
            params["active"] = str(active).lower()
        if silenced is not None:
            params["silenced"] = str(silenced).lower()
        if inhibited is not None:
            params["inhibited"] = str(inhibited).lower()
        if receiver:
            params["receiver"] = receiver

        resp = await self._request(
            "GET",
            backend_id,
            "/api/v2/alerts/groups",
            params=params or None,
        )
        data = resp.json()
        return [
            AlertGroup(
                labels=g.get("labels", {}),
                receiver=g.get("receiver"),
                alerts=[
                    GettableAlert(**a)
                    for a in g.get("alerts", [])[:max_alerts_per_group]
                ],
            )
            for g in data
        ]

    async def push_alerts(
        self, backend_id: str, alerts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        resp = await self._request(
            "POST", backend_id, "/api/v2/alerts", json=alerts
        )
        return resp.json() if resp.content else {}

    # ---- Silences ----

    async def list_silences_with_total(
        self,
        backend_id: str,
        state: Optional[str] = None,
        *,
        filter_matchers: Optional[Sequence[CompiledMatcher]] = None,
        created_by: Optional[str] = None,
        comment_search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[GettableSilence], int, bool, Optional[int]]:
        """List silences with optional state, matcher, author, and comment filtering."""
        params: Dict[str, Any] = {}
        if filter_matchers:
            params["filter"] = [m.to_filter_string() for m in filter_matchers]
        resp = await self._request(
            "GET", backend_id, "/api/v2/silences", params=params or None
        )
        raw_silences = resp.json()

        if state and state != "all":
            raw_silences = [
                s
                for s in raw_silences
                if s.get("status", {}).get("state") == state
            ]

        if created_by:
            author_q = created_by.strip().lower()
            raw_silences = [
                s
                for s in raw_silences
                if author_q in str(s.get("createdBy", "")).lower()
            ]

        if comment_search:
            comment_q = comment_search.strip().lower()
            raw_silences = [
                s
                for s in raw_silences
                if comment_q in str(s.get("comment", "")).lower()
            ]

        total = len(raw_silences)
        page = raw_silences[offset : offset + limit]
        has_more = offset + limit < total
        next_offset = offset + limit if has_more else None
        silences = [GettableSilence(**s) for s in page]
        return silences, total, has_more, next_offset

    async def list_silences(
        self,
        backend_id: str,
        state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[GettableSilence], bool, Optional[int]]:
        """List silences with optional state filter and pagination."""
        silences, _total, has_more, next_offset = await self.list_silences_with_total(
            backend_id,
            state=state,
            limit=limit,
            offset=offset,
        )
        return silences, has_more, next_offset

    async def get_silence(
        self, backend_id: str, silence_id: str
    ) -> GettableSilence:
        resp = await self._request(
            "GET", backend_id, f"/api/v2/silence/{silence_id}"
        )
        return GettableSilence(**resp.json())

    async def find_duplicate_silence(
        self, backend_id: str, matchers: List[AlertMatcher]
    ) -> Optional[GettableSilence]:
        """Check if an equivalent active silence already exists (dedup)."""
        silences, _, _ = await self.list_silences(
            backend_id, state="active", limit=500
        )
        matcher_set = {
            (m.name, m.value, m.isRegex, m.isEqual) for m in matchers
        }
        for s in silences:
            existing_set = {
                (m.name, m.value, m.isRegex, m.isEqual) for m in s.matchers
            }
            if existing_set == matcher_set:
                return s
        return None

    async def find_overlapping_silences(
        self,
        backend_id: str,
        compiled_matchers: Sequence[CompiledMatcher],
    ) -> List[GettableSilence]:
        """Find active silences whose matcher sets are identical or a subset/superset."""
        silences, _, _ = await self.list_silences(
            backend_id, state="active", limit=500
        )
        candidate_set = {
            (m.name, m.value, m.is_regex, m.is_equal)
            for m in compiled_matchers
        }
        overlapping: List[GettableSilence] = []
        for s in silences:
            existing_set = {
                (m.name, m.value, m.isRegex, m.isEqual) for m in s.matchers
            }
            if (
                existing_set
                and candidate_set
                and (
                    existing_set.issubset(candidate_set)
                    or candidate_set.issubset(existing_set)
                )
            ):
                overlapping.append(s)
        return overlapping

    async def create_silence(
        self, backend_id: str, silence: PostableSilence
    ) -> GettableSilence:
        """Create or atomically update a silence via `POST /api/v2/silences`."""
        payload = silence.to_api_payload()
        resp = await self._request(
            "POST", backend_id, "/api/v2/silences", json=payload
        )
        created = resp.json()
        if isinstance(created, dict):
            silence_id = created.get("silenceID") or created.get("id")
            if silence_id and "status" not in created:
                return await self.get_silence(backend_id, str(silence_id))
        return GettableSilence(**created)

    async def update_silence(
        self,
        backend_id: str,
        silence_id: str,
        *,
        new_ends_at: Optional[str | datetime] = None,
        duration_minutes: Optional[int] = None,
        new_comment: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> Tuple[GettableSilence, SilencePolicyResult]:
        """Atomically update an active silence via native `POST /api/v2/silences` with `id`.

        Enforces the total lifetime cap (`new_end - existing.startsAt <= max_silence_duration_minutes`)
        so callers cannot bypass `max_silence_duration_minutes` via rolling updates.
        """
        existing = await self.get_silence(backend_id, silence_id)
        if existing.status.state == "expired":
            raise SilenceSafetyError(
                f"Silence '{silence_id}' is already expired and cannot be updated. "
                "Use am_create_silence to create a new silence window."
            )

        now = utc_now()
        orig_start = parse_rfc3339(
            existing.startsAt, require_tz=False, field_name="startsAt"
        )
        if new_ends_at is not None:
            target_end = parse_rfc3339(
                new_ends_at, require_tz=True, field_name="new_ends_at"
            )
        elif duration_minutes is not None:
            if duration_minutes <= 0:
                raise AlertmanagerValidationError(
                    f"duration_minutes must be positive (got {duration_minutes})."
                )
            base_time = max(orig_start, now)
            target_end = base_time + timedelta(minutes=duration_minutes)
        else:
            target_end = parse_rfc3339(
                existing.endsAt, require_tz=False, field_name="endsAt"
            )

        effective_author = (updated_by or existing.createdBy).strip()
        effective_comment = (
            new_comment.strip()
            if new_comment is not None and new_comment.strip()
            else existing.comment
        )

        # Evaluate total lifetime window (orig_start -> target_end) against SilencePolicy
        policy_result = self.silence_policy.evaluate(
            matchers=existing.matchers,
            starts_at=orig_start,
            ends_at=target_end,
            created_by=effective_author,
            comment=effective_comment,
            now=now,
        )
        if not policy_result.valid:
            violation_msgs = "; ".join(
                f"[{v.rule_id}] {v.message} ({v.remediation})"
                for v in policy_result.violations
            )
            raise SilenceSafetyError(
                f"Silence update rejected by policy: {violation_msgs}"
            )

        postable = PostableSilence(
            id=existing.id,
            matchers=existing.matchers,
            startsAt=orig_start,
            endsAt=target_end,
            createdBy=effective_author,
            comment=effective_comment,
        )
        updated_silence = await self.create_silence(backend_id, postable)
        return updated_silence, policy_result

    async def delete_silence(self, backend_id: str, silence_id: str) -> None:
        await self._request(
            "DELETE", backend_id, f"/api/v2/silence/{silence_id}"
        )

    async def preview_silence(
        self,
        backend_id: str,
        *,
        matchers: Any,
        starts_at: Optional[str | datetime] = None,
        ends_at: Optional[str | datetime] = None,
        duration_minutes: Optional[int] = None,
        created_by: Optional[str] = "preview-operator",
        comment: Optional[str] = "PREVIEW: dry-run silence check",
    ) -> Dict[str, Any]:
        """Dry-run a silence in a single pass without $N+1$ HTTP calls."""
        bid = self.resolve_backend_id(backend_id)

        # Parse matchers first to query matching active alerts if valid
        try:
            compiled = parse_matcher_set(matchers)
        except Exception:
            compiled = []

        matched_alerts: List[GettableAlert] = []
        total_matched = 0
        critical_count = 0

        if compiled:
            model_matchers = [_compiled_to_model(m) for m in compiled]
            fetched_alerts, _, _, _ = await self.list_alerts_with_total(
                bid,
                matchers=model_matchers,
                active=True,
                limit=500,
                offset=0,
            )
            matched_alerts = [
                a for a in fetched_alerts if match_all(compiled, a.labels)
            ]
            total_matched = len(matched_alerts)
            sev_label = self._config.label_severity
            critical_count = sum(
                1
                for a in matched_alerts
                if a.labels.get(sev_label, "").lower() == "critical"
            )

        policy_res = self.silence_policy.evaluate(
            matchers=matchers,
            starts_at=starts_at,
            ends_at=ends_at,
            duration_minutes=duration_minutes,
            created_by=created_by,
            comment=comment,
            matched_alert_count=total_matched,
            matched_critical_count=critical_count,
        )

        # Single fetch of config to evaluate affected receivers in-memory (fixes P13)
        affected_receivers: List[str] = []
        try:
            parsed_cfg = await self.get_parsed_config(bid)
            route_tree = RouteTree.from_config(parsed_cfg)
            for alert in matched_alerts[:50]:
                eval_res = route_tree.evaluate(alert.labels)
                for rcv in eval_res.receivers:
                    if rcv not in affected_receivers:
                        affected_receivers.append(rcv)
        except Exception as exc:
            logger.debug("Receiver impact calculation skipped: %s", exc)

        overlapping: List[Dict[str, Any]] = []
        if compiled:
            try:
                ov_models = await self.find_overlapping_silences(bid, compiled)
                overlapping = [
                    {
                        "id": s.id,
                        "created_by": s.createdBy,
                        "comment": s.comment,
                        "ends_at": format_rfc3339_utc(
                            parse_rfc3339(s.endsAt, require_tz=False)
                        ),
                        "matchers": [m.model_dump() for m in s.matchers],
                    }
                    for s in ov_models[:10]
                ]
            except Exception as exc:
                logger.debug("Overlapping silence check skipped: %s", exc)

        warning_flag = policy_res.requires_confirmation
        warning_msg: Optional[str] = None
        if policy_res.confirmation_reasons:
            warning_msg = " ".join(policy_res.confirmation_reasons)

        return {
            "backend_id": bid,
            "valid": policy_res.valid,
            "policy": policy_res.to_dict(),
            "affected_alert_count": total_matched,
            "affected_critical_count": critical_count,
            "affected_alerts_preview": [
                a.model_dump(mode="json") for a in matched_alerts[:20]
            ],
            "affected_receivers": affected_receivers,
            "overlapping_silences": overlapping,
            "warning_flag": warning_flag,
            "requires_confirmation": policy_res.requires_confirmation,
            "warning_message": warning_msg,
        }

    # ---- Receivers & Configuration ----

    async def get_parsed_config(self, backend_id: str) -> Dict[str, Any]:
        """Fetch `/api/v2/status` and parse `config.original` YAML into a dict."""
        status = await self.get_status(backend_id)
        config_raw = status.get("config", {})
        config_str = (
            config_raw.get("original", "")
            if isinstance(config_raw, dict)
            else ""
        )
        if not config_str:
            return {}
        parsed = yaml.safe_load(config_str)
        return parsed if isinstance(parsed, dict) else {}

    async def get_redacted_config(self, backend_id: str) -> Dict[str, Any]:
        """Return the parsed Alertmanager config with all secrets deeply redacted."""
        parsed = await self.get_parsed_config(backend_id)
        return redact_config_data(parsed)

    async def get_receivers(self, backend_id: str) -> List[ReceiverConfig]:
        """Get receivers with integration type inference and deep secret redaction."""
        receiver_configs: Dict[str, Dict[str, Any]] = {}
        try:
            parsed = await self.get_parsed_config(backend_id)
            for rcv in parsed.get("receivers", []) or []:
                if isinstance(rcv, dict) and "name" in rcv:
                    receiver_configs[str(rcv["name"])] = rcv
        except Exception as exc:
            logger.warning("Failed to parse receivers from config YAML: %s", exc)

        resp = await self._request("GET", backend_id, "/api/v2/receivers")
        api_receivers = resp.json()

        receivers: List[ReceiverConfig] = []
        for r in api_receivers:
            name = r.get("name", "unknown")
            source: Dict[str, Any] = receiver_configs.get(name) or r

            r_type: Optional[str] = None
            types_found: List[str] = []
            for config_key, type_name in _RECEIVER_TYPE_MAP.items():
                if config_key in source and source[config_key]:
                    types_found.append(type_name)
            if types_found:
                r_type = types_found[0]

            details = redact_config_data(
                {k: v for k, v in source.items() if k != "name"}
            )
            receivers.append(
                ReceiverConfig(name=name, type=r_type, details=details)
            )
        return receivers

    async def get_config_snapshot(
        self, backend_id: str
    ) -> AlertmanagerConfigSnapshot:
        """Parse the active config from `/api/v2/status` into routes and inhibitions."""
        routes: List[RoutingRoute] = []
        inhibitions: List[InhibitionRule] = []

        try:
            parsed = await self.get_parsed_config(backend_id)
            if parsed:
                route_tree = RouteTree.from_config(parsed)
                routes = self._flatten_route_tree(route_tree.root)

                compiled_rules = parse_inhibit_rules(parsed)
                for rule in compiled_rules:
                    inhibitions.append(
                        InhibitionRule(
                            source_matchers=[
                                _compiled_to_model(m)
                                for m in rule.source_matchers
                            ],
                            target_matchers=[
                                _compiled_to_model(m)
                                for m in rule.target_matchers
                            ],
                            equal=list(rule.equal),
                        )
                    )
        except Exception as exc:
            logger.warning("Failed to parse Alertmanager config: %s", exc)

        return AlertmanagerConfigSnapshot(routes=routes, inhibitions=inhibitions)

    def _flatten_route_tree(self, node: RouteNode) -> List[RoutingRoute]:
        """Flatten `RouteNode` hierarchy into `List[RoutingRoute]` for snapshot summaries."""
        current = RoutingRoute(
            matchers=[_compiled_to_model(m) for m in node.matchers],
            receiver=node.receiver,
            group_by=list(node.group_by),
            group_wait=node.group_wait,
            group_interval=node.group_interval,
            repeat_interval=node.repeat_interval,
        )
        items = [current]
        for child in node.children:
            items.extend(self._flatten_route_tree(child))
        return items

    @staticmethod
    def _parse_matchers_from_config(match_data: Any) -> List[AlertMatcher]:
        """Parse matchers from Alertmanager config formats into `AlertMatcher` models."""
        if not match_data:
            return []
        try:
            compiled = parse_matcher_set(match_data)
            return [_compiled_to_model(m) for m in compiled]
        except Exception:
            return []

    @staticmethod
    def _parse_matcher_string(s: str) -> Optional[AlertMatcher]:
        """Parse a single matcher string into an `AlertMatcher` model."""
        try:
            compiled = parse_matcher(s)
            return _compiled_to_model(compiled)
        except Exception:
            return None

    @staticmethod
    def _label_matches_matcher(
        labels: Dict[str, str], matcher: AlertMatcher
    ) -> bool:
        """Evaluate whether `labels` satisfies `matcher` using RE2-compatible fullmatch."""
        try:
            compiled = CompiledMatcher(
                name=matcher.name,
                value=matcher.value,
                is_regex=matcher.isRegex,
                is_equal=matcher.isEqual,
            )
            return compiled.matches(labels)
        except Exception:
            return False

    # ---- Routing & Inhibition Evaluation ----

    async def get_routing_tree_nested(
        self, backend_id: str
    ) -> RoutingTreeNode:
        """Return the full nested routing tree preserving parent inheritance."""
        parsed = await self.get_parsed_config(backend_id)
        if not parsed or "route" not in parsed:
            return RoutingTreeNode()
        route_tree = RouteTree.from_config(parsed)
        return self._route_node_to_model(route_tree.root)

    def _route_node_to_model(self, node: RouteNode) -> RoutingTreeNode:
        return RoutingTreeNode(
            receiver=node.receiver,
            matchers=[_compiled_to_model(m) for m in node.matchers],
            group_by=list(node.group_by),
            group_wait=node.group_wait,
            group_interval=node.group_interval,
            repeat_interval=node.repeat_interval,
            continue_routing=node.continue_routing,
            routes=[self._route_node_to_model(c) for c in node.children],
        )

    async def simulate_routing(
        self,
        backend_id: str,
        alert_labels: Dict[str, str],
        *,
        check_live_alerts: bool = False,
    ) -> RoutingSimulationResult:
        """Simulate Alertmanager routing tree and inhibition rules for `alert_labels`."""
        detailed = await self.explain_routing_detailed(
            backend_id,
            alert_labels=alert_labels,
            check_live_state=check_live_alerts,
        )
        return RoutingSimulationResult(
            receivers=detailed["receivers"] or ["<no-match>"],
            route_path=detailed["matched_route"],
            inhibited_by=detailed["inhibited_by"],
        )

    async def explain_routing_for_alert(
        self,
        backend_id: str,
        alert_labels: Dict[str, str],
        *,
        check_live_state: bool = True,
    ) -> RoutingExplanation:
        """Return `RoutingExplanation` for `alert_labels` using exact `RouteTree` semantics."""
        detailed = await self.explain_routing_detailed(
            backend_id,
            alert_labels=alert_labels,
            check_live_state=check_live_state,
        )
        return RoutingExplanation(
            matched_route=detailed["matched_route"],
            receivers=detailed["receivers"] or ["<no-match>"],
            group_labels=detailed["group_labels"],
            inhibited_by=detailed["inhibited_by"],
            explanation=detailed["explanation"],
        )

    async def explain_routing_detailed(
        self,
        backend_id: str,
        *,
        alert_labels: Optional[Dict[str, str]] = None,
        fingerprint: Optional[str] = None,
        at_time: Optional[datetime] = None,
        check_live_state: bool = True,
    ) -> Dict[str, Any]:
        """Full routing, time-interval, silence, and live inhibition explanation."""
        bid = self.resolve_backend_id(backend_id)

        resolved_labels: Dict[str, str] = dict(alert_labels or {})
        if fingerprint:
            live_alert = await self.get_alert_by_fingerprint(bid, fingerprint)
            resolved_labels = dict(live_alert.labels)

        if not resolved_labels:
            raise AlertmanagerValidationError(
                "Either 'fingerprint' or non-empty 'labels' must be provided to am_explain_routing."
            )

        parsed = await self.get_parsed_config(bid)
        if not parsed or "route" not in parsed:
            return {
                "backend_id": bid,
                "fingerprint": fingerprint,
                "labels": resolved_labels,
                "matched_route": "no matching route",
                "matched_routes": [],
                "receivers": [],
                "active_receivers": [],
                "muted_receivers": [],
                "group_labels": [],
                "fell_back_to_default": False,
                "is_inhibited": False,
                "inhibited_by": [],
                "inhibition_details": [],
                "potential_inhibition_rules": [],
                "matching_silences": [],
                "route_trace": [],
                "explanation": "Alertmanager configuration contains no routing tree.",
            }

        route_tree = RouteTree.from_config(parsed)
        routing_eval = route_tree.evaluate(resolved_labels, at_time=at_time)

        inhibit_rules = parse_inhibit_rules(parsed)
        active_alerts: List[GettableAlert] = []
        matching_silences: List[Dict[str, Any]] = []

        if check_live_state:
            try:
                active_alerts, _, _ = await self.list_alerts(
                    bid, active=True, limit=1000, offset=0
                )
            except Exception as exc:
                logger.debug("Live alert fetch for inhibition check failed: %s", exc)

            try:
                active_silences, _, _ = await self.list_silences(
                    bid, state="active", limit=500, offset=0
                )
                for s in active_silences:
                    compiled_s = [
                        CompiledMatcher(
                            name=m.name,
                            value=m.value,
                            is_regex=m.isRegex,
                            is_equal=m.isEqual,
                        )
                        for m in s.matchers
                    ]
                    if compiled_s and match_all(compiled_s, resolved_labels):
                        matching_silences.append(
                            {
                                "id": s.id,
                                "created_by": s.createdBy,
                                "comment": s.comment,
                                "ends_at": format_rfc3339_utc(
                                    parse_rfc3339(s.endsAt, require_tz=False)
                                ),
                            }
                        )
            except Exception as exc:
                logger.debug("Active silence check failed: %s", exc)

        inh_eval = evaluate_inhibition(
            resolved_labels,
            inhibit_rules,
            active_alerts,
            target_fingerprint=fingerprint,
        )

        # Format route_path string
        path_parts: List[str] = []
        for delivery in routing_eval.matched_routes:
            if delivery.is_default_route:
                path_parts.append(f"root({delivery.receiver})")
            else:
                path_parts.append(f"{delivery.path}({delivery.receiver})")
        matched_route_str = (
            " -> ".join(path_parts) if path_parts else "no matching route"
        )

        group_labels = (
            routing_eval.matched_routes[0].group_by
            if routing_eval.matched_routes
            else []
        )

        inhibited_by_msgs: List[str] = []
        for match_det in inh_eval.inhibiting_Matches:
            src_names = ", ".join(match_det.inhibiting_source_alertnames)
            src_fps = ", ".join(match_det.inhibiting_source_fingerprints)
            inhibited_by_msgs.append(
                f"rule[{match_det.rule_index}]: inhibited by active alert(s) "
                f"{src_names} ({src_fps}) matching {match_det.source_matchers} "
                f"on equal={match_det.equal_values}"
            )

        label_str = ", ".join(f"{k}={v}" for k, v in sorted(resolved_labels.items()))
        explanation_lines = [f"Alert with labels [{label_str}]:"]
        if routing_eval.receivers:
            explanation_lines.append(
                f"  Routes to receiver(s): {', '.join(routing_eval.receivers)} "
                f"via {matched_route_str}"
            )
        if group_labels:
            explanation_lines.append(f"  Grouped by: {', '.join(group_labels)}")
        if routing_eval.muted_receivers:
            explanation_lines.append(
                f"  Muted by time interval on receiver(s): {', '.join(routing_eval.muted_receivers)}"
            )
        if matching_silences:
            s_ids = ", ".join(s["id"] for s in matching_silences)
            explanation_lines.append(f"  Muted by active silence(s): {s_ids}")
        if inh_eval.is_inhibited:
            explanation_lines.append("  Suppressed by active inhibition rule(s):")
            for msg in inhibited_by_msgs:
                explanation_lines.append(f"    - {msg}")

        return {
            "backend_id": bid,
            "fingerprint": fingerprint,
            "labels": resolved_labels,
            "matched_route": matched_route_str,
            "matched_routes": [
                {
                    "path": d.path,
                    "receiver": d.receiver,
                    "group_by": d.group_by,
                    "group_wait": d.group_wait,
                    "group_interval": d.group_interval,
                    "repeat_interval": d.repeat_interval,
                    "muted": d.muted,
                    "mute_reasons": d.mute_reasons,
                    "is_default_route": d.is_default_route,
                }
                for d in routing_eval.matched_routes
            ],
            "receivers": routing_eval.receivers,
            "active_receivers": routing_eval.active_receivers,
            "muted_receivers": routing_eval.muted_receivers,
            "group_labels": group_labels,
            "fell_back_to_default": routing_eval.fell_back_to_default,
            "is_inhibited": inh_eval.is_inhibited,
            "inhibited_by": inhibited_by_msgs,
            "inhibition_details": [
                {
                    "rule_index": m.rule_index,
                    "source_matchers": m.source_matchers,
                    "target_matchers": m.target_matchers,
                    "equal_labels": m.equal_labels,
                    "equal_values": m.equal_values,
                    "inhibiting_source_fingerprints": m.inhibiting_source_fingerprints,
                    "inhibiting_source_alertnames": m.inhibiting_source_alertnames,
                }
                for m in inh_eval.inhibiting_Matches
            ],
            "potential_inhibition_rules": [
                {
                    "rule_index": m.rule_index,
                    "source_matchers": m.source_matchers,
                    "target_matchers": m.target_matchers,
                    "equal_labels": m.equal_labels,
                    "active_source_found": m.active_source_found,
                }
                for m in inh_eval.potential_target_rule_Matches
            ],
            "matching_silences": matching_silences,
            "route_trace": [
                {
                    "path": t.path,
                    "receiver": t.receiver,
                    "matchers": t.matchers,
                    "matched": t.matched,
                    "continue_routing": t.continue_routing,
                    "selected": t.selected,
                    "muted": t.muted,
                    "mute_reasons": t.mute_reasons,
                    "reason": t.reason,
                }
                for t in routing_eval.trace
            ],
            "explanation": "\n".join(explanation_lines),
        }

    # ---- Governance & Hygiene Audits ----

    async def get_default_route_alerts(
        self, backend_id: str
    ) -> List[GettableAlert]:
        """List active alerts falling back to the root default route in a single pass."""
        parsed = await self.get_parsed_config(backend_id)
        if not parsed or "route" not in parsed:
            return []
        route_tree = RouteTree.from_config(parsed)

        alerts, _, _ = await self.list_alerts(
            backend_id, active=True, limit=500, offset=0
        )
        default_alerts: List[GettableAlert] = []
        for alert in alerts:
            eval_res = route_tree.evaluate(alert.labels)
            if eval_res.fell_back_to_default:
                default_alerts.append(alert)
        return default_alerts

    async def audit_alert_hygiene(
        self,
        backend_id: str,
        *,
        check_default_route: bool = True,
        check_missing_annotations: bool = True,
        check_long_firing_hours: int = 24,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Audit active alerts for routing hygiene, annotation completeness, and Watchdog health."""
        bid = self.resolve_backend_id(backend_id)
        parsed = await self.get_parsed_config(bid)
        route_tree = RouteTree.from_config(parsed) if parsed else None
        default_receiver = (
            route_tree.root.receiver if route_tree else "default"
        )

        alerts, total_active, _, _ = await self.list_alerts_with_total(
            bid,
            active=True,
            silenced=True,
            inhibited=True,
            limit=1000,
            offset=0,
        )

        watchdog_name = self._config.watchdog_alertname.lower()
        watchdog_status = "missing"
        for a in alerts:
            if a.labels.get("alertname", "").lower() == watchdog_name:
                st = (a.status or {}).get("state", "active")
                watchdog_status = "firing" if st == "active" else "suppressed"
                break

        active_only = [
            a
            for a in alerts
            if (a.status or {}).get("state", "active") == "active"
            and a.labels.get("alertname", "").lower() != watchdog_name
        ]

        default_route_alerts: List[Dict[str, Any]] = []
        label_combos: Counter[str] = Counter()
        missing_ann_alerts: List[Dict[str, Any]] = []
        invalid_sev_alerts: List[Dict[str, Any]] = []
        long_firing_alerts: List[Dict[str, Any]] = []

        req_annotations = self._config.required_annotations
        valid_severities = {
            s.lower() for s in self._config.severity_values
        }
        sev_label = self._config.label_severity
        now = utc_now()
        long_firing_cutoff = now - timedelta(hours=check_long_firing_hours)

        for alert in active_only:
            alert_summary = {
                "fingerprint": alert.fingerprint,
                "alertname": alert.labels.get("alertname", "unknown"),
                "labels": alert.labels,
                "annotations": alert.annotations,
                "startsAt": format_rfc3339_utc(
                    parse_rfc3339(alert.startsAt, require_tz=False)
                ),
            }

            if check_default_route and route_tree is not None:
                eval_res = route_tree.evaluate(alert.labels)
                if eval_res.fell_back_to_default:
                    default_route_alerts.append(alert_summary)
                    for key in (
                        self._config.label_service,
                        self._config.label_team,
                        self._config.label_env,
                        "alertname",
                    ):
                        if key in alert.labels:
                            label_combos[f'{key}="{alert.labels[key]}"'] += 1

            if check_missing_annotations and req_annotations:
                missing = [
                    ann
                    for ann in req_annotations
                    if not str(alert.annotations.get(ann, "")).strip()
                ]
                if missing:
                    missing_ann_alerts.append(
                        {**alert_summary, "missing_annotations": missing}
                    )

            sev_val = alert.labels.get(sev_label, "").strip().lower()
            if valid_severities and sev_val not in valid_severities:
                invalid_sev_alerts.append(
                    {
                        **alert_summary,
                        "severity": alert.labels.get(sev_label),
                        "expected_values": sorted(valid_severities),
                    }
                )

            start_dt = parse_rfc3339(alert.startsAt, require_tz=False)
            if start_dt <= long_firing_cutoff:
                firing_hours = round(
                    (now - start_dt).total_seconds() / 3600.0, 1
                )
                long_firing_alerts.append(
                    {**alert_summary, "firing_hours": firing_hours}
                )

        summary_text = (
            f"Audited {len(active_only)} active alerts on '{bid}': "
            f"{len(default_route_alerts)} unrouted (default route '{default_receiver}'), "
            f"{len(missing_ann_alerts)} missing required annotations ({req_annotations}), "
            f"{len(invalid_sev_alerts)} with non-standard '{sev_label}', "
            f"{len(long_firing_alerts)} firing >{check_long_firing_hours}h. "
            f"Watchdog status: {watchdog_status}."
        )

        return {
            "backend_id": bid,
            "total_active_alerts": len(active_only),
            "default_receiver": default_receiver,
            "default_route_count": len(default_route_alerts),
            "default_route_alerts": default_route_alerts[:limit],
            "suggested_matchers": dict(label_combos.most_common(10)),
            "missing_annotations_count": len(missing_ann_alerts),
            "missing_annotations_alerts": missing_ann_alerts[:limit],
            "invalid_severity_count": len(invalid_sev_alerts),
            "invalid_severity_alerts": invalid_sev_alerts[:limit],
            "long_firing_count": len(long_firing_alerts),
            "long_firing_alerts": long_firing_alerts[:limit],
            "watchdog_status": watchdog_status,
            "summary_text": summary_text,
        }

    async def export_config_yaml(self, backend_id: str) -> str:
        """Return the raw YAML config string from `/api/v2/status`."""
        status = await self.get_status(backend_id)
        config_raw = status.get("config", {})
        return (
            config_raw.get("original", "")
            if isinstance(config_raw, dict)
            else ""
        )

    async def get_recent_silence_changes(
        self, backend_id: str, hours: int = 24
    ) -> List[SilenceChange]:
        """Get recent silence create/expire/update events within `hours`."""
        silences, _, _ = await self.list_silences(
            backend_id, limit=500, offset=0
        )
        cutoff = utc_now() - timedelta(hours=hours)
        changes: List[SilenceChange] = []
        for s in silences:
            updated = s.updatedAt or s.startsAt
            updated_utc = parse_rfc3339(updated, require_tz=False)
            start_utc = parse_rfc3339(s.startsAt, require_tz=False)
            if updated_utc >= cutoff:
                matchers_str = ", ".join(
                    f"{m.name}={m.value}" for m in s.matchers
                )
                if s.status and s.status.state == "expired":
                    action = "expired"
                elif abs((updated_utc - start_utc).total_seconds()) > 60:
                    action = "updated"
                else:
                    action = "created"
                changes.append(
                    SilenceChange(
                        silence_id=s.id,
                        action=action,
                        matchers_summary=matchers_str,
                        created_by=s.createdBy,
                        comment=s.comment,
                        timestamp=updated_utc,
                    )
                )
        changes.sort(key=lambda c: c.timestamp, reverse=True)
        return changes

    async def audit_silences(
        self,
        backend_id: str,
        *,
        since_minutes: int = 1440,
        expiring_within_minutes: int = 120,
    ) -> Dict[str, Any]:
        """Comprehensive silence governance audit: changes, policy compliance, stale 0-match, and expiring soon."""
        bid = self.resolve_backend_id(backend_id)
        all_silences, _, _ = await self.list_silences(bid, limit=500, offset=0)
        all_alerts, _, _ = await self.list_alerts(
            bid,
            active=True,
            silenced=True,
            inhibited=True,
            limit=1000,
            offset=0,
        )

        now = utc_now()
        cutoff = now - timedelta(minutes=since_minutes)
        expiring_cutoff = now + timedelta(minutes=expiring_within_minutes)

        changes: List[Dict[str, Any]] = []
        created_count = 0
        expired_count = 0
        updated_count = 0

        active_silences: List[GettableSilence] = []
        non_compliant: List[Dict[str, Any]] = []
        stale_zero_match: List[Dict[str, Any]] = []
        expiring_soon: List[Dict[str, Any]] = []
        long_running: List[Dict[str, Any]] = []

        policy = self.silence_policy

        for s in all_silences:
            updated_dt = parse_rfc3339(
                s.updatedAt or s.startsAt, require_tz=False
            )
            start_dt = parse_rfc3339(s.startsAt, require_tz=False)
            end_dt = parse_rfc3339(s.endsAt, require_tz=False)
            matchers_str = ", ".join(
                f'{m.name}{"=~" if m.isRegex else ("=" if m.isEqual else "!=")}"{m.value}"'
                for m in s.matchers
            )

            if updated_dt >= cutoff:
                if s.status.state == "expired":
                    action = "expired"
                    expired_count += 1
                elif abs((updated_dt - start_dt).total_seconds()) > 60:
                    action = "updated"
                    updated_count += 1
                else:
                    action = "created"
                    created_count += 1
                changes.append(
                    {
                        "silence_id": s.id,
                        "action": action,
                        "matchers_summary": matchers_str,
                        "created_by": s.createdBy,
                        "comment": s.comment,
                        "timestamp": format_rfc3339_utc(updated_dt),
                    }
                )

            if s.status.state == "active":
                active_silences.append(s)

                # Evaluate active silence against SilencePolicy (ignoring past starts_at)
                pol_res = policy.evaluate(
                    matchers=s.matchers,
                    created_by=s.createdBy,
                    comment=s.comment,
                    validate_window=False,
                )
                duration_mins = (end_dt - start_dt).total_seconds() / 60.0
                violations = [v.to_dict() for v in pol_res.violations]
                warnings = [w.to_dict() for w in pol_res.warnings]

                if duration_mins > policy.max_duration_minutes:
                    violations.append(
                        {
                            "rule_id": "SP007",
                            "severity": "error",
                            "message": (
                                f"Active silence duration ({duration_mins:.0f}m) exceeds "
                                f"max policy cap ({policy.max_duration_minutes}m)."
                            ),
                            "remediation": "Shorten or expire long-running silence.",
                        }
                    )
                    long_running.append(
                        {
                            "id": s.id,
                            "created_by": s.createdBy,
                            "comment": s.comment,
                            "duration_minutes": round(duration_mins, 1),
                            "ends_at": format_rfc3339_utc(end_dt),
                            "matchers_summary": matchers_str,
                        }
                    )

                if violations or warnings:
                    non_compliant.append(
                        {
                            "id": s.id,
                            "created_by": s.createdBy,
                            "comment": s.comment,
                            "matchers_summary": matchers_str,
                            "violations": violations,
                            "warnings": warnings,
                        }
                    )

                # Count alerts currently silenced by this silence ID or matching its matchers
                compiled_s = pol_res.compiled_matchers
                matched_count = 0
                for a in all_alerts:
                    silenced_by = (a.status or {}).get("silencedBy") or []
                    if s.id in silenced_by or (
                        compiled_s and match_all(compiled_s, a.labels)
                    ):
                        matched_count += 1

                if matched_count == 0:
                    stale_zero_match.append(
                        {
                            "id": s.id,
                            "created_by": s.createdBy,
                            "comment": s.comment,
                            "matchers_summary": matchers_str,
                            "ends_at": format_rfc3339_utc(end_dt),
                        }
                    )

                if now < end_dt <= expiring_cutoff:
                    rem_mins = round((end_dt - now).total_seconds() / 60.0, 1)
                    expiring_soon.append(
                        {
                            "id": s.id,
                            "created_by": s.createdBy,
                            "comment": s.comment,
                            "matchers_summary": matchers_str,
                            "ends_at": format_rfc3339_utc(end_dt),
                            "remaining_minutes": rem_mins,
                            "silenced_alert_count": matched_count,
                        }
                    )

        changes.sort(key=lambda c: c["timestamp"], reverse=True)

        summary_text = (
            f"Silence audit on '{bid}' (last {since_minutes}m): "
            f"{len(changes)} change(s) ({created_count} created, {updated_count} updated, {expired_count} expired); "
            f"{len(active_silences)} active silence(s), "
            f"{len(non_compliant)} with policy findings, "
            f"{len(stale_zero_match)} matching 0 alerts, "
            f"{len(expiring_soon)} expiring within {expiring_within_minutes}m."
        )

        return {
            "backend_id": bid,
            "since_minutes": since_minutes,
            "total_changes": len(changes),
            "created_count": created_count,
            "expired_count": expired_count,
            "updated_count": updated_count,
            "changes": changes[:100],
            "active_silences_count": len(active_silences),
            "policy_violations_count": len(non_compliant),
            "non_compliant_silences": non_compliant,
            "stale_zero_match_silences": stale_zero_match,
            "expiring_soon_silences": expiring_soon,
            "long_running_silences": long_running,
            "summary_text": summary_text,
        }
