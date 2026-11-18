"""Contract tests verifying every kargo_* tool and kargo:// URI in skills/**/*.md matches registered server primitives."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from tests.conftest import make_test_server

FORBIDDEN_LEGACY_NAMES = {
    "kargo_project_mgmt",
    "kargo_stage_mgmt",
    "kargo_warehouse_mgmt",
    "kargo_freight_mgmt",
    "kargo_promotion_mgmt",
    "kargo_promotion_task_mgmt",
    "kargo_credentials_mgmt",
    "kargo_describe_topology",
    "kargo://best-practices",
    "kargo://promotion-steps",
}

EXPECTED_STAGE_DIAGNOSIS_CODES = {
    "PROMOTION_STEP_FAILED",
    "GIT_OR_REGISTRY_AUTH_ERROR",
    "ARGOCD_SYNC_OR_AUTH_FAILED",
    "VERIFICATION_FAILED",
    "STAGE_HEALTH_DEGRADED",
    "AUTO_PROMOTION_ON_HOLD",
    "PROMOTION_IN_PROGRESS",
    "VERIFICATION_IN_PROGRESS",
    "NO_FREIGHT_DEPLOYED",
    "HEALTHY",
}

EXPECTED_WAREHOUSE_DIAGNOSIS_CODES = {
    "DEPRECATED_SUBSCRIPTION_FIELDS",
    "REPOSITORY_AUTH_FAILED",
    "WAREHOUSE_DISCOVERY_FAILED",
    "NO_ARTIFACTS_DISCOVERED",
    "HEALTHY",
}


def _template_to_regex(uri_template: str) -> re.Pattern[str]:
    escaped = re.escape(uri_template)
    pattern = re.sub(r"\\\{[a-zA-Z0-9_]+\\\}", r"(\{[a-zA-Z0-9_]+\}|[a-zA-Z0-9_.-]+)", escaped)
    return re.compile(f"^{pattern}$")


@pytest.mark.asyncio
async def test_all_skill_markdown_tool_and_resource_references_are_valid(
    server_root: Path,
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        registered_tools = {t.name for t in await client.list_tools()}
        static_uris = {str(r.uri) for r in await client.list_resources()}
        template_uris = {str(t.uriTemplate) for t in await client.list_resource_templates()}

    uri_matchers = [_template_to_regex(u) for u in (static_uris | template_uris)]

    md_files = sorted((server_root / "skills").glob("**/*.md"))
    assert len(md_files) >= 11

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")

        for legacy in FORBIDDEN_LEGACY_NAMES:
            assert legacy not in text, (
                f"{md_file} references removed legacy identifier '{legacy}'"
            )

        for tool_token in re.findall(r"\bkargo_[a-z0-9_]+\b", text):
            assert tool_token in registered_tools, (
                f"{md_file} references unknown tool '{tool_token}'. Registered: {sorted(registered_tools)}"
            )

        for uri_token in re.findall(r"kargo://[a-zA-Z0-9_{}/-]+", text):
            cleaned_uri = uri_token.rstrip("/")
            assert any(rx.match(cleaned_uri) for rx in uri_matchers), (
                f"{md_file} references unregistered resource URI '{cleaned_uri}'"
            )


def test_diagnosis_catalog_documents_every_emitted_diagnosis_code(
    server_root: Path,
) -> None:
    catalog_path = (
        server_root
        / "skills"
        / "troubleshooting-kargo-pipelines"
        / "references"
        / "diagnosis-catalog.md"
    )
    text = catalog_path.read_text(encoding="utf-8")
    for code in EXPECTED_STAGE_DIAGNOSIS_CODES | EXPECTED_WAREHOUSE_DIAGNOSIS_CODES:
        assert code in text, f"Diagnosis code '{code}' is missing from diagnosis-catalog.md"
