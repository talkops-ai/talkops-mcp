"""Unit tests for JSON-string coercion on MCP tool Dict/List arguments."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP

from prometheus_mcp_server.tools.diagnostics.diagnostics_tools import DiagnosticsTools
from prometheus_mcp_server.tools.exporter.exporter_tools import ExporterTools
from prometheus_mcp_server.tools.rules.rules_tools import RulesTools
from prometheus_mcp_server.tools.scrape_config.scrape_config_tools import (
    ScrapeConfigTools,
)
from prometheus_mcp_server.utils.param_coercion import coerce_json_value


def test_coerce_json_value_parses_dicts_lists_and_quoted_keys() -> None:
    raw = '{"selector":{"matchLabels":{"\\"app.kubernetes.io/name\\"":"frontend-proxy"}},"endpoints":[{"port":"envoy-admin"}]}'
    out = coerce_json_value(raw)
    assert isinstance(out, dict)
    assert out["selector"]["matchLabels"] == {"app.kubernetes.io/name": "frontend-proxy"}

    raw_list = '[{"interval":"1m","input_series":[]}]'
    out_list = coerce_json_value(raw_list)
    assert isinstance(out_list, list)
    assert out_list[0]["interval"] == "1m"


@pytest.mark.asyncio
async def test_fastmcp_accepts_stringified_json_dict_and_list_arguments() -> None:
    mcp = FastMCP("test-prom")
    prom_svc = MagicMock()
    prom_svc.is_write_allowed.return_value = True
    prom_svc.get_alerts = AsyncMock(return_value=[])
    k8s_svc = MagicMock()
    k8s_svc.get_servicemonitor_required_labels = AsyncMock(
        return_value={"release": "kube-prometheus-stack"}
    )
    k8s_svc.get_rule_required_labels = AsyncMock(
        return_value={"release": "kube-prometheus-stack"}
    )
    k8s_svc.discover_service = AsyncMock(return_value=None)
    k8s_svc.upsert_rule_group_crd = AsyncMock(
        return_value={
            "action": "created",
            "crd_name": "test-rules",
            "namespace": "otel-demo",
            "group_name": "test.rules",
            "sibling_group_count": 0,
            "manifest": {},
        }
    )

    locator = {
        "prometheus_service": prom_svc,
        "kubernetes_service": k8s_svc,
        "toolsets": ["all"],
        "allow_write": True,
    }
    ScrapeConfigTools(locator).register(mcp)
    RulesTools(locator).register(mcp)
    ExporterTools(locator).register(mcp)
    DiagnosticsTools(locator).register(mcp)

    # 1. Stringified `spec` on prom_apply_scrape_config (reproduces exact agy call_mcp_tool behavior)
    scrape_tool = await mcp.get_tool("prom_apply_scrape_config")
    res_scrape = await scrape_tool.run(
        {
            "backend_id": "default",
            "kind": "ServiceMonitor",
            "name": "frontend-proxy-envoy-monitor",
            "namespace": "otel-demo",
            "dry_run": True,
            "spec": json.dumps(
                {
                    "selector": {"matchLabels": {"app.kubernetes.io/name": "frontend-proxy"}},
                    "endpoints": [{"port": "envoy-admin", "path": "/stats/prometheus"}],
                }
            ),
        }
    )
    assert "frontend-proxy-envoy-monitor" in str(res_scrape)

    # 2. Stringified `rule_group` + `unit_tests` on prom_validate_rules
    val_tool = await mcp.get_tool("prom_validate_rules")
    res_val = await val_tool.run(
        {
            "rule_group": json.dumps(
                {
                    "name": "otel-demo.rules",
                    "interval": "1m",
                    "rules": [
                        {
                            "record": "job:http_requests:rate5m",
                            "expr": "sum by (job) (rate(http_requests_total[5m]))",
                        }
                    ],
                }
            ),
            "unit_tests": json.dumps([]),
        }
    )
    assert "valid" in str(res_val)

    # 3. Stringified `exporter_config` on prom_install_exporter
    exp_tool = await mcp.get_tool("prom_install_exporter")
    res_exp = await exp_tool.run(
        {
            "exporter_type": "postgres_exporter",
            "namespace": "otel-demo",
            "release_name": "otel-demo-pg-exporter",
            "dry_run": True,
            "exporter_config": json.dumps(
                {
                    "secret_env": {
                        "DATA_SOURCE_NAME": {"name": "otel-demo-pg-dsn", "key": "dsn"}
                    }
                }
            ),
        }
    )
    assert "otel-demo-pg-exporter" in str(res_exp)
