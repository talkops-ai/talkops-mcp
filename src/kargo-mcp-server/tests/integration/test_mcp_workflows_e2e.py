"""End-to-end integration tests covering all 5 Kargo operational workflows plus Credentials & RBAC."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from tests.conftest import make_test_server


def _parse(res) -> dict:
    if hasattr(res, "data") and isinstance(res.data, dict):
        return res.data
    return json.loads(res.content[0].text)


@pytest.mark.asyncio
async def test_workflow_1_onboarding_pipeline_e2e(fake_kargo_service: MagicMock) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        # 1. Create Project (preview -> apply)
        p_prev = _parse(
            await client.call_tool(
                "kargo_manage_project",
                {"action": "create", "name": "guestbook", "dry_run": True},
            )
        )
        assert p_prev["status"] == "preview"
        p_apply = _parse(
            await client.call_tool(
                "kargo_manage_project",
                {"action": "create", "name": "guestbook", "dry_run": False},
            )
        )
        assert p_apply["status"] == "success"

        # 2. Apply Warehouse
        wh_apply = _parse(
            await client.call_tool(
                "kargo_apply_warehouse",
                {
                    "project": "guestbook",
                    "name": "main-warehouse",
                    "subscriptions": [
                        {
                            "image": {
                                "repoURL": "ghcr.io/example/guestbook",
                                "constraint": "^1.0.0",
                            }
                        }
                    ],
                    "dry_run": False,
                },
            )
        )
        assert wh_apply["status"] == "success"

        # 3. Apply PromotionTask
        pt_apply = _parse(
            await client.call_tool(
                "kargo_apply_promotion_task",
                {
                    "project": "guestbook",
                    "name": "promote-task",
                    "steps": [
                        {"uses": "git-clone", "config": {"repoURL": "https://github.com/example/gitops.git"}},
                        {
                            "uses": "yaml-update",
                            "config": {
                                "path": "./out/values.yaml",
                                "updates": [{"key": "image.tag", "value": "1.2.0"}],
                            },
                        },
                    ],
                    "dry_run": False,
                },
            )
        )
        assert pt_apply["status"] == "success"

        # 4. Apply Stage
        st_apply = _parse(
            await client.call_tool(
                "kargo_apply_stage",
                {
                    "project": "guestbook",
                    "name": "dev",
                    "requested_freight": [
                        {
                            "origin": {"kind": "Warehouse", "name": "main-warehouse"},
                            "sources": {"direct": True},
                        }
                    ],
                    "promotion_template": {"task_name": "promote-task"},
                    "dry_run": False,
                },
            )
        )
        assert st_apply["status"] == "success"

        # 5. Apply ProjectConfig (auto-promotion)
        cfg_apply = _parse(
            await client.call_tool(
                "kargo_apply_project_config",
                {
                    "project": "guestbook",
                    "promotion_policies": [
                        {"stageSelector": {"name": "dev"}, "autoPromotionEnabled": True}
                    ],
                    "dry_run": False,
                },
            )
        )
        assert cfg_apply["status"] == "success"

        # 6. Refresh Warehouse
        ref = _parse(
            await client.call_tool(
                "kargo_refresh",
                {"project": "guestbook", "kind": "warehouse", "name": "main-warehouse"},
            )
        )
        assert ref["status"] == "success"


@pytest.mark.asyncio
async def test_workflow_2_and_3_query_approve_and_promote_e2e(
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        # Query freight
        fq = _parse(
            await client.call_tool(
                "kargo_query_freight",
                {"project": "guestbook", "stage": "dev"},
            )
        )
        assert fq["total"] >= 1

        # Approve freight for prod
        approved = _parse(
            await client.call_tool(
                "kargo_approve_freight",
                {
                    "project": "guestbook",
                    "freight_or_alias": "vivid-falcon",
                    "stage": "prod",
                    "confirm": True,
                },
            )
        )
        assert approved["status"] == "success"

        # Promote freight to prod
        promoted = _parse(
            await client.call_tool(
                "kargo_promote",
                {
                    "project": "guestbook",
                    "stage": "prod",
                    "freight_alias": "vivid-falcon",
                },
            )
        )
        assert promoted["status"] == "success"


@pytest.mark.asyncio
async def test_workflow_4_and_5_diagnose_rollback_and_reverify_e2e(
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        diag = _parse(
            await client.call_tool(
                "kargo_diagnose_stage",
                {"project": "guestbook", "stage": "dev"},
            )
        )
        assert "HEALTHY" in diag["diagnosis_codes"]
        assert diag["current_freight"] == "freight-120"

        rb = _parse(
            await client.call_tool(
                "kargo_rollback_stage",
                {
                    "project": "guestbook",
                    "stage": "dev",
                    "confirm": True,
                },
            )
        )
        assert rb["status"] == "success"
        assert rb["details"]["target_freight"] == "freight-110"

        reverify = _parse(
            await client.call_tool(
                "kargo_manage_verification",
                {"action": "reverify", "project": "guestbook", "stage": "dev"},
            )
        )
        assert reverify["status"] == "success"


@pytest.mark.asyncio
async def test_credentials_and_rbac_workflows_e2e(fake_kargo_service: MagicMock) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        cred_res = _parse(
            await client.call_tool(
                "kargo_manage_credentials",
                {
                    "action": "create",
                    "project": "guestbook",
                    "name": "github-creds",
                    "credential": {
                        "kind": "repo",
                        "cred_type": "git",
                        "repo_url": "https://github.com/example/gitops.git",
                        "secret_ref": "GH_MAIN",
                    },
                },
            )
        )
        assert cred_res["status"] == "success"

        role_res = _parse(
            await client.call_tool(
                "kargo_manage_roles",
                {
                    "action": "create",
                    "project": "guestbook",
                    "role": "dev-promoter",
                    "permissions": [
                        {
                            "resourceType": "stages",
                            "resourceName": "dev",
                            "verbs": ["promote"],
                        }
                    ],
                    "claims": {"groups": ["devs"]},
                },
            )
        )
        assert role_res["status"] == "success"
