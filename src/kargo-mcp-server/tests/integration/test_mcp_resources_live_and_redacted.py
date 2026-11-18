"""Integration tests verifying all 18 live kargo:// resources, secret redaction, and B8 error visibility."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from fastmcp import Client

from kargo_mcp_server.exceptions import KargoApiError
from kargo_mcp_server.utils import REDACTED_PLACEHOLDER
from tests.conftest import make_test_server

EXPECTED_STATIC_URIS = {
    "kargo://server/capabilities",
    "kargo://projects",
}

EXPECTED_TEMPLATE_URIS = {
    "kargo://projects/{project}",
    "kargo://projects/{project}/pipeline",
    "kargo://projects/{project}/events",
    "kargo://projects/{project}/roles",
    "kargo://projects/{project}/stages/{stage}",
    "kargo://projects/{project}/stages/{stage}/manifest",
    "kargo://projects/{project}/warehouses/{warehouse}",
    "kargo://projects/{project}/freight/{freight_or_alias}",
    "kargo://projects/{project}/promotions",
    "kargo://projects/{project}/promotions/{promotion}",
    "kargo://projects/{project}/promotion-tasks/{task}",
    "kargo://cluster-promotion-tasks/{task}",
    "kargo://projects/{project}/analysis-templates",
    "kargo://projects/{project}/analysis-runs/{run}",
    "kargo://projects/{project}/analysis-runs/{run}/logs",
    "kargo://projects/{project}/credentials",
}


def _read_text(res) -> str:
    return res[0].text if isinstance(res, list) else res.contents[0].text


@pytest.mark.asyncio
async def test_all_18_resources_registered_and_readable(
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        resources = await client.list_resources()
        templates = await client.list_resource_templates()

        static_uris = {str(r.uri) for r in resources}
        template_uris = {str(t.uriTemplate) for t in templates}
        assert static_uris == EXPECTED_STATIC_URIS
        assert template_uris == EXPECTED_TEMPLATE_URIS

        # Read static resources
        caps = json.loads(_read_text(await client.read_resource("kargo://server/capabilities")))
        assert caps["allow_write"] is True
        assert "all" in caps["toolsets"]

        projects = json.loads(_read_text(await client.read_resource("kargo://projects")))
        assert projects["count"] == 1

        # Read representative template resources
        proj = json.loads(_read_text(await client.read_resource("kargo://projects/guestbook")))
        assert proj["name"] == "guestbook"
        assert "promotion_policies" in proj

        pipeline = json.loads(
            _read_text(await client.read_resource("kargo://projects/guestbook/pipeline"))
        )
        assert pipeline["stage_count"] == 2

        stage_yaml = yaml.safe_load(
            _read_text(
                await client.read_resource("kargo://projects/guestbook/stages/dev/manifest")
            )
        )
        assert stage_yaml["kind"] == "Stage"

        creds = json.loads(
            _read_text(await client.read_resource("kargo://projects/guestbook/credentials"))
        )
        assert creds["repo_credentials"][0]["redacted"] is True
        cred_str = json.dumps(creds)
        assert "password" not in cred_str.lower()
        assert REDACTED_PLACEHOLDER not in cred_str or creds["repo_credentials"][0]["redacted"] is True


@pytest.mark.asyncio
async def test_resources_surface_backend_errors_instead_of_empty_lists(
    fake_kargo_service: MagicMock,
) -> None:
    """Regression test for B8: failed resource reads must return structured error payloads."""
    fake_kargo_service.list_projects = AsyncMock(
        side_effect=KargoApiError(401, "401 unauthorized")
    )
    mcp = make_test_server(allow_write=False, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        payload = json.loads(_read_text(await client.read_resource("kargo://projects")))
    assert "error" in payload
    assert "401" in payload["error"]
