#!/usr/bin/env python3
"""Offline generator for scaling a legacy Deployment YAML to replicas: 0 for GitOps."""

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


def scale_down_deployment(dep: dict) -> str:
    if not isinstance(dep, dict) or dep.get("kind") != "Deployment":
        raise ValueError(f"Input must be kind: Deployment, got: {dep.get('kind') if isinstance(dep, dict) else type(dep).__name__}")
    dep.setdefault("spec", {})["replicas"] = 0
    return yaml.dump(dep, default_flow_style=False, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Deployment YAML with spec.replicas=0 for GitOps scale-down.")
    parser.add_argument("--input", "-i", type=str, help="Path to Deployment YAML file (defaults to stdin)")
    args = parser.parse_args()

    try:
        raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        doc = yaml.safe_load(raw)
        print(scale_down_deployment(doc), end="")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
