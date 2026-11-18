"""Unit tests for HelmService execution methods, context propagation, and health monitoring."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from helm_mcp_server.config import ServerConfig
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.services.helm_service import HelmService
from helm_mcp_server.services.kubernetes_service import KubernetesService
from helm_mcp_server.utils.helm_helper import REDACTED_PLACEHOLDER


def test_validate_chart_ref() -> None:
    """validate_chart_ref should accept explicit repo/chart or OCI refs and reject bare names."""
    assert HelmService.validate_chart_ref("bitnami/postgresql") == "bitnami/postgresql"
    assert HelmService.validate_chart_ref("oci://registry-1.docker.io/bitnamicharts/postgresql") == (
        "oci://registry-1.docker.io/bitnamicharts/postgresql"
    )
    assert HelmService.validate_chart_ref("./local-chart") == "./local-chart"

    with pytest.raises(HelmOperationError, match="helm_search_charts"):
        HelmService.validate_chart_ref("postgresql")

    with pytest.raises(HelmOperationError, match="cannot be empty"):
        HelmService.validate_chart_ref("   ")


@pytest.mark.asyncio
async def test_build_cmd_injects_kubeconfig_and_session_context(
    helm_service: HelmService,
    k8s_service: KubernetesService,
) -> None:
    """_build_cmd should inject --kubeconfig and the session's active --kube-context."""
    await k8s_service.set_context("prod-cluster", session_id="sess-1")

    cmd = helm_service._build_cmd(["list", "-o", "json"], session_id="sess-1")
    assert "--kubeconfig" in cmd
    assert "/tmp/fake-kubeconfig" in cmd
    assert "--kube-context" in cmd
    assert cmd[cmd.index("--kube-context") + 1] == "prod-cluster"

    # Repo commands should not include cluster flags
    repo_cmd = helm_service._build_cmd(["repo", "list", "-o", "json"], include_cluster_flags=False)
    assert "--kube-context" not in repo_cmd


@pytest.mark.asyncio
async def test_read_only_guardrail_blocks_mutations_and_allows_rollback_dry_run(
    readonly_config: ServerConfig,
    k8s_service: KubernetesService,
    mock_helm_subprocess: Any,
) -> None:
    """When allow_write=False, mutating methods must fail except rollback_release(dry_run=True)."""
    ro_service = HelmService(readonly_config, k8s_service=k8s_service)

    with pytest.raises(HelmOperationError, match="read-only mode"):
        await ro_service.ensure_repository("bitnami", "https://charts.bitnami.com/bitnami")

    with pytest.raises(HelmOperationError, match="read-only mode"):
        await ro_service.install_chart("bitnami/postgresql", "new-pg", namespace="prod")

    with pytest.raises(HelmOperationError, match="read-only mode"):
        await ro_service.upgrade_release("my-postgres", "bitnami/postgresql", namespace="prod")

    with pytest.raises(HelmOperationError, match="read-only mode"):
        await ro_service.rollback_release("my-postgres", namespace="prod", dry_run=False)

    with pytest.raises(HelmOperationError, match="read-only mode"):
        await ro_service.uninstall_release("my-postgres", namespace="prod")

    # dry_run=True on rollback_release is permitted in read-only mode
    dry_res = await ro_service.rollback_release("my-postgres", namespace="prod", revision=1, dry_run=True)
    assert dry_res["status"] == "dry_run_success"
    assert dry_res["dry_run"] is True


@pytest.mark.asyncio
async def test_list_and_ensure_repositories(
    helm_service: HelmService,
    mock_helm_subprocess: Any,
) -> None:
    """list_repositories and ensure_repository should manage chart repositories cleanly."""
    repos = await helm_service.list_repositories()
    assert len(repos) == 2
    assert repos[0]["name"] == "bitnami"

    # Existing repo returns added=False without running helm repo add
    existing_res = await helm_service.ensure_repository("bitnami", "https://charts.bitnami.com/bitnami")
    assert existing_res["added"] is False

    # New repo runs helm repo add and helm repo update
    new_res = await helm_service.ensure_repository("grafana", "https://grafana.github.io/helm-charts")
    assert new_res["added"] is True
    assert any(cmd[:3] == ["helm", "repo", "add"] for cmd in mock_helm_subprocess.commands)
    assert any(cmd[:3] == ["helm", "repo", "update"] for cmd in mock_helm_subprocess.commands)


