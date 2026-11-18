#!/usr/bin/env python3
"""Deterministic local validator for rendered Kubernetes YAML manifests.

Usage:
    python3 validate_manifests.py <path-to-manifests.yaml>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def validate_manifests_text(manifests: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    resource_types: dict[str, int] = {}
    resource_count = 0

    if not manifests or not manifests.strip():
        return {
            "valid": False,
            "resource_count": 0,
            "resource_types": {},
            "errors": ["Manifests content is empty"],
            "warnings": [],
        }

    try:
        documents = list(yaml.safe_load_all(manifests))
    except yaml.YAMLError as exc:
        return {
            "valid": False,
            "resource_count": 0,
            "resource_types": {},
            "errors": [f"Invalid YAML syntax: {exc}"],
            "warnings": [],
        }

    for idx, doc in enumerate(documents, start=1):
        if doc is None:
            continue
        if not isinstance(doc, dict):
            errors.append(f"Document #{idx}: expected mapping object, got {type(doc).__name__}")
            continue

        resource_count += 1
        kind = str(doc.get("kind") or "Unknown")
        resource_types[kind] = resource_types.get(kind, 0) + 1

        if "apiVersion" not in doc:
            errors.append(f"Document #{idx} ({kind}): missing 'apiVersion'")
        if "kind" not in doc:
            errors.append(f"Document #{idx}: missing 'kind'")
        metadata = doc.get("metadata")
        if not isinstance(metadata, dict) or not metadata.get("name"):
            errors.append(f"Document #{idx} ({kind}): missing 'metadata.name'")

    if resource_count == 0 and not errors:
        errors.append("No Kubernetes resource documents found in YAML")

    return {
        "valid": len(errors) == 0,
        "resource_count": resource_count,
        "resource_types": resource_types,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rendered Kubernetes YAML manifests locally.")
    parser.add_argument("manifests_file", help="Path to rendered YAML file (or '-' for stdin)")
    args = parser.parse_args()

    try:
        if args.manifests_file == "-":
            content = sys.stdin.read()
        else:
            content = Path(args.manifests_file).read_text(encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [f"Cannot read input: {exc}"], "warnings": []}))
        return 1

    result = validate_manifests_text(content)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
