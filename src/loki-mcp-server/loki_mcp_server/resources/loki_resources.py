"""Dynamic Loki MCP resources — 9 live state resource endpoints (zero static doc resources).

URIs:
1. loki://server/capabilities
2. loki://system/health
3. loki://schema/labels
4. loki://config/guardrails
5. loki://config/backends
6. loki://rules/groups
7. loki://compactor/delete-requests
8. loki://operator/crs/{namespace}
9. loki://operator/manifests/{kind}/{namespace}/{name}
"""

import json
from typing import Any, Dict, List

from loki_mcp_server.resources.base import BaseResource
from loki_mcp_server.utils.redaction import redact_url, sanitize_k8s_manifest


class LokiResources(BaseResource):
    """Dynamic Loki MCP resource definitions."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        loki = self.loki_service
        k8s = self.kubernetes_service
        config = self.config

        # ──────────────────────────────────────────
        # Resource 1: loki://server/capabilities
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://server/capabilities",
            name="Loki Server Capabilities",
            description=(
                "Server version, active toolsets, write gate status, query guardrails, "
                "and detected Loki 3.x backend capabilities"
            ),
            mime_type="application/json",
        )
        async def server_capabilities() -> str:
            """Return server and backend capability summary as JSON."""
            g = config.guardrails
            build_info = await loki.get_build_info()
            version_str = str(build_info.get("version", "unknown"))
            major_ver = 3
            if version_str and version_str[0].isdigit():
                try:
                    major_ver = int(version_str.split(".")[0])
                except ValueError:
                    major_ver = 3

            payload: Dict[str, Any] = {
                "server": config.name,
                "version": config.version,
                "transport": config.transport,
                "allow_write": config.allow_write,
                "toolsets": list(config.toolsets),
                "kubernetes_enabled": config.kubernetes.enabled,
                "guardrails": {
                    "max_query_bytes": g.max_query_bytes,
                    "max_query_bytes_human": f"{g.max_query_bytes / 1e9:.1f} GB",
                    "max_time_window_hours": g.max_time_window_hours,
                    "max_log_limit": g.max_log_limit,
                    "max_series": g.max_series,
                    "max_points_per_series": g.max_points_per_series,
                    "high_cardinality_threshold": g.high_cardinality_threshold,
                },
                "backend": {
                    "url": redact_url(config.loki.base_url),
                    "org_id": config.auth.org_id or "default",
                    "loki_version": version_str,
                    "loki_major_version": major_ver,
                    "features": {
                        "detected_fields": major_ver >= 3,
                        "structured_metadata": major_ver >= 3,
                        "bloom_filters": major_ver >= 3,
                        "pattern_ingester_supported": True,
                        "index_volume_supported": True,
                        "ruler_api_supported": True,
                        "compactor_delete_api_supported": True,
                    },
                },
            }
            return json.dumps(payload, indent=2)

        # ──────────────────────────────────────────
        # Resource 2: loki://system/health
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://system/health",
            name="Loki System Health",
            description="Loki reachability, readiness status, and label count",
            mime_type="application/json",
        )
        async def system_health() -> str:
            """Return Loki system health as JSON."""
            health = await loki.health_check()
            return json.dumps(health, indent=2)

        # ──────────────────────────────────────────
        # Resource 3: loki://schema/labels
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://schema/labels",
            name="Loki Label Schema",
            description="All available label names in Loki",
            mime_type="application/json",
        )
        async def label_schema() -> str:
            """Return all label names as JSON."""
            labels = await loki.get_labels()
            return json.dumps(
                {
                    "labels": labels,
                    "count": len(labels),
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 4: loki://config/guardrails
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://config/guardrails",
            name="Guardrail Configuration",
            description="Current safety thresholds for query limits, time windows, and cardinality",
            mime_type="application/json",
        )
        async def guardrail_config() -> str:
            """Return current guardrail configuration as JSON."""
            g = config.guardrails
            return json.dumps(
                {
                    "max_query_bytes": g.max_query_bytes,
                    "max_query_bytes_human": f"{g.max_query_bytes / 1e9:.1f} GB",
                    "max_time_window_hours": g.max_time_window_hours,
                    "max_time_window_days": g.max_time_window_hours // 24,
                    "max_log_limit": g.max_log_limit,
                    "max_series": g.max_series,
                    "max_points_per_series": g.max_points_per_series,
                    "high_cardinality_threshold": g.high_cardinality_threshold,
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 5: loki://config/backends
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://config/backends",
            name="Loki Backend Profiles",
            description="Configured Loki backend connection details (URL, tenant, environment) with redacted secrets",
            mime_type="application/json",
        )
        async def backend_profiles() -> str:
            """Return backend connection profile as JSON with secrets redacted."""
            loki_cfg = config.loki
            auth_cfg = config.auth
            return json.dumps(
                {
                    "backend": {
                        "url": redact_url(loki_cfg.base_url),
                        "timeout_seconds": loki_cfg.timeout,
                        "verify_ssl": loki_cfg.verify_ssl,
                        "org_id": auth_cfg.org_id or "default",
                        "auth_type": (
                            "bearer"
                            if auth_cfg.auth_token
                            else "basic"
                            if auth_cfg.basic_auth_user
                            else "none"
                        ),
                        "credentials_redacted": True,
                    },
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 6: loki://rules/groups
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://rules/groups",
            name="Loki Ruler Rule Groups",
            description="Active Loki Ruler alerting and recording rule groups across namespaces",
            mime_type="application/json",
        )
        async def ruler_groups() -> str:
            """Return active Loki Ruler rule groups as JSON."""
            rules_data = await loki.get_rules()
            namespaces: List[str] = (
                list(rules_data.keys()) if isinstance(rules_data, dict) else []
            )
            total_groups = 0
            if isinstance(rules_data, dict):
                for groups in rules_data.values():
                    if isinstance(groups, list):
                        total_groups += len(groups)
            return json.dumps(
                {
                    "namespaces": namespaces,
                    "total_groups": total_groups,
                    "rules": rules_data,
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 7: loki://compactor/delete-requests
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://compactor/delete-requests",
            name="Compactor Log Deletion Requests",
            description="Active and processed Compactor log deletion requests (/loki/api/v1/delete)",
            mime_type="application/json",
        )
        async def compactor_delete_requests() -> str:
            """Return Compactor log deletion requests as JSON."""
            requests = await loki.list_delete_requests()
            return json.dumps(
                {
                    "requests": requests,
                    "count": len(requests),
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 8: loki://operator/crs/{namespace}
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://operator/crs/{namespace}",
            name="Loki Operator Custom Resources",
            description=(
                "Inventory of Kubernetes LokiStack, RulerConfig, AlertingRule, "
                "and RecordingRule CRs in a namespace (use '_all' for cluster-wide)"
            ),
            mime_type="application/json",
        )
        async def operator_crs(namespace: str) -> str:
            """Return Loki Operator CRs in the target namespace."""
            crs = await k8s.list_loki_operator_crs(namespace=namespace)
            return json.dumps(
                {
                    "namespace": namespace,
                    "kubernetes_enabled": config.kubernetes.enabled,
                    "items": crs,
                    "total": len(crs),
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 9: loki://operator/manifests/{kind}/{namespace}/{name}
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://operator/manifests/{kind}/{namespace}/{name}",
            name="Loki Operator CR Manifest",
            description="Sanitized and secret-redacted Loki Operator CR manifest (LokiStack, RulerConfig, AlertingRule, RecordingRule)",
            mime_type="application/json",
        )
        async def operator_manifest(kind: str, namespace: str, name: str) -> str:
            """Return a sanitized Loki Operator CR manifest."""
            manifest = await k8s.get_loki_operator_cr(
                kind=kind,
                namespace=namespace,
                name=name,
            )
            return json.dumps(sanitize_k8s_manifest(manifest), indent=2)
