#!/usr/bin/env python3
"""Deterministic local security scanner for rendered Kubernetes YAML manifests.

Checks for:
  - Privileged containers & privilege escalation (HIGH)
  - Host namespace sharing (hostNetwork, hostPID, hostIPC) & hostPath volumes (HIGH)
  - Wildcard RBAC rules in Role / ClusterRole (HIGH)
  - Mutable image tags (:latest, :main, :master, untagged) (MEDIUM)
  - Missing resource limits / requests (MEDIUM)
  - Missing runAsNonRoot in securityContext (MEDIUM)

Usage:
    python3 scan_manifest_security.py <path-to-manifests.yaml>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet", "Pod"}
MUTABLE_TAGS = {"latest", "main", "master", "dev", "head"}


def _extract_pod_spec(doc: dict[str, Any]) -> dict[str, Any] | None:
    kind = doc.get("kind")
    if kind == "Pod":
        return doc.get("spec")
    if kind == "CronJob":
        return (
            doc.get("spec", {})
            .get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("spec")
        )
    if kind in WORKLOAD_KINDS:
        return doc.get("spec", {}).get("template", {}).get("spec")
    return None


def scan_manifests_text(manifests: str) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    docs = [d for d in yaml.safe_load_all(manifests) if isinstance(d, dict)]

    for doc in docs:
        kind = str(doc.get("kind") or "Unknown")
        name = str(doc.get("metadata", {}).get("name") or "unnamed")
        res_id = f"{kind}/{name}"

        # RBAC checks
        if kind in ("Role", "ClusterRole"):
            for rule in doc.get("rules") or []:
                if not isinstance(rule, dict):
                    continue
                verbs = rule.get("verbs") or []
                resources = rule.get("resources") or []
                if "*" in verbs or "*" in resources:
                    findings.append({
                        "severity": "high",
                        "resource": res_id,
                        "rule": "no-wildcard-rbac",
                        "message": f"{res_id} grants wildcard RBAC permissions (verbs={verbs}, resources={resources})",
                        "remediation": "Scope Role/ClusterRole rules to explicit verbs and resource types.",
                    })

        pod_spec = _extract_pod_spec(doc)
        if not isinstance(pod_spec, dict):
            continue

        for host_flag in ("hostNetwork", "hostPID", "hostIPC"):
            if pod_spec.get(host_flag) is True:
                findings.append({
                    "severity": "high",
                    "resource": res_id,
                    "rule": f"no-{host_flag.lower()}",
                    "message": f"{res_id} enables {host_flag}=true",
                    "remediation": f"Disable {host_flag} in pod spec unless strictly required.",
                })

        for vol in pod_spec.get("volumes") or []:
            if isinstance(vol, dict) and "hostPath" in vol:
                findings.append({
                    "severity": "high",
                    "resource": res_id,
                    "rule": "no-hostpath-volume",
                    "message": f"{res_id} mounts a hostPath volume ({vol.get('name', 'unnamed')})",
                    "remediation": "Replace hostPath volume with PersistentVolumeClaim or emptyDir.",
                })

        pod_sec = pod_spec.get("securityContext") or {}
        pod_non_root = pod_sec.get("runAsNonRoot") is True

        containers = list(pod_spec.get("containers") or []) + list(pod_spec.get("initContainers") or [])
        for c in containers:
            if not isinstance(c, dict):
                continue
            c_name = str(c.get("name") or "container")
            c_id = f"{res_id}/container/{c_name}"
            c_sec = c.get("securityContext") or {}

            if c_sec.get("privileged") is True:
                findings.append({
                    "severity": "high",
                    "resource": c_id,
                    "rule": "no-privileged-container",
                    "message": f"{c_id} runs with privileged=true",
                    "remediation": "Set containerSecurityContext.privileged=false.",
                })

            if c_sec.get("allowPrivilegeEscalation") is True:
                findings.append({
                    "severity": "high",
                    "resource": c_id,
                    "rule": "no-privilege-escalation",
                    "message": f"{c_id} sets allowPrivilegeEscalation=true",
                    "remediation": "Set containerSecurityContext.allowPrivilegeEscalation=false.",
                })

            if not (pod_non_root or c_sec.get("runAsNonRoot") is True):
                findings.append({
                    "severity": "medium",
                    "resource": c_id,
                    "rule": "require-run-as-non-root",
                    "message": f"{c_id} does not enforce runAsNonRoot=true",
                    "remediation": "Set securityContext.runAsNonRoot=true at pod or container level.",
                })

            image = str(c.get("image") or "")
            if "@sha256:" not in image:
                tag = image.rsplit(":", 1)[1].lower() if ":" in image.rsplit("/", 1)[-1] else "latest"
                if tag in MUTABLE_TAGS:
                    findings.append({
                        "severity": "medium",
                        "resource": c_id,
                        "rule": "pin-image-tag",
                        "message": f"{c_id} uses mutable image tag '{image}'",
                        "remediation": "Pin an immutable version tag or SHA256 digest in values.",
                    })

            resources = c.get("resources") or {}
            limits = resources.get("limits") or {}
            requests = resources.get("requests") or {}
            if not (limits.get("memory") and requests.get("cpu") and requests.get("memory")):
                findings.append({
                    "severity": "medium",
                    "resource": c_id,
                    "rule": "require-resource-limits",
                    "message": f"{c_id} is missing CPU/memory requests or memory limits",
                    "remediation": "Define resources.requests (cpu, memory) and resources.limits (memory).",
                })

    summary = {
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "medium": sum(1 for f in findings if f["severity"] == "medium"),
        "low": sum(1 for f in findings if f["severity"] == "low"),
        "total": len(findings),
    }
    return {
        "passed": summary["high"] == 0,
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan rendered Kubernetes manifests for security issues.")
    parser.add_argument("manifests_file", help="Path to rendered YAML file (or '-' for stdin)")
    args = parser.parse_args()

    try:
        content = sys.stdin.read() if args.manifests_file == "-" else Path(args.manifests_file).read_text(encoding="utf-8")
        report = scan_manifests_text(content)
    except Exception as exc:
        print(json.dumps({"passed": False, "error": str(exc), "findings": []}))
        return 1

    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
