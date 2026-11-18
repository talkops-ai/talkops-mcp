#!/usr/bin/env python3
"""Offline Deployment readiness linter for Argo Rollouts migration.

Reads a Kubernetes Deployment YAML from --input (or stdin) and outputs a JSON
ReadinessReport with score, blocking issues, warnings, and detected_container_port.
Exits 0 when ready=True, 1 when blocking issues exist or input is invalid.
"""

import argparse
import json
import sys
from pathlib import Path
try:
    import yaml
except ModuleNotFoundError:
    import os as _os, shutil as _shutil, subprocess as _sp
    if _shutil.which("uv") and not _os.environ.get("_UV_YAML_BOOTSTRAPPED"):
        raise SystemExit(
            _sp.call(
                ["uv", "run", "--quiet", "--with", "pyyaml", "python3", *sys.argv],
                env={**_os.environ, "_UV_YAML_BOOTSTRAPPED": "1"},
            )
        )
    raise


def extract_container_port(pod_spec: dict) -> int:
    for container in (pod_spec or {}).get("containers", []):
        for p in container.get("ports", []):
            if p.get("containerPort") is not None:
                return int(p["containerPort"])
    return 80


def lint_deployment(dep: dict) -> dict:
    if not isinstance(dep, dict) or dep.get("kind") != "Deployment":
        raise ValueError(f"Input must be a Kubernetes Deployment, got: {dep.get('kind') if isinstance(dep, dict) else type(dep).__name__}")

    meta = dep.get("metadata") or {}
    spec = dep.get("spec") or {}
    app_name = meta.get("name", "unknown")
    namespace = meta.get("namespace", "default")
    issues = []
    warnings = []
    recommendations = []
    score = 100

    if not spec:
        issues.append("Deployment has no spec")
        score -= 50
    if not spec.get("selector"):
        issues.append("Deployment has no selector (required for Rollout)")
        score -= 25

    template = spec.get("template") or {}
    pod_spec = template.get("spec") or {}
    if not pod_spec:
        issues.append("Deployment has no pod template spec")
        score -= 25

    containers = pod_spec.get("containers") or []
    if not containers:
        issues.append("No containers defined in Deployment pod template")
        score -= 25

    replicas = int(spec.get("replicas", 1))
    if replicas < 2:
        warnings.append(f"Only {replicas} replica(s) — consider 2+ for canary traffic splitting")
        score -= 10
    elif replicas < 3:
        warnings.append("2 replicas — consider 3+ for production high availability")
        score -= 5

    for c in containers:
        cname = c.get("name", "unnamed")
        res = c.get("resources") or {}
        limits = res.get("limits") or {}
        requests = res.get("requests") or {}
        if not limits.get("cpu") or not limits.get("memory"):
            warnings.append(f"Container '{cname}' missing resource limits")
            score -= 5
        if not requests.get("cpu") or not requests.get("memory"):
            warnings.append(f"Container '{cname}' missing resource requests")
            score -= 5
        if not c.get("readinessProbe"):
            warnings.append(f"Container '{cname}' missing readinessProbe")
            score -= 5
            recommendations.append("Add readinessProbe so Argo Rollouts can verify canary pod readiness")
        if not c.get("livenessProbe"):
            warnings.append(f"Container '{cname}' missing livenessProbe")
            score -= 3
        lifecycle = c.get("lifecycle") or {}
        if not (isinstance(lifecycle, dict) and lifecycle.get("preStop")):
            warnings.append(f"Container '{cname}' missing lifecycle.preStop hook")
            score -= 2

    term_grace = pod_spec.get("terminationGracePeriodSeconds")
    if term_grace is None or int(term_grace) < 30:
        warnings.append("terminationGracePeriodSeconds not set or < 30")
        score -= 2

    detected_port = extract_container_port(pod_spec)
    ready = len(issues) == 0
    return {
        "ready": ready,
        "score": max(0, score),
        "app_name": app_name,
        "namespace": namespace,
        "replicas": replicas,
        "containers_count": len(containers),
        "detected_container_port": detected_port,
        "issues": issues,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint a Kubernetes Deployment YAML for Argo Rollouts readiness.")
    parser.add_argument("--input", "-i", type=str, help="Path to Deployment YAML file (defaults to stdin)")
    args = parser.parse_args()

    try:
        raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        doc = yaml.safe_load(raw)
        report = lint_deployment(doc)
        print(json.dumps(report, indent=2))
        return 0 if report["ready"] else 1
    except Exception as exc:
        print(json.dumps({"ready": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
