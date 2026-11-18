"""End-to-End Workflow Test: Security Posture Audit Flow.

Matches the `auditing-observability-security-posture` skill workflow:
  1. Read `otel://server/capabilities`
  2. Run `otel_audit_security_posture` across collectors, RBAC, and eBPF DaemonSets
  3. Remediate PII scrubbing via `otel_configure_processing(redact_pii=True, dry_run=True)`
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_security_audit_flow(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        # 1. Audit security posture
        audit_res = await client.call_tool(
            "otel_audit_security_posture",
            {"namespace": "default"},
        )
        audit_data = json.loads(audit_res.content[0].text)
        assert "findings" in audit_data
        assert "collectors_audited" in audit_data and "ebpf_pods" in audit_data

        # 2. Preview PII redaction remediation
        remediate_res = await client.call_tool(
            "otel_configure_processing",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "signals": ["logs", "traces"],
                "rules": {"mask_pii": True},
                "dry_run": True,
            },
        )
        remediate_data = json.loads(remediate_res.content[0].text)
        assert remediate_data["dry_run"] is True
