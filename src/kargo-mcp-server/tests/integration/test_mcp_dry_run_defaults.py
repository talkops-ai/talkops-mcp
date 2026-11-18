"""Integration tests verifying all 6 structural apply tools default to dry_run=True without mutating."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from tests.conftest import make_test_server


def _parse(res) -> dict:
    if hasattr(res, "data") and isinstance(res.data, dict):
        return res.data
    text = res.content[0].text
    return json.loads(text)


@pytest.mark.asyncio
async def test_all_structural_apply_tools_default_to_dry_run_preview(
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        # 1. kargo_manage_project(action="create")
        r1 = _parse(
            await client.call_tool(
                "kargo_manage_project",
                {"action": "create", "name": "new-proj"},
            )
        )
        assert r1["status"] == "preview"
        assert r1["dry_run"] is True
        fake_kargo_service.create_project.assert_not_called()

        # 2. kargo_apply_project_config
        r2 = _parse(
            await client.call_tool(
                "kargo_apply_project_config",
                {
                    "project": "guestbook",
                    "promotion_policies": [
                        {"stageSelector": {"name": "dev"}, "autoPromotionEnabled": True}
                    ],
                },
            )
        )
        assert r2["status"] == "preview"
        assert r2["dry_run"] is True
        fake_kargo_service.upsert_project_config.assert_not_called()

        # 3. kargo_apply_warehouse
        r3 = _parse(
            await client.call_tool(
                "kargo_apply_warehouse",
                {
                    "project": "guestbook",
                    "name": "main-warehouse",
                    "subscriptions": [
                        {"image": {"repoURL": "ghcr.io/org/app", "constraint": "^1.0.0"}}
                    ],
                },
            )
        )
        assert r3["status"] == "preview"
        assert r3["dry_run"] is True
        fake_kargo_service.upsert_warehouse.assert_not_called()

        # 4. kargo_apply_promotion_task
        r4 = _parse(
            await client.call_tool(
                "kargo_apply_promotion_task",
                {
                    "project": "guestbook",
                    "name": "promote-task",
                    "steps": [{"uses": "git-clone", "config": {"repoURL": "https://github.com/org/repo"}}],
                },
            )
        )
        assert r4["status"] == "preview"
        assert r4["dry_run"] is True
        fake_kargo_service.upsert_promotion_task.assert_not_called()

        # 5. kargo_apply_stage
        r5 = _parse(
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
                },
            )
        )
        assert r5["status"] == "preview"
        assert r5["dry_run"] is True
        fake_kargo_service.upsert_stage.assert_not_called()

        # 6. kargo_apply_analysis_template
        r6 = _parse(
            await client.call_tool(
                "kargo_apply_analysis_template",
                {
                    "project": "guestbook",
                    "name": "smoke-test",
                    "spec": {
                        "metrics": [
                            {"name": "ok", "provider": {"web": {"url": "http://svc/health"}}}
                        ]
                    },
                },
            )
        )
        assert r6["status"] == "preview"
        assert r6["dry_run"] is True
        fake_kargo_service.upsert_analysis_template.assert_not_called()
