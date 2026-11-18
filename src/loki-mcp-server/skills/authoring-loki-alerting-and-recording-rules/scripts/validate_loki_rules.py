#!/usr/bin/env python3
"""Validate Grafana Loki Ruler rule group YAML or Loki Operator AlertingRule/RecordingRule CRDs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

import yaml

RECORD_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_]*:[a-zA-Z0-9_:]+$")
HIGH_CARD_BY_RE = re.compile(
    r"\bby\s*\([^)]*\b(trace_id|span_id|request_id|user_id|session_id|order_id|client_ip|pod_ip|ip|uuid|container_id)\b",
    re.IGNORECASE,
)


def _validate_rule_group_dict(group: dict[str, Any], errors: list[str], warnings: list[str]) -> int:
    name = group.get("name")
    if not name or not isinstance(name, str):
        errors.append("Rule group is missing required string field 'name'.")
    rules = group.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append(f"Rule group '{name or '<unnamed>'}' must contain a non-empty 'rules' list.")
        return 0

    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"Rule #{idx + 1} in group '{name}' is not a mapping.")
            continue
        is_alert = "alert" in rule
        is_record = "record" in rule
        if is_alert == is_record:
            errors.append(f"Rule #{idx + 1} in group '{name}' must define exactly one of 'alert' or 'record'.")
            continue

        expr = str(rule.get("expr") or "").strip()
        if not expr:
            errors.append(f"Rule #{idx + 1} in group '{name}' has an empty 'expr'.")
        else:
            if "{" not in expr or "}" not in expr:
                errors.append(f"Rule #{idx + 1} in group '{name}' ('expr') is missing a LogQL '{{...}}' stream selector.")
            if HIGH_CARD_BY_RE.search(expr):
                errors.append(
                    f"Rule #{idx + 1} in group '{name}' aggregates by a high-cardinality label in 'by (...)', risking metric explosion."
                )
            if re.search(r"\bclamp_(min|max)\s*\(", expr):
                errors.append(
                    f"Rule #{idx + 1} in group '{name}' uses PromQL-only 'clamp_min/clamp_max', which Loki LogQL rejects with HTTP 400; filter the denominator with '(sum by (...) (rate(...[5m])) > 0)' instead."
                )
            if "unwrap" in expr and "__error__" not in expr:
                warnings.append(
                    f"Rule #{idx + 1} in group '{name}' uses '| unwrap' without '| __error__=\"\"'."
                )

        if is_alert:
            alert_name = str(rule.get("alert") or "").strip()
            if not alert_name:
                errors.append(f"Alert rule #{idx + 1} in group '{name}' has an empty 'alert' name.")
            if not rule.get("for"):
                warnings.append(
                    f"Alert '{alert_name}' in group '{name}' omits 'for:' duration; add e.g. 'for: 5m' to prevent flapping."
                )
            annotations = rule.get("annotations") or {}
            if not isinstance(annotations, dict) or "summary" not in annotations:
                warnings.append(f"Alert '{alert_name}' in group '{name}' should include an 'annotations.summary'.")
        else:
            record_name = str(rule.get("record") or "").strip()
            if not RECORD_NAME_RE.match(record_name):
                warnings.append(
                    f"Recording rule '{record_name}' should follow the 'level:metric:operations' naming convention."
                )

    return len(rules)


def validate_rules_yaml(raw_yaml: str) -> dict[str, Any]:
    """Validate a Loki Ruler group YAML or Loki Operator AlertingRule/RecordingRule CRD."""
    errors: list[str] = []
    warnings: list[str] = []
    doc_kind = "RulerRuleGroup"
    total_rules = 0

    try:
        doc = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        return {
            "valid": False,
            "kind": "InvalidYAML",
            "total_rules": 0,
            "errors": [f"YAML parse error: {exc}"],
            "warnings": [],
        }

    if not isinstance(doc, dict):
        return {
            "valid": False,
            "kind": "InvalidDocument",
            "total_rules": 0,
            "errors": ["Root YAML document must be a mapping."],
            "warnings": [],
        }

    # Check if Kubernetes CRD (AlertingRule / RecordingRule)
    if "apiVersion" in doc and "kind" in doc:
        doc_kind = str(doc.get("kind"))
        if doc_kind not in ("AlertingRule", "RecordingRule"):
            errors.append(f"Unsupported CRD kind '{doc_kind}'. Expected AlertingRule or RecordingRule.")
        spec = doc.get("spec") or {}
        groups = spec.get("groups") if isinstance(spec, dict) else None
        if not isinstance(groups, list) or not groups:
            errors.append(f"{doc_kind} CRD must contain a non-empty 'spec.groups' list.")
        else:
            for g in groups:
                if isinstance(g, dict):
                    total_rules += _validate_rule_group_dict(g, errors, warnings)
    elif "groups" in doc and isinstance(doc["groups"], list):
        doc_kind = "RulerRuleGroupList"
        for g in doc["groups"]:
            if isinstance(g, dict):
                total_rules += _validate_rule_group_dict(g, errors, warnings)
    else:
        total_rules = _validate_rule_group_dict(doc, errors, warnings)

    return {
        "valid": len(errors) == 0,
        "kind": doc_kind,
        "total_rules": total_rules,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Loki Ruler YAML or AlertingRule/RecordingRule CRDs.")
    parser.add_argument("--file", help="Path to YAML file")
    parser.add_argument("--yaml", help="Inline YAML string")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    raw_yaml = args.yaml or ""
    if args.file and os.path.exists(args.file):
        with open(args.file, encoding="utf-8") as f:
            raw_yaml = f.read()

    result = validate_rules_yaml(raw_yaml)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "VALID" if result["valid"] else "INVALID"
        print(f"[{status}] Kind={result['kind']} Rules={result['total_rules']}")
        for e in result["errors"]:
            print(f"  ERROR: {e}")
        for w in result["warnings"]:
            print(f"  WARN:  {w}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