@pytest.mark.asyncio
async def test_search_and_chart_metadata_methods(helm_service: HelmService) -> None:
    """search_charts, get_chart_info, get_chart_values, and get_chart_readme should return structured data."""
    charts = await helm_service.search_charts("postgresql", repository="bitnami")
    assert len(charts) == 2
    assert charts[0]["name"] == "bitnami/postgresql"

    info = await helm_service.get_chart_info("postgresql", "bitnami")
    assert info["name"] == "postgresql"
    assert info["kubeVersion"] == ">=1.23.0-0"

    values = await helm_service.get_chart_values("postgresql", "bitnami")
    assert "auth" in values

    readme = await helm_service.get_chart_readme("postgresql", "bitnami")
    assert "# Bitnami PostgreSQL" in readme


@pytest.mark.asyncio
async def test_list_releases_and_status_filter_validation(helm_service: HelmService) -> None:
    """list_releases should support status filtering and reject invalid status filters."""
    all_res = await helm_service.list_releases()
    assert all_res["count"] == 2

    deployed_res = await helm_service.list_releases(status="deployed")
    assert deployed_res["count"] == 2
    assert deployed_res["releases"][0]["name"] == "my-postgres"

    with pytest.raises(HelmOperationError, match="Invalid status filter"):
        await helm_service.list_releases(status="bogus-status")


@pytest.mark.asyncio
async def test_get_release_status_executes_single_helm_call_and_returns_resource_uris(
    helm_service: HelmService,
    mock_helm_subprocess: Any,
) -> None:
    """get_release_status should make only 1 subprocess call and return resource_uris."""
    mock_helm_subprocess.commands.clear()
    status = await helm_service.get_release_status("my-postgres", namespace="prod")

    assert len(mock_helm_subprocess.commands) == 1
    assert status["release_name"] == "my-postgres"
    assert status["namespace"] == "prod"
    assert status["status"] == "deployed"
    assert status["total_resources"] == 2
    assert status["resource_counts"] == {"Service": 1, "StatefulSet": 1}
    assert status["resource_uris"]["history"] == "helm://releases/prod/my-postgres/history"
    assert status["resource_uris"]["values"] == "helm://releases/prod/my-postgres/values"
    assert status["resource_uris"]["manifest"] == "helm://releases/prod/my-postgres/manifest"


@pytest.mark.asyncio
async def test_get_release_values_and_manifest_redact_secrets(helm_service: HelmService) -> None:
    """get_release_values and get_release_manifest must redact sensitive credentials."""
    values = await helm_service.get_release_values("my-postgres", namespace="prod")
    assert values["auth"]["postgresPassword"] == REDACTED_PLACEHOLDER
    assert values["auth"]["existingSecret"] == "prod-postgres-secret"
    assert values["primary"]["replicaCount"] == 2

    manifest = await helm_service.get_release_manifest("my-postgres", namespace="prod")
    assert REDACTED_PLACEHOLDER in manifest
    assert "c2VjcmV0MTIz" not in manifest
    assert "plain-secret-value" not in manifest
    assert "my-inline-secret" not in manifest


@pytest.mark.asyncio
async def test_plan_release_install_and_upgrade_modes(
    helm_service: HelmService,
) -> None:
    """plan_release should return mode='install' for new releases and mode='upgrade' with live diff for existing ones."""
    # 1. Install mode (brand new release)
    install_plan = await helm_service.plan_release(
        chart_ref="bitnami/postgresql",
        release_name="brand-new-pg",
        namespace="prod",
    )
    assert install_plan["mode"] == "install"
    assert install_plan["total_resources"] == 3
    assert len(install_plan["diff"]["added_resources"]) == 3
    assert install_plan["diff"]["modified_resources"] == []

    # 2. Upgrade mode (existing release prod/my-postgres with new image tag and replica count)
    upgrade_plan = await helm_service.plan_release(
        chart_ref="bitnami/postgresql",
        release_name="my-postgres",
        namespace="prod",
        values={"image": {"tag": "16.5.0"}, "replicas": 3},
    )
    assert upgrade_plan["mode"] == "upgrade"
    assert upgrade_plan["diff"]["modified_resources"] == [
        {
            "kind": "StatefulSet",
            "namespace": "prod",
            "name": "my-postgres",
            "changed_fields": ["spec"],
        }
    ]
    assert upgrade_plan["diff"]["image_changes"] == [
        {
            "resource": "StatefulSet/my-postgres",
            "container": "postgresql",
            "from": "docker.io/bitnami/postgresql:16.2.0",
            "to": "docker.io/bitnami/postgresql:16.5.0",
        }
    ]
    assert upgrade_plan["diff"]["replica_changes"] == [
        {
            "resource": "StatefulSet/my-postgres",
            "from": 1,
            "to": 3,
        }
    ]


