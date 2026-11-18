#!/usr/bin/env python3
"""Offline workload manifest linter for OpenTelemetry auto-instrumentation compatibility.

Usage:
    python scripts/lint_workload_manifest.py --file deployment.yaml --language go
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

SUPPORTED_LANGUAGES = ("java", "python", "nodejs", "dotnet", "go", "apache-httpd", "nginx")


def lint_workload(doc: dict, language: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    kind = doc.get("kind", "")
    if kind not in ("Deployment", "StatefulSet", "DaemonSet"):
        findings.append(
            {
                "code": "INST_UNSUPPORTED_KIND",
                "severity": "ERROR",
                "message": (
                    f"Workload kind '{kind}' is not a supported rolling pod template controller "
                    "(Deployment, StatefulSet, DaemonSet). For CronJobs, place "
                    "instrumentation.opentelemetry.io/inject-<lang> under "
                    "spec.jobTemplate.spec.template.metadata.annotations and call "
                    "TracerProvider.force_flush() + shutdown() before batch process exit."
                ),
            }
        )
        return findings

    spec = doc.get("spec") or {}
    template = spec.get("template") or {}
    meta = template.get("metadata") or {}
    annotations = meta.get("annotations") or {}
    pod_spec = template.get("spec") or {}
    containers = pod_spec.get("containers") or []

    if not containers:
        findings.append(
            {
                "code": "INST_NO_CONTAINERS",
                "severity": "ERROR",
                "message": "Pod template spec defines no containers.",
            }
        )
        return findings

    if len(containers) > 1:
        container_names_Key = f"instrumentation.opentelemetry.io/{language}-container-names"
        generic_key = "instrumentation.opentelemetry.io/container-names"
        if container_names_Key not in annotations and generic_key not in annotations:
            findings.append(
                {
                    "code": "INST_MULTI_CONTAINER_AMBIGUOUS",
                    "severity": "WARNING",
                    "message": (
                        f"Multi-container pod ({len(containers)} containers) lacks "
                        f"'{container_names_Key}' annotation; webhook may inject into wrong container."
                    ),
                }
            )

    if language == "go":
        go_target = annotations.get("instrumentation.opentelemetry.io/otel-go-auto-target-exe", "")
        if not go_target:
            findings.append(
                {
                    "code": "INST_GO_MISSING_TARGET_EXE",
                    "severity": "ERROR",
                    "message": (
                        "Go auto-instrumentation requires "
                        "'instrumentation.opentelemetry.io/otel-go-auto-target-exe' annotation."
                    ),
                }
            )

    for c in containers:
        cname = c.get("name", "default")
        sec = c.get("securityContext") or {}
        if sec.get("readOnlyRootFilesystem") is True:
            volume_mounts = c.get("volumeMounts") or []
            has_tmp = any(vm.get("mountPath") == "/tmp" for vm in volume_mounts)
            if not has_tmp:
                findings.append(
                    {
                        "code": "INST_READONLY_ROOTFS_NO_TMP",
                        "severity": "WARNING",
                        "message": (
                            f"Container '{cname}' sets readOnlyRootFilesystem=true without a writable "
                            "emptyDir volumeMount at /tmp; JVM javaagent.jar dynamic attach / tempfile "
                            "extraction and runtime auto-instrumentation agents fail at startup without /tmp."
                        ),
                    }
                )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint a Kubernetes workload manifest for OpenTelemetry auto-instrumentation."
    )
    parser.add_argument("--file", required=True, help="Path to workload YAML file.")
    parser.add_argument(
        "--language",
        required=True,
        choices=SUPPORTED_LANGUAGES,
        help="Target auto-instrumentation language.",
    )
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"valid": False, "error": f"File not found: {path}"}), file=sys.stderr)
        return 1

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"valid": False, "error": f"Invalid YAML: {exc}"}), file=sys.stderr)
        return 1

    if not isinstance(raw, dict):
        print(
            json.dumps({"valid": False, "error": "YAML root must be a mapping"}),
            file=sys.stderr,
        )
        return 1

    findings = lint_workload(raw, args.language)
    errors = [f for f in findings if f["severity"] == "ERROR"]
    result = {
        "valid": len(errors) == 0,
        "language": args.language,
        "error_count": len(errors),
        "warning_count": len(findings) - len(errors),
        "findings": findings,
    }
    print(json.dumps(result, indent=2))
    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
