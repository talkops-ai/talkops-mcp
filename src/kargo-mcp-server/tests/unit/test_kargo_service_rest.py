"""Unit tests for KargoService REST endpoints using respx (B1, B2, B3, B7, B9 regressions)."""

from __future__ import annotations

import httpx
import pytest
import respx

from kargo_mcp_server.config import KargoConfig, ServerConfig
from kargo_mcp_server.services import KargoService


def _make_service() -> KargoService:
    cfg = ServerConfig(
        allow_write=True,
        default_project="guestbook",
        kargo=KargoConfig(
            base_url="https://kargo.test:8443",
            admin_password="test-password",
        ),
    )
    return KargoService(cfg)


@pytest.mark.asyncio
@respx.mock
async def test_promotion_tasks_use_hyphenated_rest_endpoint() -> None:
    """Regression test for B1: Kargo v1.12 uses /v1beta1/projects/{project}/promotion-tasks."""
    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    route = respx.get(
        "https://kargo.test:8443/v1beta1/projects/guestbook/promotion-tasks"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "PromotionTask",
                        "metadata": {"name": "promote-task", "namespace": "guestbook"},
                        "spec": {"steps": [{"uses": "git-clone"}]},
                    }
                ]
            },
        )
    )
    svc = _make_service()
    tasks = await svc.list_promotion_tasks("guestbook")
    assert route.called
    assert len(tasks) == 1
    assert tasks[0]["metadata"]["name"] == "promote-task"


@pytest.mark.asyncio
@respx.mock
async def test_promote_to_stage_uses_native_endpoint_and_allows_repeat_promotions() -> None:
    """Regression test for B2: native POST /v1beta1/projects/{p}/stages/{s}/promotions."""
    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    call_count = 0

    def _promo_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        promo_doc = {
            "apiVersion": "kargo.akuity.io/v1alpha1",
            "kind": "Promotion",
            "metadata": {
                "name": f"dev.01j9.{call_count}",
                "namespace": "guestbook",
            },
            "spec": {"stage": "dev", "freight": "freight-120"},
            "status": {"phase": "Pending"},
        }
        body = promo_doc if call_count == 1 else {"promotion": promo_doc}
        return httpx.Response(201, json=body)

    route = respx.post(
        "https://kargo.test:8443/v1beta1/projects/guestbook/stages/dev/promotions"
    ).mock(side_effect=_promo_handler)

    svc = _make_service()
    p1 = await svc.promote_to_stage("guestbook", "dev", freight="freight-120")
    p2 = await svc.promote_to_stage("guestbook", "dev", freight="freight-120")
    assert route.call_count == 2
    assert p1.metadata.name == "dev.01j9.1"
    assert p2.metadata.name == "dev.01j9.2"


@pytest.mark.asyncio
@respx.mock
async def test_project_config_upsert_uses_dedicated_resource_not_project_spec() -> None:
    """Regression test for B3: promotionPolicies and webhookReceivers live on ProjectConfig."""
    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    put_route = respx.put("https://kargo.test:8443/v1beta1/resources").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "updatedResourceManifest": {
                            "apiVersion": "kargo.akuity.io/v1alpha1",
                            "kind": "ProjectConfig",
                            "metadata": {"name": "guestbook", "namespace": "guestbook"},
                            "spec": {
                                "promotionPolicies": [
                                    {
                                        "stageSelector": {"name": "dev"},
                                        "autoPromotionEnabled": True,
                                    }
                                ]
                            },
                        }
                    }
                ]
            },
        )
    )

    svc = _make_service()
    cfg_obj = await svc.upsert_project_config(
        "guestbook",
        spec={
            "promotionPolicies": [
                {"stageSelector": {"name": "dev"}, "autoPromotionEnabled": True}
            ]
        },
    )
    assert put_route.called
    assert cfg_obj.spec.promotion_policies[0].auto_promotion_enabled is True


