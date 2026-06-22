"""Loki MCP resources — 8 resource endpoints.

System: loki://system/health
Schema: loki://schema/labels
Config: loki://config/guardrails, loki://config/backends
Reference: loki://reference/logql, loki://reference/best-practices,
           loki://reference/query-templates, loki://reference/label-governance
"""

import json
from pathlib import Path
from typing import Any, Dict

from loki_mcp_server.resources.base import BaseResource

_STATIC_DIR = Path(__file__).parent.parent / "static"


def _load_static_markdown(filename: str, fallback_title: str) -> str:
    """Load a markdown file from the static directory.

    Args:
        filename: Name of the file in the static directory.
        fallback_title: Title to use if file is missing.

    Returns:
        Markdown content or fallback message.
    """
    path = _STATIC_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"# {fallback_title}\n\nReference file not found."


class LokiResources(BaseResource):
    """All Loki MCP resource definitions."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        loki = self.loki_service
        config = self.config

        # ──────────────────────────────────────────
        # Resource 1: loki://system/health
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
        # Resource 2: loki://schema/labels
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
        # Resource 3: loki://config/guardrails
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
                    "high_cardinality_threshold": g.high_cardinality_threshold,
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 4: loki://config/backends
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://config/backends",
            name="Loki Backend Profiles",
            description="Configured Loki backend connection details (URL, tenant, environment)",
            mime_type="application/json",
        )
        async def backend_profiles() -> str:
            """Return backend connection profile as JSON."""
            loki_cfg = config.loki
            auth_cfg = config.auth
            return json.dumps(
                {
                    "backend": {
                        "url": loki_cfg.base_url,
                        "timeout_seconds": loki_cfg.timeout,
                        "verify_ssl": loki_cfg.verify_ssl,
                        "org_id": auth_cfg.org_id or "default",
                        "auth_type": (
                            "bearer" if auth_cfg.auth_token
                            else "basic" if auth_cfg.basic_auth_user
                            else "none"
                        ),
                    },
                },
                indent=2,
            )

        # ──────────────────────────────────────────
        # Resource 5: loki://reference/logql
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://reference/logql",
            name="LogQL Quick Reference",
            description="LogQL syntax guide: stream selectors, line filters, parsers, metric queries",
            mime_type="text/markdown",
        )
        async def logql_reference() -> str:
            """Return the LogQL quick reference as markdown."""
            return _load_static_markdown("logql_reference.md", "LogQL Quick Reference")

        # ──────────────────────────────────────────
        # Resource 6: loki://reference/best-practices
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://reference/best-practices",
            name="Loki Best Practices",
            description="Cardinality rules, pattern parser vs regex, structured metadata, pipeline order",
            mime_type="text/markdown",
        )
        async def best_practices() -> str:
            """Return Loki best practices as markdown."""
            return _load_static_markdown("best_practices.md", "Loki Best Practices")

        # ──────────────────────────────────────────
        # Resource 7: loki://reference/query-templates
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://reference/query-templates",
            name="LogQL Query Templates",
            description="Common incident, debug, audit, and performance LogQL query patterns",
            mime_type="text/markdown",
        )
        async def query_templates() -> str:
            """Return LogQL query templates as markdown."""
            return _load_static_markdown("query_templates.md", "LogQL Query Templates")

        # ──────────────────────────────────────────
        # Resource 8: loki://reference/label-governance
        # ──────────────────────────────────────────
        @mcp_instance.resource(
            "loki://reference/label-governance",
            name="Label Governance Guide",
            description="Label naming conventions, cardinality rules, structured metadata guidance",
            mime_type="text/markdown",
        )
        async def label_governance() -> str:
            """Return label governance guide as markdown."""
            return _load_static_markdown("label_governance.md", "Label Governance Guide")