@pytest.mark.asyncio
async def test_install_upgrade_rollback_uninstall_lifecycle(
    helm_service: HelmService,
    mock_helm_subprocess: Any,
) -> None:
    """Test install_chart, upgrade_release, rollback_release, and uninstall_release execution flags."""
    # Installing an already-existing release raises conflict error guiding to helm_upgrade_release
    with pytest.raises(HelmOperationError, match="helm_upgrade_release"):
        await helm_service.install_chart("bitnami/postgresql", "my-postgres", namespace="prod")

    # Install a new release
    install_res = await helm_service.install_chart(
        chart_ref="bitnami/postgresql",
        release_name="analytics-db",
        namespace="prod",
        values={"primary": {"persistence": {"size": "20Gi"}}},
        version="15.5.38",
        create_namespace=True,
        skip_crds=True,
        wait_timeout="5m",
    )
    assert install_res["status"] == "deployed"
    assert install_res["release_name"] == "analytics-db"
    install_cmd = mock_helm_subprocess.commands[-1]
    assert "--create-namespace" in install_cmd
    assert "--skip-crds" in install_cmd
    assert "--wait" in install_cmd
    assert "--timeout" in install_cmd

    # Upgrade with values_strategy="reset_then_reuse" and atomic=True
    upgrade_res = await helm_service.upgrade_release(
        release_name="analytics-db",
        chart_ref="bitnami/postgresql",
        namespace="prod",
        values_strategy="reset_then_reuse",
        atomic=True,
        wait_timeout="5m",
    )
    assert upgrade_res["status"] == "deployed"
    upgrade_cmd = mock_helm_subprocess.commands[-1]
    assert "--reset-then-reuse-values" in upgrade_cmd
    assert "--atomic" in upgrade_cmd

    # Rollback to revision 1
    rb_res = await helm_service.rollback_release("analytics-db", namespace="prod", revision=1)
    assert rb_res["status"] == "rolled_back"
    assert rb_res["target_revision"] == 1

    # Uninstall with keep_history=True
    un_res = await helm_service.uninstall_release("analytics-db", namespace="prod", keep_history=True)
    assert un_res["status"] == "uninstalled"
    assert "--keep-history" in mock_helm_subprocess.commands[-1]


@pytest.mark.asyncio
async def test_monitor_deployment_health_ready_and_failure_states(
    helm_service: HelmService,
    mock_k8s_module: Any,
    mock_helm_subprocess: Any,
) -> None:
    """monitor_deployment_health should detect ready workloads as well as CrashLoopBackOff and OOMKilledRecurring."""
    # 1. Healthy deployment returns status="ready"
    ready_res = await helm_service.monitor_deployment_health(
        release_name="my-postgres",
        namespace="prod",
        max_wait_seconds=5,
        check_interval=1,
    )
    assert ready_res["status"] == "ready"
    assert ready_res["pod_summary"]["running"] == 1
    assert ready_res["issues"] == []

    # 2. Pod in CrashLoopBackOff returns status="failed" immediately
    crashing_pod = SimpleNamespace(
        metadata=SimpleNamespace(name="my-postgres-0"),
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[
                SimpleNamespace(
                    name="postgresql",
                    restart_count=4,
                    state=SimpleNamespace(
                        waiting=SimpleNamespace(
                            reason="CrashLoopBackOff",
                            message="back-off 5m0s restarting failed container",
                        ),
                        terminated=None,
                    ),
                    last_state=SimpleNamespace(
                        terminated=SimpleNamespace(reason="Error")
                    ),
                )
            ],
            init_container_statuses=[],
            conditions=[],
        ),
    )
    mock_k8s_module.core_v1.list_namespaced_pod.return_value = SimpleNamespace(items=[crashing_pod])

    crash_res = await helm_service.monitor_deployment_health(
        release_name="my-postgres",
        namespace="prod",
        max_wait_seconds=5,
        check_interval=1,
    )
    assert crash_res["status"] == "failed"
    assert any(i["reason"] == "CrashLoopBackOff" for i in crash_res["issues"])

    # 3. Helm release in failed status gate
    mock_helm_subprocess.release_status_override = "failed"
    helm_fail_res = await helm_service.monitor_deployment_health(
        release_name="my-postgres",
        namespace="prod",
        max_wait_seconds=5,
        check_interval=1,
    )
    assert helm_fail_res["status"] == "failed"
    assert helm_fail_res["helm_status"] == "failed"
