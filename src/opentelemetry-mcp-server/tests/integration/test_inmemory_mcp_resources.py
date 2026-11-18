"""T-I2 & T-I7: Integration tests for the 14 live MCP Resources using FastMCP Client."""

import json
import os
import pytest
from fastmcp import Client

from opentelemetry_mcp_server.utils.redaction import REDACTED_VALUE

pytestmark = pytest.mark.asyncio

EXPECTED_STATIC_RESOURCES = {
    "otel://server/capabilities",
    "otel://cluster/contexts",
    "otel://operator/status",
}

EXPECTED_TEMPLATE_RESOURCES = {
    "otel://collectors/{namespace}",
    "otel://collector/{namespace}/{name}",
    "otel://collector/{namespace}/{name}/config",
    "otel://collector/{namespace}/{name}/history",
    "otel://k8s-enrichment/{namespace}/{collector}",
    "otel://logs-profile/{namespace}/{collector}",
    "otel://spanmetrics/{namespace}/{collector}",
    "otel://sampling/{namespace}/{collector}",
    "otel://instrumentations/{namespace}",
    "otel://instrumentation/{namespace}/{name}",
    "otel://target-allocator/{namespace}/{name}",
}


async def test_all_14_live_resources_registered_and_static_knowledge_removed(bootstrapped_mcp):
    """T-I2: Verify 3 static + 11 template live resources exist and static language registry is gone."""
    async with Client(bootstrapped_mcp) as client:
        resources = await client.list_resources()
        templates = await client.list_resource_templates()

        static_uris = {str(r.uri) for r in resources}
        template_uris = {str(t.uriTemplate) for t in templates}

        assert static_uris == EXPECTED_STATIC_RESOURCES
        assert template_uris == EXPECTED_TEMPLATE_RESOURCES
        assert len(static_uris) + len(template_uris) == 14

        # Static knowledge resources must NOT exist
        assert "otel://registry/languages" not in static_uris
        assert "otel://lang/{language}" not in template_uris


async def test_read_server_capabilities_cluster_contexts_and_operator_status(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        cap_res = await client.read_resource("otel://server/capabilities")
        cap_data = json.loads(cap_res[0].text)
        assert cap_data["allow_write"] is True
        assert "all" in cap_data["toolsets"]

        ctx_res = await client.read_resource("otel://cluster/contexts")
        ctx_data = json.loads(ctx_res[0].text)
        assert "contexts" in ctx_data
        assert ctx_data["contexts"][0]["is_current"] is True

        op_res = await client.read_resource("otel://operator/status")
        op_data = json.loads(op_res[0].text)
        assert op_data["operator_found"] is True


async def test_read_collector_resources_and_redaction(bootstrapped_mcp, mock_kubernetes_service):
    """T-I7: Verify collector config and CR resources redact inline secrets and do not cache stale reads."""
    cr_with_secret = {
        "apiVersion": "opentelemetry.io/v1beta1",
        "kind": "OpenTelemetryCollector",
        "metadata": {
            "name": "my-collector",
            "namespace": "observability",
            "managedFields": [{"manager": "kubectl"}],
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": '{"secret":"leak"}',
            },
        },
        "spec": {
            "mode": "daemonset",
            "replicas": 1,
            "config": {
                "receivers": {"otlp": {}},
                "processors": {"memory_limiter": {}, "k8sattributes": {}, "batch": {}},
                "exporters": {
                    "otlphttp": {
                        "endpoint": "https://vendor.example.com",
                        "headers": {"Authorization": "Bearer sk_live_supersecret999"},
                    }
                },
                "connectors": {"spanmetrics": {"dimensions": [{"name": "http.method"}]}},
                "service": {
                    "pipelines": {
                        "traces": {
                            "receivers": ["otlp"],
                            "processors": ["memory_limiter", "k8sattributes", "batch"],
                            "exporters": ["otlphttp", "spanmetrics"],
                        },
                        "logs": {
                            "receivers": ["otlp"],
                            "processors": ["memory_limiter", "batch"],
                            "exporters": ["otlphttp"],
                        },
                    }
                },
            },
        },
    }
    mock_kubernetes_service.get_otel_collector.return_value = cr_with_secret
    mock_kubernetes_service.list_otel_collectors.return_value = {"items": [cr_with_secret]}

    async with Client(bootstrapped_mcp) as client:
        list_res = await client.read_resource("otel://collectors/observability")
        list_data = json.loads(list_res[0].text)
        assert list_data["count"] == 1

        detail_res = await client.read_resource("otel://collector/observability/my-collector")
        detail_text = detail_res[0].text
        assert "sk_live_supersecret999" not in detail_text
        assert "managedFields" not in detail_text
        assert "last-applied-configuration" not in detail_text

        cfg_res = await client.read_resource("otel://collector/observability/my-collector/config")
        cfg_text = cfg_res[0].text
        assert "sk_live_supersecret999" not in cfg_text
        assert REDACTED_VALUE in cfg_text

        hist_res = await client.read_resource("otel://collector/observability/my-collector/history")
        hist_data = json.loads(hist_res[0].text)
        assert "has_snapshot" in hist_data
        assert hist_data["collector"] == "observability/my-collector"

        enrich_res = await client.read_resource("otel://k8s-enrichment/observability/my-collector")
        assert "enabled" in json.loads(enrich_res[0].text)

        logs_res = await client.read_resource("otel://logs-profile/observability/my-collector")
        assert json.loads(logs_res[0].text)["enabled"] is True

        sm_res = await client.read_resource("otel://spanmetrics/observability/my-collector")
        assert json.loads(sm_res[0].text)["enabled"] is True

        samp_res = await client.read_resource("otel://sampling/observability/my-collector")
        assert "mode" in json.loads(samp_res[0].text)


async def test_read_instrumentation_and_target_allocator_resources(
    bootstrapped_mcp, mock_kubernetes_service
):
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "fixtures",
        "otel",
        "collector_cr_with_ta.json",
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        ta_cr = json.load(f)
    mock_kubernetes_service.get_otel_collector.return_value = ta_cr

    async with Client(bootstrapped_mcp) as client:
        insts_res = await client.read_resource("otel://instrumentations/default")
        assert json.loads(insts_res[0].text)["count"] >= 1

        inst_res = await client.read_resource("otel://instrumentation/default/my-app")
        assert "default" in inst_res[0].text

        ta_res = await client.read_resource("otel://target-allocator/observability/my-collector")
        ta_data = json.loads(ta_res[0].text)
        assert ta_data["enabled"] is True
        assert ta_data["allocation_strategy"] == "consistent-hashing"
