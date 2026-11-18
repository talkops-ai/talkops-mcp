#!/usr/bin/env python3
"""Offline Rollout-to-Deployment reverse converter."""

import argparse
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


def convert_rollout_to_deployment(
    rollout: dict,
    deployment_strategy: str = "RollingUpdate",
    max_surge: str = "25%",
    max_unavailable: str = "25%",
) -> str:
    if not isinstance(rollout, dict) or rollout.get("kind") != "Rollout":
        raise ValueError(f"Input must be kind: Rollout, got: {rollout.get('kind') if isinstance(rollout, dict) else type(rollout).__name__}")

    meta = rollout.get("metadata") or {}
    spec = rollout.get("spec") or {}
    name = meta.get("name")
    if not name:
        raise ValueError("Rollout metadata.name is required")

    labels = dict(meta.get("labels") or {})
    labels.pop("managed-by", None)
    annotations = {
        k: v
        for k, v in (meta.get("annotations") or {}).items()
        if "argoproj" not in k and "argo-rollouts" not in k
    }

    dep_meta: dict = {
        "name": name,
        "namespace": meta.get("namespace", "default"),
    }
    if labels:
        dep_meta["labels"] = labels
    if annotations:
        dep_meta["annotations"] = annotations

    dep_spec: dict = {}
    if "workloadRef" in spec and "template" not in spec:
        ref_name = (spec.get("workloadRef") or {}).get("name") or name
        raise ValueError(
            f"Rollout '{name}' uses spec.workloadRef referencing Deployment '{ref_name}' without an inline "
            f"spec.template and cannot be converted standalone from the Rollout file alone. "
            f"To roll back in GitOps, restore spec.replicas on the referenced Deployment/{ref_name} manifest in Git "
            f"and wait for its pods to become Ready before removing Rollout/{name}."
        )
    if "replicas" in spec:
        dep_spec["replicas"] = spec["replicas"]
    if "selector" in spec:
        dep_spec["selector"] = spec["selector"]
    if "template" in spec:
        dep_spec["template"] = spec["template"]

    if deployment_strategy == "RollingUpdate":
        dep_spec["strategy"] = {
            "type": "RollingUpdate",
            "rollingUpdate": {"maxSurge": max_surge, "maxUnavailable": max_unavailable},
        }
    elif deployment_strategy == "Recreate":
        dep_spec["strategy"] = {"type": "Recreate"}
    else:
        raise ValueError(f"Unsupported deployment_strategy: {deployment_strategy}")

    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": dep_meta,
        "spec": dep_spec,
    }
    return yaml.dump(deployment, default_flow_style=False, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an Argo Rollout YAML back to a Kubernetes Deployment YAML.")
    parser.add_argument("--input", "-i", type=str, help="Path to Rollout YAML file (defaults to stdin)")
    parser.add_argument("--strategy", choices=["RollingUpdate", "Recreate"], default="RollingUpdate")
    args = parser.parse_args()

    try:
        raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        doc = yaml.safe_load(raw)
        print(convert_rollout_to_deployment(doc, deployment_strategy=args.strategy), end="")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