@pytest.mark.asyncio
@respx.mock
async def test_build_merged_stage_manifest_preserves_existing_spec_and_blocks_cycles() -> None:
    """Regression test for B7: Stage update merges existing fields and checks DAG cycles."""
    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    respx.get("https://kargo.test:8443/v1beta1/projects/guestbook/stages/dev").mock(
        return_value=httpx.Response(
            200,
            json={
                "apiVersion": "kargo.akuity.io/v1alpha1",
                "kind": "Stage",
                "metadata": {"name": "dev", "namespace": "guestbook"},
                "spec": {
                    "requestedFreight": [
                        {
                            "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                            "sources": {"direct": True},
                        }
                    ],
                    "promotionTemplate": {
                        "spec": {"steps": [{"task": {"name": "existing-task"}}]}
                    },
                },
            },
        )
    )
    respx.get("https://kargo.test:8443/v1beta1/projects/guestbook/stages").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "Stage",
                        "metadata": {"name": "dev", "namespace": "guestbook"},
                        "spec": {"requestedFreight": []},
                    },
                    {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "Stage",
                        "metadata": {"name": "prod", "namespace": "guestbook"},
                        "spec": {
                            "requestedFreight": [
                                {
                                    "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                                    "sources": {"direct": False, "stages": ["dev"]},
                                }
                            ]
                        },
                    },
                ]
            },
        )
    )

    svc = _make_service()
    manifest = await svc.build_merged_stage_manifest(
        "guestbook",
        "dev",
        spec_updates={"verification": {"analysisTemplates": [{"name": "smoke-test"}]}},
    )
    assert manifest["spec"]["promotionTemplate"]["spec"]["steps"] == [
        {"task": {"name": "existing-task"}}
    ]
    assert manifest["spec"]["verification"]["analysisTemplates"] == [{"name": "smoke-test"}]

    with pytest.raises(ValueError, match="cycle"):
        await svc.build_merged_stage_manifest(
            "guestbook",
            "dev",
            spec_updates={
                "requestedFreight": [
                    {
                        "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                        "sources": {"direct": False, "stages": ["prod"]},
                    }
                ]
            },
        )


