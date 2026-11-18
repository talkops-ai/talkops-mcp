#!/usr/bin/env python3
"""Audit Grafana Loki label cardinality and generate structured_metadata migration configs."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any

ALWAYS_HIGH_CARD_LABELS = {
    "trace_id",
    "span_id",
    "request_id",
    "user_id",
    "session_id",
    "order_id",
    "pod_ip",
    "client_ip",
    "ip",
    "uuid",
    "container_id",
    "pod",
    "k8s_pod_name",
    "k8s.pod.name",
}


def audit_cardinality(card_map: dict[str, int], threshold: int = 500) -> dict[str, Any]:
    """Evaluate label cardinalities and produce remediation recommendations."""
    keep_indexed: dict[str, int] = {}
    move_to_structured_metadata: dict[str, int] = {}
    findings: list[dict[str, Any]] = []

    for label, count in sorted(card_map.items(), key=lambda x: x[1], reverse=True):
        c = int(count)
        is_dynamic_name = label.lower() in ALWAYS_HIGH_CARD_LABELS
        if c >= threshold or is_dynamic_name:
            move_to_structured_metadata[label] = c
            reason = (
                f"Cardinality {c} >= threshold {threshold}"
                if c >= threshold
                else f"Label '{label}' is an ephemeral/high-churn identifier"
            )
            findings.append(
                {
                    "label": label,
                    "cardinality": c,
                    "action": "MOVE_TO_STRUCTURED_METADATA",
                    "reason": reason,
                }
            )
        else:
            keep_indexed[label] = c
            findings.append(
                {
                    "label": label,
                    "cardinality": c,
                    "action": "KEEP_INDEXED",
                    "reason": f"Low cardinality ({c} < {threshold})",
                }
            )

    current_worst_case = math.prod(max(v, 1) for v in card_map.values()) if card_map else 0
    optimized_worst_case = math.prod(max(v, 1) for v in keep_indexed.values()) if keep_indexed else 1

    demoted_keys = list(move_to_structured_metadata.keys())
    alloy_values = ",\n      ".join(f'{k} = "{k}"' for k in demoted_keys)
    drop_list = json.dumps(demoted_keys)

    alloy_snippet = (
        f'loki.process "demote_high_cardinality" {{\n'
        f"  stage.structured_metadata {{\n"
        f"    values = {{\n"
        f"      {alloy_values}\n"
        f"    }}\n"
        f"  }}\n"
        f"  stage.label_drop {{\n"
        f"    values = {drop_list}\n"
        f"  }}\n"
        f"  forward_to = [loki.write.default.receiver]\n"
        f"}}"
        if demoted_keys
        else "# All labels are within safe cardinality bounds."
    )

    return {
        "threshold": threshold,
        "total_labels": len(card_map),
        "high_cardinality_count": len(move_to_structured_metadata),
        "current_theoretical_max_streams": current_worst_case,
        "optimized_theoretical_max_streams": optimized_worst_case,
        "keep_indexed": keep_indexed,
        "move_to_structured_metadata": move_to_structured_metadata,
        "findings": findings,
        "alloy_remediation_snippet": alloy_snippet,
    }


def _load_cardinality_map(raw_arg: str) -> dict[str, int]:
    text = raw_arg
    if os.path.exists(raw_arg):
        with open(raw_arg, encoding="utf-8") as f:
            text = f.read()
    data = json.loads(text)
    if isinstance(data, dict):
        if "detected_labels" in data and isinstance(data["detected_labels"], list):
            return {
                str(item.get("label") or item.get("name")): int(item.get("cardinality", 0))
                for item in data["detected_labels"]
                if isinstance(item, dict)
            }
        return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float, str))}
    if isinstance(data, list):
        return {
            str(item.get("label") or item.get("name")): int(item.get("cardinality", 0))
            for item in data
            if isinstance(item, dict)
        }
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Loki label cardinalities for FinOps optimization.")
    parser.add_argument("--cardinality-json", required=True, help="JSON string or file mapping label -> cardinality")
    parser.add_argument("--threshold", type=int, default=500, help="Max safe cardinality for indexed labels")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    card_map = _load_cardinality_map(args.cardinality_json)
    result = audit_cardinality(card_map, threshold=args.threshold)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"Labels audited: {result['total_labels']} | High-cardinality offenders: {result['high_cardinality_count']}"
        )
        print(
            f"Worst-case streams: {result['current_theoretical_max_streams']} -> {result['optimized_theoretical_max_streams']}"
        )
        for f in result["findings"]:
            print(f"  [{f['action']}] {f['label']}={f['cardinality']} ({f['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
