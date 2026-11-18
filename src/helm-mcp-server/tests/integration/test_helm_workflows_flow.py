"""End-to-end multi-tool workflow tests through the FastMCP Client."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastmcp import Client

from tests.conftest import get_text


@pytest.mark.asyncio
async def test_e2e_discovery_plan_install_and_monitor_workflow(
    bootstrapped_mcp: Any,
) -> None:
    """Flow 1: Search charts -> check prerequisites -> plan new release -> install release -> monitor health."""
    async with Client(bootstrapped_mcp) as client:
        # Step 1: Search for postgresql chart
        search_res = await client.call_tool(
            "helm_search_charts",
            {"query": "postgresql", "repository": "bitnami"},
        )
        charts = json.loads(get_text(search_res))
        chart_ref = charts[0]["name"]
        chart_version = charts[0]["version"]
        assert chart_ref == "bitnami/postgresql"

        # Step 2: Check cluster prerequisites using chart's metadata resource
        chart_meta = json.loads(
            get_text(await client.read_resource("helm://charts/bitnami/postgresql"))
        )
        prereq_res = await client.call_tool(
            "kubernetes_check_prerequisites",
            {
                "min_kubernetes_version": chart_meta["kubeVersion"],
                "required_api_resources": ["StatefulSet", "Service", "Secret"],
            },
        )
        assert json.loads(get_text(prereq_res))["all_prerequisites_met"] is True

        # Step 3: Plan the new release
        plan_res = await client.call_tool(
            "helm_plan_release",
            {
                "chart_ref": chart_ref,
                "release_name": "payments-db",
                "namespace": "prod",
                "version": chart_version,
            },
        )
        plan_data = json.loads(get_text(plan_res))
        assert plan_data["mode"] == "install"
        assert plan_data["total_resources"] == 3

        # Step 4: Install the release
        install_res = await client.call_tool(
            "helm_install_chart",
            {
                "chart_ref": chart_ref,
                "release_name": "payments-db",
                "namespace": "prod",
                "version": chart_version,
                "create_namespace": True,
                "wait_timeout": "5m",
            },
        )
        assert json.loads(get_text(install_res))["status"] == "deployed"

        # Step 5: Monitor deployment health
        monitor_res = await client.call_tool(
            "helm_monitor_deployment",
            {
                "release_name": "payments-db",
                "namespace": "prod",
                "max_wait_seconds": 10,
                "check_interval": 1,
            },
        )
        assert json.loads(get_text(monitor_res))["status"] == "ready"


@pytest.mark.asyncio
async def test_e2e_upgrade_failed_rollout_and_rollback_workflow(
    bootstrapped_mcp: Any,
    mock_k8s_module: Any,
) -> None:
    """Flow 2: Plan upgrade -> execute upgrade -> detect failed rollout -> inspect history resource -> rollback."""
    async with Client(bootstrapped_mcp) as client:
        # Step 1: Plan upgrade of prod/my-postgres
        plan_res = await client.call_tool(
            "helm_plan_release",
            {
                "chart_ref": "bitnami/postgresql",
                "release_name": "my-postgres",
                "namespace": "prod",
                "values": {"image": {"tag": "16.99.0-broken"}},
            },
        )
        plan_data = json.loads(get_text(plan_res))
        assert plan_data["mode"] == "upgrade"
        assert len(plan_data["diff"]["image_changes"]) == 1

        # Step 2: Execute upgrade
        up_res = await client.call_tool(
            "helm_upgrade_release",
            {
                "release_name": "my-postgres",
                "chart_ref": "bitnami/postgresql",
                "namespace": "prod",
                "values": {"image": {"tag": "16.99.0-broken"}},
                "values_strategy": "reuse",
            },
        )
        assert json.loads(get_text(up_res))["status"] == "deployed"

        # Step 3: Simulate ImagePullBackOff on pod and monitor deployment
        broken_pod = SimpleNamespace(
            metadata=SimpleNamespace(name="my-postgres-0"),
            status=SimpleNamespace(
                phase="Pending",
                container_statuses=[
                    SimpleNamespace(
                        name="postgresql",
                        restart_count=0,
                        state=SimpleNamespace(
                            waiting=SimpleNamespace(
                                reason="ImagePullBackOff",
                                message="Back-off pulling image bitnami/postgresql:16.99.0-broken",
                            ),
                            terminated=None,
                        ),
                        last_state=SimpleNamespace(terminated=None),
                    )
                ],
                init_container_statuses=[],
                conditions=[],
            ),
        )
        mock_k8s_module.core_v1.list_namespaced_pod.return_value = SimpleNamespace(items=[broken_pod])

        mon_res = await client.call_tool(
            "helm_monitor_deployment",
            {"release_name": "my-postgres", "namespace": "prod", "max_wait_seconds": 5},
        )
        mon_data = json.loads(get_text(mon_res))
        assert mon_data["status"] == "failed"
        assert mon_data["issues"][0]["reason"] == "ImagePullBackOff"

        # Step 4: Read release history resource to find last known-good revision
        hist_res = await client.read_resource("helm://releases/prod/my-postgres/history")
        hist_data = json.loads(get_text(hist_res))
        first_revision = hist_data["revisions"][0]["revision"]
        assert first_revision == 1

        # Step 5: Rollback to revision 1
        rb_res = await client.call_tool(
            "helm_rollback_release",
            {
                "release_name": "my-postgres",
                "namespace": "prod",
                "revision": first_revision,
                "wait_timeout": "5m",
            },
        )
        rb_data = json.loads(get_text(rb_res))
        assert rb_data["status"] == "rolled_back"
        assert rb_data["target_revision"] == 1


@pytest.mark.asyncio
async def test_e2e_context_switch_propagates_kube_context_to_helm_cli(
    bootstrapped_mcp: Any,
    mock_helm_subprocess: Any,
) -> None:
    """Flow 3: Calling kubernetes_set_context must propagate --kube-context to subsequent helm CLI subprocesses."""
    async with Client(bootstrapped_mcp) as client:
        # Switch context to prod-cluster
        ctx_res = await client.call_tool(
            "kubernetes_set_context",
            {"context_name": "prod-cluster"},
        )
        assert json.loads(get_text(ctx_res))["context_name"] == "prod-cluster"

        mock_helm_subprocess.commands.clear()

        # Execute helm_list_releases and helm_install_chart
        await client.call_tool("helm_list_releases", {"namespace": "prod"})
        await client.call_tool(
            "helm_install_chart",
            {
                "chart_ref": "bitnami/postgresql",
                "release_name": "ctx-verified-db",
                "namespace": "prod",
            },
        )

        assert len(mock_helm_subprocess.commands) >= 2
        for cmd in mock_helm_subprocess.commands:
            assert "--kube-context" in cmd, f"Expected --kube-context in command: {cmd}"
            idx = cmd.index("--kube-context")
            assert cmd[idx + 1] == "prod-cluster"
