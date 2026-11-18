#!/usr/bin/env python3
"""Deterministic local validator for Helm chart values files or JSON strings.

Usage:
    python3 validate_values.py <path-to-values.yaml-or-json> [--schema <path-to-schema.json>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|api[_-]?key|private[_-]?key|access[_-]?token|auth[_-]?token)",
    re.IGNORECASE,
)
SAFE_SECRET_REF_PATTERN = re.compile(
    r"(existingsecret|secretname|secretkey|secretref|key$|path$)",
    re.IGNORECASE,
)
CPU_QUANTITY_PATTERN = re.compile(r"^(\d+m|\d+(\.\d+)?)$")
MEMORY_QUANTITY_PATTERN = re.compile(r"^\d+(\.\d+)?(Ei|Pi|Ti|Gi|Mi|Ki|E|P|T|G|M|K|B)?$")


def _walk_values(
    obj: Any,
    path: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            current = f"{path}.{k}" if path else str(k)
            key_lower = str(k).lower()

            # Replica bounds check
            if key_lower in ("replicas", "replicacount", "minreplicas", "maxreplicas"):
                if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                    errors.append(f"{current}: invalid replica value {v!r} (must be non-negative integer)")
                elif v > 100:
                    warnings.append(
                        f"{current}: high replica count ({v}); keep within 1..100 or use HorizontalPodAutoscaler (HPA) and verify cluster capacity"
                    )

            # Service port integer bounds check (Kubernetes ServicePort.port / nodePort must be integer 1..65535)
            if key_lower in ("port", "nodeport") and (
                path.lower() == "service" or path.lower().endswith(".service") or ".service." in f".{path.lower()}."
            ):
                if isinstance(v, bool) or not isinstance(v, int) or not (1 <= v <= 65535):
                    errors.append(f"{current}: invalid service port {v!r} (must be an integer between 1 and 65535)")

            # CPU & memory quantity syntax check inside resources.requests / resources.limits
            if key_lower == "cpu" and (".requests." in f".{current}." or ".limits." in f".{current}."):
                if not isinstance(v, (int, float)) and (not isinstance(v, str) or not CPU_QUANTITY_PATTERN.match(v.strip())):
                    errors.append(f"{current}: invalid Kubernetes CPU quantity {v!r}")
            if key_lower == "memory" and (".requests." in f".{current}." or ".limits." in f".{current}."):
                if not isinstance(v, (int, float)) and (not isinstance(v, str) or not MEMORY_QUANTITY_PATTERN.match(v.strip())):
                    errors.append(f"{current}: invalid Kubernetes memory quantity {v!r}")

            # Floating image tag check
            if key_lower in ("tag", "imagetag") and isinstance(v, str):
                if v.strip().lower() in ("latest", "main", "master", "dev", "head"):
                    warnings.append(f"{current}: avoid mutable image tag {v!r}; pin an immutable version")

            # Plaintext secret check
            if (
                SENSITIVE_KEY_PATTERN.search(str(k))
                and not SAFE_SECRET_REF_PATTERN.search(str(k))
                and isinstance(v, str)
                and v.strip()
                and not v.strip().startswith("$")
            ):
                warnings.append(
                    f"{current}: appears to contain a hardcoded secret value; prefer existingSecret reference"
                )

            _walk_values(v, current, errors, warnings)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _walk_values(item, f"{path}[{idx}]", errors, warnings)


def validate_values_data(
    values: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(values, dict):
        return {
            "valid": False,
            "errors": ["Root values payload must be a YAML/JSON mapping (dict)"],
            "warnings": [],
        }

    if not values:
        warnings.append("Empty values object; chart defaults will be used")

    _walk_values(values, "", errors, warnings)

    if schema and isinstance(schema, dict):
        for req in schema.get("required", []):
            if req not in values:
                errors.append(f"Missing required top-level field from schema: {req}")
        props = schema.get("properties", {})
        type_map = {
            "object": dict,
            "array": list,
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
        }
        for prop_name, prop_spec in props.items():
            if prop_name in values and isinstance(prop_spec, dict):
                expected_type_name = str(prop_spec.get("type") or "")
                expected_py = type_map.get(expected_type_name)
                if expected_py and not isinstance(values[prop_name], expected_py):
                    errors.append(
                        f"Field '{prop_name}' expected type '{expected_type_name}', got {type(values[prop_name]).__name__}"
                    )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Helm chart values locally.")
    parser.add_argument("values_input", help="Path to YAML/JSON values file or inline JSON string")
    parser.add_argument("--schema", help="Optional path to JSON schema file", default=None)
    args = parser.parse_args()

    path = Path(args.values_input)
    try:
        if args.values_input == "-":
            raw = sys.stdin.read()
        elif path.exists():
            raw = path.read_text(encoding="utf-8")
        else:
            raw = args.values_input
        parsed = yaml.safe_load(raw)
        if parsed is None:
            parsed = {}
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [f"Failed to parse values: {exc}"], "warnings": []}))
        return 1

    result = validate_values_data(parsed, None)
    if args.schema:
        try:
            schema_data = json.loads(Path(args.schema).read_text(encoding="utf-8"))
        except Exception as exc:
            print(json.dumps({"valid": False, "errors": [f"Failed to load schema: {exc}"], "warnings": []}))
            return 1
        result = validate_values_data(parsed, schema_data)

    result["error_count"] = len(result["errors"])
    result["warning_count"] = len(result["warnings"])
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
