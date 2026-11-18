#!/usr/bin/env python3
"""Offline validator for Prometheus Operator scrape CRDs and file_sd specs."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List


def validate_scrape_spec(kind: str, name: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    if not name or "_" in name:
        errors.append(
            f"Resource name '{name}' must be a valid DNS-1123 subdomain (use hyphens, not underscores)."
        )

    if kind == "ServiceMonitor":
        if "selector" not in spec:
            errors.append("ServiceMonitor spec requires 'selector' (e.g. {'matchLabels': {...}}).")
        endpoints = spec.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            errors.append("ServiceMonitor spec requires a non-empty 'endpoints' list.")
        else:
            for idx, ep in enumerate(endpoints):
                port = ep.get("port")
                if isinstance(port, int) or (isinstance(port, str) and port.isdigit()):
                    warnings.append(
                        f"endpoints[{idx}].port='{port}' is numeric; ServiceMonitor 'port' should be a named Service port string."
                    )
    elif kind == "PodMonitor":
        if "selector" not in spec:
            errors.append("PodMonitor spec requires 'selector'.")
        if not spec.get("podMetricsEndpoints"):
            errors.append("PodMonitor spec requires a non-empty 'podMetricsEndpoints' list.")
    elif kind == "Probe":
        if not spec.get("prober", {}).get("url"):
            errors.append("Probe spec requires 'prober.url' (e.g. 'blackbox-exporter:9115').")
        if not spec.get("targets"):
            errors.append("Probe spec requires 'targets' configuration.")
    elif kind == "ScrapeConfig":
        if not spec.get("staticConfigs") and not spec.get("httpSDConfigs"):
            errors.append("ScrapeConfig spec requires 'staticConfigs' or 'httpSDConfigs'.")
    elif kind == "file_sd":
        if not spec.get("file_path"):
            errors.append("file_sd spec requires 'file_path'.")
        if not isinstance(spec.get("targets"), list) or not spec.get("targets"):
            errors.append("file_sd spec requires a non-empty 'targets' list.")
    else:
        errors.append(f"Unsupported kind '{kind}'.")

    return {
        "valid": len(errors) == 0,
        "kind": kind,
        "name": name,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Prometheus scrape CRD or file_sd spec offline."
    )
    parser.add_argument(
        "--kind",
        choices=["ServiceMonitor", "PodMonitor", "Probe", "ScrapeConfig", "file_sd"],
        required=True,
    )
    parser.add_argument("--name", required=True, help="Resource name")
    parser.add_argument("--spec-json", required=True, help="JSON string of the spec dictionary")
    args = parser.parse_args()

    try:
        spec = json.loads(args.spec_json)
        if not isinstance(spec, dict):
            raise ValueError("spec-json must decode to a JSON object.")
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [f"Invalid JSON: {exc}"]}), file=sys.stderr)
        return 1

    res = validate_scrape_spec(args.kind, args.name, spec)
    print(json.dumps(res, indent=2))
    return 0 if res["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
