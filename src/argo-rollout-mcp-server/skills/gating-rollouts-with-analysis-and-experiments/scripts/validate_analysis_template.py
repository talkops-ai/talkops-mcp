#!/usr/bin/env python3
"""Offline validator for AnalysisTemplate and ClusterAnalysisTemplate YAML manifests."""

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


def validate_template(doc: dict) -> dict:
    if not isinstance(doc, dict) or doc.get("kind") not in ("AnalysisTemplate", "ClusterAnalysisTemplate"):
        raise ValueError(
            f"Input must be AnalysisTemplate or ClusterAnalysisTemplate, got: "
            f"{doc.get('kind') if isinstance(doc, dict) else type(doc).__name__}"
        )

    issues = []
    warnings = []
    spec = doc.get("spec") or {}
    metrics = spec.get("metrics") or []
    if not metrics:
        issues.append("spec.metrics is empty — at least one metric is required")

    for m in metrics:
        name = m.get("name", "unnamed")
        if not m.get("provider"):
            issues.append(f"Metric '{name}' is missing 'provider'")
        if not m.get("successCondition") and not m.get("failureCondition"):
            issues.append(f"Metric '{name}' must define 'successCondition' or 'failureCondition'")
        if m.get("interval") and not m.get("count"):
            warnings.append(
                f"Metric '{name}' defines 'interval' without finite 'count' — will run indefinitely and block blue-green prePromotionAnalysis"
            )

    valid = len(issues) == 0
    return {
        "valid": valid,
        "kind": doc.get("kind"),
        "name": (doc.get("metadata") or {}).get("name", "unknown"),
        "metrics_count": len(metrics),
        "issues": issues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an AnalysisTemplate or ClusterAnalysisTemplate YAML.")
    parser.add_argument("--input", "-i", type=str, help="Path to AnalysisTemplate YAML file (defaults to stdin)")
    args = parser.parse_args()

    try:
        raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        doc = yaml.safe_load(raw)
        report = validate_template(doc)
        print(json.dumps(report, indent=2))
        return 0 if report["valid"] else 1
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
