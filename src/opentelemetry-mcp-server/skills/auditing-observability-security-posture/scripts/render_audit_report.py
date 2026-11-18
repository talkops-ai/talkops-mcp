#!/usr/bin/env python3
"""Offline Markdown report generator for otel_audit_security_posture JSON output.

Usage:
    python scripts/render_audit_report.py --input audit_output.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def render_markdown(data: dict) -> str:
    findings = data.get("findings") or []
    if "compliant" in data:
        compliant = bool(data["compliant"])
    else:
        compliant = len(findings) == 0 and str(data.get("risk_level", "low")).lower() in ("low", "none")
    status_badge = "COMPLIANT" if compliant else "NON-COMPLIANT"
    namespace = data.get("namespace") or "all-namespaces"
    collectors_audited = data.get("collectors_audited", 0)
    ebpf_audited = data.get("ebpf_daemonsets_audited", data.get("total_ebpf_pods", 0))
    rbac_audited = data.get("cluster_roles_audited", data.get("rbac_roles_audited", 0))

    lines = [
        "# OpenTelemetry Security Posture Audit Report",
        "",
        f"- **Status**: `{status_badge}`",
        f"- **Scope**: `{namespace}`",
        f"- **Collectors Audited**: `{collectors_audited}`",
        f"- **eBPF DaemonSets Audited**: `{ebpf_audited}`",
        f"- **ClusterRoles Audited**: `{rbac_audited}`",
        f"- **Total Findings**: `{len(findings)}`",
        "",
        "## Findings Summary",
        "",
    ]

    if not findings:
        lines.append("No security findings detected. All audited resources meet hardening invariants.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Severity | Code | Component / Field | Message | Remediation |",
            "|---|---|---|---|---|",
        ]
    )
    for f in findings:
        sev = f.get("severity", "WARNING")
        code = f.get("code", "UNKNOWN")
        comp = f.get("component") or f.get("field_path") or "collector"
        msg = (f.get("message") or "").replace("|", "\\|")
        rem = (f.get("remediation") or f.get("next_tool_hint") or "").replace("|", "\\|")
        lines.append(f"| `{sev}` | `{code}` | `{comp}` | {msg} | {rem} |")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a Markdown compliance report from otel_audit_security_posture JSON."
    )
    parser.add_argument("--input", required=True, help="Path to audit JSON file.")
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error: Invalid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict):
        print("Error: Audit JSON root must be an object", file=sys.stderr)
        return 1

    print(render_markdown(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