def test_resolve_secret_material_reads_server_env_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for B9: credentials resolve strictly from server-side env/file."""
    monkeypatch.setenv("KARGO_CRED_GH_MAIN_USERNAME", "octocat")
    monkeypatch.setenv("KARGO_CRED_GH_MAIN_PASSWORD", "ghp_secret_token")

    svc = _make_service()
    resolved = svc.resolve_secret_material(secret_ref="GH_MAIN")
    assert resolved["username"] == "octocat"
    assert resolved["password"] == "ghp_secret_token"


@pytest.mark.asyncio
@respx.mock
async def test_create_role_uses_kargo_v112_metadata_and_normalizes_resource_rules() -> None:
    """Regression test: POST /v1beta1/projects/{p}/roles requires metadata.name and PolicyRule format."""
    import json as _json

    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    captured: dict = {}

    def _role_handler(request: httpx.Request) -> httpx.Response:
        captured.update(_json.loads(request.content.decode()))
        return httpx.Response(201, json=captured)

    respx.post("https://kargo.test:8443/v1beta1/projects/guestbook/roles").mock(
        side_effect=_role_handler
    )

    svc = _make_service()
    await svc.create_role(
        "guestbook",
        "release-approver",
        claims={"groups": ["sre"]},
        rules=[{"resourceType": "stages", "resourceName": "prod", "verbs": ["promote"]}],
        description="Prod release approvers",
    )
    assert captured["metadata"]["name"] == "release-approver"
    assert captured["metadata"]["namespace"] == "guestbook"
    assert captured["rules"] == [
        {
            "apiGroups": ["kargo.akuity.io"],
            "resources": ["stages"],
            "resourceNames": ["prod"],
            "verbs": ["promote"],
        }
    ]


@pytest.mark.asyncio
@respx.mock
async def test_create_freight_populates_placeholder_metadata_name() -> None:
    """Regression test: POST /v1beta1/resources Freight requires non-empty metadata.name for webhook mutation."""
    import json as _json

    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    captured: dict = {}

    def _res_handler(request: httpx.Request) -> httpx.Response:
        captured.update(_json.loads(request.content.decode()))
        return httpx.Response(
            201,
            json={"results": [{"createdResourceManifest": {**captured, "metadata": {"name": "sha1-computed", "namespace": "guestbook"}}}]},
        )

    respx.post("https://kargo.test:8443/v1beta1/resources").mock(side_effect=_res_handler)
    svc = _make_service()
    out = await svc.create_freight(
        "guestbook",
        "main-warehouse",
        artifacts={"charts": [{"repoURL": "https://example.com/charts", "name": "app", "version": "0.1.0"}]},
        alias="manual-rc1",
    )
    assert captured["metadata"]["name"] == "manual-rc1"
    assert out["metadata"]["name"] == "sha1-computed"


def test_chart_subscription_maps_version_and_constraint_to_semver_constraint() -> None:
    """Regression test: Kargo v1.12 ChartDiscoverySubscription evaluates semverConstraint."""
    from kargo_mcp_server.utils.warehouse_spec_builder import build_warehouse_spec

    spec = build_warehouse_spec(
        subscriptions=[
            {"type": "chart", "repo_url": "https://talkops-ai.github.io/OTEL-APP", "chart_name": "frontend-proxy", "version": "^0.1.0"}
        ]
    )
    assert spec["subscriptions"][0]["chart"]["semverConstraint"] == "^0.1.0"


def test_validate_promotion_steps_allows_create_target_branch_on_git_push_only() -> None:
    """Regression test: createTargetBranch is valid on git-push and rejected on git-open-pr."""
    from kargo_mcp_server.utils.kargo_helpers import validate_promotion_steps

    errs_ok, _ = validate_promotion_steps(
        [{"uses": "git-push", "config": {"path": "./out", "createTargetBranch": True}}]
    )
    assert errs_ok == []

    errs_bad, _ = validate_promotion_steps(
        [{"uses": "git-open-pr", "config": {"repoURL": "https://example.com/r.git", "createTargetBranch": True}}]
    )
    assert any("createTargetBranch" in e for e in errs_bad)


@pytest.mark.asyncio
@respx.mock
async def test_get_analysis_run_logs_falls_back_on_http_501() -> None:
    """Regression test: HTTP 501 on /logs synthesizes metric execution summary from get_analysis_run."""
    respx.post("https://kargo.test:8443/v1beta1/login").mock(
        return_value=httpx.Response(200, json={"idToken": "test-jwt"})
    )
    respx.get("https://kargo.test:8443/v1beta1/projects/guestbook/analysis-runs/ar-1/logs").mock(
        return_value=httpx.Response(501, json={"error": "AnalysisRun log streaming is not configured"})
    )
    respx.get("https://kargo.test:8443/v1beta1/projects/guestbook/analysis-runs/ar-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": {
                    "phase": "Failed",
                    "metricResults": [
                        {
                            "name": "checkout-error-rate",
                            "phase": "Failed",
                            "message": "result 0.08 >= 0.05",
                            "measurements": [{"phase": "Failed", "value": "[0.08]"}],
                        }
                    ],
                }
            },
        )
    )
    svc = _make_service()
    logs = await svc.get_analysis_run_logs("guestbook", "ar-1")
    assert "checkout-error-rate" in logs
    assert "0.08" in logs


def test_resolve_secret_material_does_not_leak_default_repo_creds_into_unknown_named_ref() -> None:
    """Regression test: unknown named secret_ref must not silently fall back to KARGO_REPO_*."""
    svc = _make_service()
    svc._kargo.repo_username = "default-bot"
    svc._kargo.repo_password = "default-password"
    assert svc.resolve_secret_material(secret_ref="nonexistent_ref") == {}
    assert svc.resolve_secret_material(secret_ref="default")["username"] == "default-bot"
