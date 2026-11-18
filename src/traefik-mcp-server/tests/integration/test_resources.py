"""Integration tests for all 12 read-only traefik:// resources (R1-R12)."""

import json
import pytest
from fastmcp.client import Client


@pytest.mark.asyncio
async def test_all_12_traefik_resources_return_sanitized_json(mcp_ro):
    uris_to_test = [
        "traefik://server/capabilities",
        "traefik://cluster/contexts",
        "traefik://instance/static-config",
        "traefik://runtime/health",
        "traefik://runtime/http",
        "traefik://routes/default",
        "traefik://manifests/IngressRoute/default/payments-route",
        "traefik://policies/default",
        "traefik://certificates/default",
        "traefik://gateway/default",
        "traefik://metrics/default/payments-wrr/summary",
        "traefik://schema/Middleware",
    ]
    async with Client(mcp_ro) as client:
        for uri in uris_to_test:
            res = await client.read_resource(uri)
            text = res[0].text
            parsed = json.loads(text)
            assert isinstance(parsed, dict), f"Resource {uri} did not return a JSON object"

        # R7: Verify managedFields and last-applied-configuration are stripped from manifests
        manifest_res = await client.read_resource("traefik://manifests/IngressRoute/default/payments-route")
        manifest_obj = json.loads(manifest_res[0].text)
        assert "managedFields" not in manifest_obj["manifest"]["metadata"]
        assert "kubectl.kubernetes.io/last-applied-configuration" not in (
            manifest_obj["manifest"]["metadata"].get("annotations") or {}
        )

        # R9: Verify private key material is never exposed in certificates inventory
        certs_res = await client.read_resource("traefik://certificates/default")
        assert "SUPER_SECRET_PRIVATE_KEY_BASE64" not in certs_res[0].text
        certs_obj = json.loads(certs_res[0].text)
        assert certs_obj["count"] == 1
        assert "*.example.com" in certs_obj["certificates"][0]["sans"]
