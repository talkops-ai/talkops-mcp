#!/usr/bin/env python3
"""Offline Markdown report renderer for Traefik AuditReport JSON payloads."""

import argparse
import json
import sys


def render_markdown(report: dict) -> str:
    score = report.get("score", 100)
    counts = report.get("counts_by_severity") or report.get("counts") or {}
    findings = report.get("findings") or []

    lines = [
        "# Traefik v3 Security & Configuration Posture Report",
        "",
        f"- **Posture Score**: `{score}/100`",
        f"- **Summary**: {report.get('summary', 'Audit completed.')}",
        (
            f"- **Counts by Severity**: Critical: `{counts.get('critical', 0)}`, "
            f"High: `{counts.get('high', 0)}`, Medium: `{counts.get('medium', 0)}`, "
            f"Low: `{counts.get('low', 0)}`"
        ),
        "",
        "## Prioritized Findings",
        "",
        "| Check ID | Severity | Category | Target | Title | Remediation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not findings:
        lines.append("| `NONE` | `info` | `-` | `-` | No findings detected | None required |")
    else:
        for f in findings:
            cid = f.get("check_id") or f.get("id") or "UNKNOWN"
            if f.get("resource_kind") or f.get("resource_name"):
                target = f"{f.get('resource_kind', '-')}/{f.get('namespace', '-')}/{f.get('resource_name', '-')}"
            else:
                target = f.get("resource_uri") or "-"
            rem = (
                f.get("remediation")
                or f.get("remediation_tool")
                or f.get("skill_reference")
                or f.get("evidence")
                or "-"
            )
            lines.append(
                f"| `{cid}` | `{f.get('severity', 'low')}` | `{f.get('category', '-')}` | "
                f"`{target}` | {f.get('title', '-')} | {rem} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a Traefik AuditReport JSON payload into Markdown offline."
    )
    parser.add_argument("--report-json", default=None, help="Inline AuditReport JSON string")
    parser.add_argument("--report-file", default=None, help="Path to AuditReport JSON file")
    args = parser.parse_args()

    if args.report_file:
        with open(args.report_file, "r", encoding="utf-8") as fh:
            report = json.load(fh)
    elif args.report_json:
        report = json.loads(args.report_json)
    else:
        report = {
            "score": 88,
            "summary": "Sample audit report (1 high finding).",
            "counts_by_severity": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
            "findings": [
                {
                    "check_id": "TLS-001",
                    "category": "tls",
                    "severity": "high",
                    "resource_kind": "TLSOption",
                    "resource_name": "legacy-tls",
                    "namespace": "default",
                    "title": "Deprecated TLS 1.0/1.1 protocol enabled",
                    "remediation": "Set min_version='VersionTLS12' via traefik_configure_tls_policy.",
                }
            ],
        }
    sys.stdout.write(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
