#!/usr/bin/env python3
"""Offline CLI to preview exporter Kubernetes manifests and audit DSN secret hygiene."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# Allow importing from project root or local talkops-mcp/src when invoked standalone
PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CANDIDATE_PATHS = [PROJECT_ROOT]
if os.environ.get("TALKOPS_MCP_SRC_DIR"):
    _CANDIDATE_PATHS.append(Path(os.environ["TALKOPS_MCP_SRC_DIR"]) / "prometheus-mcp-server")
for _anc in Path(__file__).resolve().parents:
    _sib = _anc / "talkops-mcp" / "src" / "prometheus-mcp-server"
    if _sib.is_dir():
        _CANDIDATE_PATHS.append(_sib)
        break
for _p in _CANDIDATE_PATHS:
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from prometheus_mcp_server.config import SUPPORTED_EXPORTERS
from prometheus_mcp_server.utils.exporter_catalog import (
    build_exporter_manifests,
    build_servicemonitor_manifest,
)
from prometheus_mcp_server.utils.redaction import is_secret_key, redact_sensitive_data


def parse_env_pairs(pairs: List[str]) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Invalid --env entry '{item}' (expected KEY=VALUE).")
        k, v = item.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render and secret-audit Kubernetes manifests for a Prometheus exporter."
    )
    parser.add_argument(
        "--exporter-type",
        required=True,
        help="Exporter type (e.g. redis_exporter, postgres_exporter, node_exporter)",
    )
    parser.add_argument("--namespace", default="monitoring", help="Kubernetes namespace")
    parser.add_argument("--name", default=None, help="Optional release name override")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Key=Value config flag (can be passed multiple times)",
    )
    args = parser.parse_args()

    if args.exporter_type not in SUPPORTED_EXPORTERS:
        print(
            json.dumps(
                {
                    "error": f"Unknown exporter_type '{args.exporter_type}'",
                    "supported": sorted(SUPPORTED_EXPORTERS.keys()),
                }
            ),
            file=sys.stderr,
        )
        return 1

    try:
        env_map = parse_env_pairs(args.env)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    warnings: List[str] = []
    for k, v in env_map.items():
        if is_secret_key(k) or re.search(r"://[^/@\s]+:[^/@\s]+@", v):
            warnings.append(
                f"Config key '{k}' contains credentials; prefer referencing a Kubernetes Secret via valueFrom.secretKeyRef in production."
            )

    rel_name = (args.name or args.exporter_type).replace("_", "-")
    manifests = build_exporter_manifests(
        exporter_type=args.exporter_type,
        namespace=args.namespace,
        service_name=rel_name,
        config={"env": env_map},
    )
    manifests.append(
        build_servicemonitor_manifest(
            name=rel_name,
            namespace=args.namespace,
            service_name=rel_name,
        )
    )

    output: Dict[str, Any] = {
        "exporter_type": args.exporter_type,
        "name": rel_name,
        "namespace": args.namespace,
        "resource_count": len(manifests),
        "security_warnings": warnings,
        "manifests": redact_sensitive_data(manifests),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
