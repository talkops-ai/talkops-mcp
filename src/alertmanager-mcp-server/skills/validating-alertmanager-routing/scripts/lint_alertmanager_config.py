#!/usr/bin/env python3
"""Offline static linter for Alertmanager configuration files (`LINT001`–`LINT008`).

Usage:
  python3 lint_alertmanager_config.py --config alertmanager.yml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None

LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
UNSUPPORTED_RE2_RE = re.compile(r"\(\?(?:=|!|<=|<!|>|\()|\\[1-9]")
SINGLE_MATCHER_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*(.*?)\s*$", re.DOTALL
)


def load_config_file(path_str: str) -> dict[str, Any]:
    raw_text = Path(path_str).read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(raw_text)
    else:
        data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a YAML/JSON mapping.")
    return data


def _validate_matcher_expr(expr: str) -> str | None:
    s = expr.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    m = SINGLE_MATCHER_RE.match(s)
    if not m:
        return f"Invalid matcher expression '{expr}'."
    name, op, raw_val = m.group(1), m.group(2), m.group(3).strip()
    if not LABEL_NAME_RE.match(name):
        return f"Invalid label name '{name}' in '{expr}'."
    val = raw_val.strip('"').strip("'")
    if op in ("=~", "!~"):
        if UNSUPPORTED_RE2_RE.search(val):
            return f"Regex '{val}' in '{expr}' uses PCRE constructs unsupported by Go RE2."
        try:
            re.compile(f"^(?:{val})$")
        except re.error as exc:
            return f"Invalid regex '{val}' in '{expr}': {exc}"
    return None


def lint_config(config: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    defined_receivers: set[str] = set()
    for rcv in config.get("receivers") or []:
        if isinstance(rcv, Mapping) and rcv.get("name"):
            defined_receivers.add(str(rcv["name"]))

    defined_intervals: set[str] = set()
    for section in ("time_intervals", "mute_time_intervals"):
        for item in config.get(section) or []:
            if isinstance(item, Mapping) and item.get("name"):
                defined_intervals.add(str(item["name"]))

    referenced_receivers: set[str] = set()
    root_route = config.get("route")
    if not isinstance(root_route, Mapping) or not root_route.get("receiver"):
        findings.append(
            {
                "rule_id": "LINT001",
                "severity": "error",
                "path": "route",
                "message": "Missing root 'route' block or missing root 'route.receiver'.",
            }
        )

    def _walk_route(node: Mapping[str, Any], path: str, is_root: bool) -> None:
        rcv = node.get("receiver")
        if rcv:
            rcv_name = str(rcv)
            referenced_receivers.add(rcv_name)
            if defined_receivers and rcv_name not in defined_receivers:
                findings.append(
                    {
                        "rule_id": "LINT002",
                        "severity": "error",
                        "path": path,
                        "message": f"Route '{path}' references undefined receiver '{rcv_name}'.",
                    }
                )

        if "match" in node or "match_re" in node:
            findings.append(
                {
                    "rule_id": "LINT005",
                    "severity": "warning",
                    "path": path,
                    "message": f"Route '{path}' uses deprecated 'match'/'match_re'; prefer 'matchers'.",
                }
            )

        raw_match_re = node.get("match_re")
        if isinstance(raw_match_re, Mapping):
            for k, v in raw_match_re.items():
                err = _validate_matcher_expr(f'{k}=~"{v}"')
                if err:
                    findings.append(
                        {
                            "rule_id": "LINT007",
                            "severity": "error",
                            "path": path,
                            "message": err,
                        }
                    )

        for expr in node.get("matchers") or []:
            if isinstance(expr, str):
                err = _validate_matcher_expr(expr)
                if err:
                    findings.append(
                        {
                            "rule_id": "LINT007",
                            "severity": "error",
                            "path": path,
                            "message": err,
                        }
                    )

        for int_key in ("mute_time_intervals", "active_time_intervals"):
            for int_name in node.get(int_key) or []:
                if str(int_name) not in defined_intervals:
                    findings.append(
                        {
                            "rule_id": "LINT004",
                            "severity": "error",
                            "path": path,
                            "message": f"Route '{path}' references undefined time interval '{int_name}'.",
                        }
                    )

        children = node.get("routes")
        if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
            unconditional_stop_at: int | None = None
            for idx, child in enumerate(children):
                if not isinstance(child, Mapping):
                    continue
                child_path = f"{path}/{idx}"
                if unconditional_stop_at is not None:
                    findings.append(
                        {
                            "rule_id": "LINT006",
                            "severity": "warning",
                            "path": child_path,
                            "message": (
                                f"Route '{child_path}' is shadowed by unconditional sibling "
                                f"route '{path}/{unconditional_stop_at}' with continue=false."
                            ),
                        }
                    )
                has_matchers = bool(
                    child.get("match")
                    or child.get("match_re")
                    or child.get("matchers")
                )
                if (
                    not has_matchers
                    and not bool(child.get("continue", False))
                    and unconditional_stop_at is None
                ):
                    unconditional_stop_at = idx
                _walk_route(child, child_path, False)

    if isinstance(root_route, Mapping):
        _walk_route(root_route, "root", True)

    for unused in sorted(defined_receivers - referenced_receivers):
        findings.append(
            {
                "rule_id": "LINT003",
                "severity": "warning",
                "path": f"receivers[{unused}]",
                "message": f"Receiver '{unused}' is defined but never referenced in the routing tree.",
            }
        )

    for idx, rule in enumerate(config.get("inhibit_rules") or []):
        if not isinstance(rule, Mapping):
            continue
        rpath = f"inhibit_rules[{idx}]"
        if (
            "source_match" in rule
            or "source_match_re" in rule
            or "target_match" in rule
            or "target_match_re" in rule
        ):
            findings.append(
                {
                    "rule_id": "LINT005",
                    "severity": "warning",
                    "path": rpath,
                    "message": f"{rpath} uses deprecated source_match/target_match; prefer source_matchers/target_matchers.",
                }
            )
        src_m = list(rule.get("source_matchers") or [])
        tgt_m = list(rule.get("target_matchers") or [])
        eq = list(rule.get("equal") or [])
        if src_m and src_m == tgt_m:
            findings.append(
                {
                    "rule_id": "LINT008",
                    "severity": "warning",
                    "path": rpath,
                    "message": f"{rpath} has identical source_matchers and target_matchers.",
                }
            )
        if not eq:
            findings.append(
                {
                    "rule_id": "LINT008",
                    "severity": "warning",
                    "path": rpath,
                    "message": f"{rpath} omits 'equal' scoping labels, which may cause cross-service inhibition.",
                }
            )

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Static linter for Alertmanager configuration YAML/JSON files."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to alertmanager.yml or JSON config file",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = load_config_file(args.config)
        report = lint_config(cfg)
        print(json.dumps(report, indent=2))
        return 0 if report["valid"] else 1
    except Exception as exc:
        print(
            json.dumps({"valid": False, "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
