"""In-memory MCP integration tests for the 13 resources, redaction, and bug fixes B3/B8/B12 (T-I5)."""

import json
import pytest
import yaml
from fastmcp import Client
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_all_13_resources_and_redaction_and_bug_fixes(
    fake_argo_service, fake_generator_service
):
    mcp = make_test_server(
        allow_write=False,
        toolsets=["all"],
        prometheus_url=None,  # Unconfigured Prometheus to verify B12 fix
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        static_res = await client.list_resources()
        templates = await client.list_resource_templates()
        all_uris = {str(r.uri) for r in static_res} | {str(t.uriTemplate) for t in templates}

        assert len(all_uris) == 13
        assert "argorollout://health/summary" not in all_uris
        assert "argorollout://history/all" not in all_uris

        # 1. rollouts/detail is concise JSON with healthScore and no YAML dump
        detail_res = await client.read_resource("argorollout://rollouts/default/payments-api/detail")
        detail_json = json.loads(detail_res[0].text)
        assert detail_json["name"] == "payments-api"
        assert detail_json["healthScore"] == 100
        assert detail_json["canaryWeight"] == 25
        assert "managedFields" not in detail_res[0].text

        # 2. rollouts/manifest is sanitized YAML with redacted literal env values
        manifest_res = await client.read_resource("argorollout://rollouts/default/payments-api/manifest")
        manifest_doc = yaml.safe_load(manifest_res[0].text)
        assert "managedFields" not in manifest_doc.get("metadata", {})
        assert "kubectl.kubernetes.io/last-applied-configuration" not in (
            manifest_doc.get("metadata", {}).get("annotations") or {}
        )
        env_list = manifest_doc["spec"]["template"]["spec"]["containers"][0]["env"]
        assert env_list[0]["value"] == "***REDACTED***"
        assert "valueFrom" in env_list[1]

        # 3. history separates revisions from conditions (fixes B3)
        hist_res = await client.read_resource("argorollout://history/default/payments-api")
        hist_json = json.loads(hist_res[0].text)
        assert "revisions" in hist_json
        assert "conditions" in hist_json
        assert hist_json["currentRevision"] == 2
        assert "revision" not in hist_json["conditions"][0]

        # 4. metrics summary returns explicit status="unavailable" when Prometheus is down (fixes B12)
        metrics_res = await client.read_resource("argorollout://metrics/default/payments-api/summary")
        metrics_json = json.loads(metrics_res[0].text)
        assert metrics_json["status"] == "unavailable"
        assert "error" in metrics_json
        assert "requestRate" not in metrics_json

        # 5. rollouts/list surfaces errors instead of returning "[]" (fixes B8)
        fake_argo_service.list_rollouts.side_effect = RuntimeError("Cluster connection refused")
        list_res = await client.read_resource("argorollout://rollouts/list")
        list_json = json.loads(list_res[0].text)
        assert "error" in list_json
        assert "Cluster connection refused" in list_json["error"]
