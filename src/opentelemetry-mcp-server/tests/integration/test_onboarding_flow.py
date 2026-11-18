"""End-to-End Workflow Test: Workload Instrumentation Onboarding Flow.

Matches the `instrumenting-kubernetes-workloads` skill workflow:
  1. Read `otel://server/capabilities` and `otel://operator/status`
  2. Discover workloads via `otel_list_workloads`
  3. Create/patch Instrumentation CR via `otel_patch_instrumentation(dry_run=True)`
  4. Enable workload instrumentation via `otel_manage_workload_instrumentation(dry_run=True)`
  5. Verify end-to-end delivery via `otel_verify_instrumentation`
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_onboarding_flow(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        # 1. Preconditions
        cap = json.loads((await client.read_resource("otel://server/capabilities"))[0].text)
        assert cap["allow_write"] is True

        op = json.loads((await client.read_resource("otel://operator/status"))[0].text)
        assert op["operator_found"] is True

        # 2. List workloads
        wl_res = await client.call_tool("otel_list_workloads", {"namespace": "default"})
        wl_data = json.loads(wl_res.content[0].text)
        assert len(wl_data["items"]) > 0

        # 3. Preview Instrumentation CR
        inst_res = await client.call_tool(
            "otel_patch_instrumentation",
            {
                "namespace": "default",
                "name": "default-inst",
                "collector_endpoint": "http://otel-collector.observability.svc:4317",
                "languages": ["java", "python"],
                "dry_run": True,
            },
        )
        inst_data = json.loads(inst_res.content[0].text)
        assert inst_data["dry_run"] is True

        # 4. Preview workload injection annotation
        manage_res = await client.call_tool(
            "otel_manage_workload_instrumentation",
            {
                "namespace": "default",
                "workload_name": "frontend-service",
                "workload_kind": "Deployment",
                "action": "enable",
                "language": "java",
                "dry_run": True,
            },
        )
        manage_data = json.loads(manage_res.content[0].text)
        assert manage_data["dry_run"] is True

        # 5. Verify instrumentation
        ver_res = await client.call_tool(
            "otel_verify_instrumentation",
            {"namespace": "default", "workload_name": "frontend-service", "workload_kind": "Deployment"},
        )
        ver_data = json.loads(ver_res.content[0].text)
        assert "findings" in ver_data
