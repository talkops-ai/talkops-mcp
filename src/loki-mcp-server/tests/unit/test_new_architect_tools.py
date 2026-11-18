"""Tests for the new N->1 Architect tools, redaction utilities, and CLI config flags."""

import json
import os
from unittest.mock import patch

import pytest

from loki_mcp_server.config import Config
from loki_mcp_server.utils.redaction import redact_dict, redact_url, sanitize_k8s_manifest
from tests.conftest import get_text


class TestRedactionAndConfigCLI:
    """Unit tests for redaction utilities and CLI argument overrides."""

    def test_redact_url_strips_basic_auth_and_tokens(self):
        raw = "https://admin:supersecret@loki.internal:3100/loki/api/v1/query?token=abc123&limit=10"
        redacted = redact_url(raw)
        assert "supersecret" not in redacted
        assert "abc123" not in redacted
        assert "limit=10" in redacted

    def test_redact_dict_and_k8s_manifest(self):
        manifest = {
            "apiVersion": "loki.grafana.com/v1",
            "kind": "LokiStack",
            "metadata": {
                "name": "loki-prod",
                "namespace": "logging",
                "managedFields": [{"manager": "kubectl"}],
                "annotations": {
                    "kubectl.kubernetes.io/last-applied-configuration": "{}",
                    "app": "loki",
                },
            },
            "spec": {
                "storage": {
                    "secret": {"name": "loki-s3", "access_key_secret": "topsecret"}
                }
            },
        }
        cleaned = sanitize_k8s_manifest(manifest)
        assert "managedFields" not in cleaned["metadata"]
        assert (
            "kubectl.kubernetes.io/last-applied-configuration"
            not in cleaned["metadata"]["annotations"]
        )
        assert (
            cleaned["spec"]["storage"]["secret"]["access_key_secret"] == "***REDACTED***"
        )
        assert redact_dict({"Authorization": "Bearer xyz"})["Authorization"] == "***REDACTED***"

    def test_cli_flags_override_env(self):
        with patch.dict(os.environ, {"MCP_ALLOW_WRITE": "false"}, clear=False):
            cfg = Config.from_cli_and_env(
                ["--allow-write", "--toolsets", "discovery,rules", "--transport", "http"]
            )
            assert cfg.allow_write is True
            assert cfg.toolsets == ("discovery", "rules")
            assert cfg.transport == "http"
            assert cfg.should_register("discovery", is_write=False) is True
            assert cfg.should_register("rules", is_write=True) is True
            assert cfg.should_register("governance", is_write=True) is False


class TestNewArchitectTools:
    """Tests for loki_summarize_service_logs, loki_compare_periods, loki_correlate_trace_logs, loki_analyze_volume, and loki_get_diagnostics."""

    @pytest.mark.asyncio
    async def test_loki_summarize_service_logs(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_summarize_service_logs",
            {
                "selector": '{app="api-gateway"}',
                "start": "now-1h",
            },
        )
        data = json.loads(get_text(result))
        assert data["selector"] == '{app="api-gateway"}'
        assert "index_stats" in data
        assert "error_summary" in data
        assert "sample_error_streams" in data

    @pytest.mark.asyncio
    async def test_loki_compare_periods(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_compare_periods",
            {
                "selector": '{app="api-gateway"}',
                "start": "now-15m",
                "baseline_offset": "1h",
            },
        )
        data = json.loads(get_text(result))
        assert "current_error_count" in data
        assert "baseline_error_count" in data
        assert "new_error_signatures" in data

    @pytest.mark.asyncio
    async def test_loki_correlate_trace_logs(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_correlate_trace_logs",
            {
                "correlation_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "start": "now-1h",
            },
        )
        data = json.loads(get_text(result))
        assert data["correlation_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert "timeline" in data
        assert "participating_services" in data

    @pytest.mark.asyncio
    async def test_loki_analyze_volume(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_analyze_volume",
            {
                "query": '{namespace="prod"}',
                "start": "now-6h",
            },
        )
        data = json.loads(get_text(result))
        assert data["query"] == '{namespace="prod"}'
        assert "top_producers" in data
        assert "total_attributed_bytes" in data

    @pytest.mark.asyncio
    async def test_loki_get_diagnostics(self, mcp_client):
        result = await mcp_client.call_tool("loki_get_diagnostics", {})
        data = json.loads(get_text(result))
        assert "health" in data
        assert "build_info" in data
        assert data["build_info"]["version"] == "3.2.0"
        assert "ingestion_metrics" in data
        assert data["ingestion_metrics"]["total_discarded_samples"] == 47.0
