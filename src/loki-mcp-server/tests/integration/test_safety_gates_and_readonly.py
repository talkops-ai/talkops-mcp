"""Integration tests for write safety gates, dry_run defaults, and confirmation enforcement."""

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from loki_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import LOKI_BASE_URL, get_text

SAMPLE_RULE_GROUP_YAML = """
name: checkout-alerts
interval: 1m
rules:
  - alert: CheckoutHighErrors
    expr: rate({service_name="checkout"} |= "error" [5m]) > 2
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High error rate on checkout"
"""

SAMPLE_LOKISTACK_CR_YAML = """
apiVersion: loki.grafana.com/v1
kind: LokiStack
metadata:
  name: loki-prod
  namespace: logging
spec:
  size: 1x.small
"""


@pytest.fixture
async def write_mcp_client(mock_loki_http):
    env = {
        "LOKI_URL": LOKI_BASE_URL,
        "MCP_ALLOW_WRITE": "true",
    }
    with patch.dict(os.environ, env, clear=False):
        mcp, _, _ = ServerBootstrap.initialize(["--allow-write"])
        async with Client(transport=mcp) as client:
            yield client


class TestWriteSafetyGates:
    """Verifies dry_run=True defaults and confirm=True / elicitation enforcement across all 4 write tools."""

    @pytest.mark.asyncio
    async def test_upsert_rule_group_dry_run_default(self, write_mcp_client):
        result = await write_mcp_client.call_tool(
            "loki_upsert_rule_group",
            {
                "namespace": "prod",
                "group_name": "checkout-alerts",
                "rules_yaml": SAMPLE_RULE_GROUP_YAML,
            },
        )
        data = json.loads(get_text(result))
        assert data["dry_run"] is True
        assert data["status"] == "dry_run_preview"
        assert "diff" in data

    @pytest.mark.asyncio
    async def test_upsert_rule_group_requires_confirmation(self, write_mcp_client):
        result = await write_mcp_client.call_tool(
            "loki_upsert_rule_group",
            {
                "namespace": "prod",
                "group_name": "checkout-alerts",
                "rules_yaml": SAMPLE_RULE_GROUP_YAML,
                "dry_run": False,
                "confirm": False,
            },
        )
        data = json.loads(get_text(result))
        assert data["status"] == "confirmation_required"
        assert data["approved"] is False

    @pytest.mark.asyncio
    async def test_upsert_rule_group_confirmed_succeeds(self, write_mcp_client):
        result = await write_mcp_client.call_tool(
            "loki_upsert_rule_group",
            {
                "namespace": "prod",
                "group_name": "checkout-alerts",
                "rules_yaml": SAMPLE_RULE_GROUP_YAML,
                "dry_run": False,
                "confirm": True,
            },
        )
        data = json.loads(get_text(result))
        assert data["dry_run"] is False
        assert data["group_name"] == "checkout-alerts"

    @pytest.mark.asyncio
    async def test_delete_rule_group_dry_run_and_confirm(self, write_mcp_client):
        preview = await write_mcp_client.call_tool(
            "loki_delete_rule_group",
            {"namespace": "prod", "group_name": "checkout-alerts"},
        )
        preview_data = json.loads(get_text(preview))
        assert preview_data["dry_run"] is True
        assert preview_data["status"] == "dry_run_preview"

        blocked = await write_mcp_client.call_tool(
            "loki_delete_rule_group",
            {
                "namespace": "prod",
                "group_name": "checkout-alerts",
                "dry_run": False,
                "confirm": False,
            },
        )
        blocked_data = json.loads(get_text(blocked))
        assert blocked_data["status"] == "confirmation_required"

        applied = await write_mcp_client.call_tool(
            "loki_delete_rule_group",
            {
                "namespace": "prod",
                "group_name": "checkout-alerts",
                "dry_run": False,
                "confirm": True,
            },
        )
        applied_data = json.loads(get_text(applied))
        assert applied_data["dry_run"] is False

    @pytest.mark.asyncio
    async def test_manage_delete_requests_create_and_cancel(self, write_mcp_client):
        preview = await write_mcp_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "create",
                "query": '{service_name="auth"} |= "secret"',
                "start": "now-1h",
            },
        )
        preview_data = json.loads(get_text(preview))
        assert preview_data["dry_run"] is True
        assert preview_data["status"] == "dry_run_preview"

        blocked = await write_mcp_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "create",
                "query": '{service_name="auth"} |= "secret"',
                "start": "now-1h",
                "dry_run": False,
                "confirm": False,
            },
        )
        blocked_data = json.loads(get_text(blocked))
        assert blocked_data["status"] == "confirmation_required"

        created = await write_mcp_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "create",
                "query": '{service_name="auth"} |= "secret"',
                "start": "now-1h",
                "dry_run": False,
                "confirm": True,
            },
        )
        created_data = json.loads(get_text(created))
        assert created_data["dry_run"] is False

        # List flow
        listed = await write_mcp_client.call_tool(
            "loki_manage_delete_requests",
            {"action": "list"},
        )
        listed_data = json.loads(get_text(listed))
        assert listed_data["status"] == "ok"
        assert listed_data["count"] >= 1

        # Unbounded whole-namespace deletion without line/metadata filter is blocked
        unbounded = await write_mcp_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "create",
                "query": '{namespace="otel-demo"}',
                "start": "now-7d",
            },
        )
        unbounded_text = get_text(unbounded)
        assert "blocked by safety guardrails" in unbounded_text or "Unbounded" in unbounded_text

        # Cancel flow
        cancel_preview = await write_mcp_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "cancel",
                "request_id": "del-001",
            },
        )
        assert json.loads(get_text(cancel_preview))["dry_run"] is True

        cancel_applied = await write_mcp_client.call_tool(
            "loki_manage_delete_requests",
            {
                "action": "cancel",
                "request_id": "del-001",
                "dry_run": False,
                "confirm": True,
            },
        )
        assert json.loads(get_text(cancel_applied))["dry_run"] is False

    @pytest.mark.asyncio
    async def test_apply_operator_cr_dry_run_and_confirm(self, mock_loki_http):
        mock_k8s = AsyncMock()
        mock_k8s.apply_loki_operator_cr.side_effect = [
            {
                "status": "dry_run_preview",
                "dry_run": True,
                "kind": "LokiStack",
                "namespace": "logging",
                "name": "loki-prod",
                "diff": "--- live\n+++ desired",
            },
            {
                "status": "dry_run_preview",
                "dry_run": True,
                "kind": "LokiStack",
                "namespace": "logging",
                "name": "loki-prod",
                "diff": "--- live\n+++ desired",
            },
            {
                "status": "dry_run_preview",
                "dry_run": True,
                "kind": "LokiStack",
                "namespace": "logging",
                "name": "loki-prod",
                "diff": "--- live\n+++ desired",
            },
            {
                "status": "applied",
                "dry_run": False,
                "kind": "LokiStack",
                "namespace": "logging",
                "name": "loki-prod",
                "diff": "--- live\n+++ desired",
            },
        ]
        from loki_mcp_server.config import Config

        cfg = Config.from_cli_and_env(["--allow-write"])
        mcp, _, _ = ServerBootstrap.build(
            config=cfg, services={"kubernetes_service": mock_k8s}
        )
        async with Client(transport=mcp) as client:
            preview = await client.call_tool(
                "loki_apply_operator_cr",
                {"manifest_yaml": SAMPLE_LOKISTACK_CR_YAML, "namespace": "logging"},
            )
            assert json.loads(get_text(preview))["dry_run"] is True

            blocked = await client.call_tool(
                "loki_apply_operator_cr",
                {
                    "manifest_yaml": SAMPLE_LOKISTACK_CR_YAML,
                    "namespace": "logging",
                    "dry_run": False,
                    "confirm": False,
                },
            )
            assert json.loads(get_text(blocked))["status"] == "confirmation_required"

            applied = await client.call_tool(
                "loki_apply_operator_cr",
                {
                    "manifest_yaml": SAMPLE_LOKISTACK_CR_YAML,
                    "namespace": "logging",
                    "dry_run": False,
                    "confirm": True,
                },
            )
            assert json.loads(get_text(applied))["status"] == "applied"

    @pytest.mark.asyncio
    async def test_toolset_filtering(self, mock_loki_http):
        mcp, _, _ = ServerBootstrap.initialize(["--toolsets", "discovery,analysis"])
        async with Client(transport=mcp) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert names == {
                "loki_get_labels",
                "loki_get_label_values",
                "loki_get_series",
                "loki_get_log_patterns",
                "loki_get_detected_fields",
                "loki_summarize_service_logs",
                "loki_compare_periods",
                "loki_correlate_trace_logs",
                "loki_analyze_volume",
            }
