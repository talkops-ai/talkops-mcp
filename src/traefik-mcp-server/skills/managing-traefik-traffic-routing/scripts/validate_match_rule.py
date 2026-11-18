#!/usr/bin/env python3
"""Offline Traefik v3 match rule validator and priority calculator."""

import argparse
import json
import re
import sys


V2_PATTERNS = [
    (re.compile(r"\bHeaders\s*\("), "Use 'Header(`key`, `val`)' instead of v2 'Headers(...)'"),
    (re.compile(r"\bHeadersRegexp\s*\("), "Use 'HeaderRegexp(`key`, `regex`)' instead of v2 'HeadersRegexp(...)'"),
    (re.compile(r"\bHostHeader\s*\("), "Use 'Host(`domain`)' instead of v2 'HostHeader(...)'"),
    (re.compile(r"\bPathStrip\w*\s*\("), "Use a StripPrefix Middleware instead of v2 PathStrip rule matcher"),
    (re.compile(r"\{[a-zA-Z0-9_]+:[^}]+\}"), "Curly-brace regex syntax '{name:pattern}' is v2; use Go RE2 in HostRegexp/PathRegexp"),
    (re.compile(r"\b(?:Host|Path|PathPrefix)\s*\(\s*`[^`]+`\s*,\s*`"), "Traefik v3 matchers accept a single argument; join multiple with '||'"),
    (re.compile(r"\bQuery\s*\(\s*`[^`]*=[^`]*`\s*\)"), "Traefik v2 single-argument Query(`key=value`) changed in v3 to Query(`key`, `value`)"),
]


def validate_rule(rule: str, explicit_priority: int | None = None) -> dict:
    rule_s = rule.strip()
    issues = []
    if not rule_s:
        issues.append("Match rule cannot be empty")
    if rule_s.count("(") != rule_s.count(")"):
        issues.append("Unbalanced parentheses in match rule")
    if rule_s.count("`") % 2 != 0:
        issues.append("Unbalanced backticks in match rule")
    for pat, msg in V2_PATTERNS:
        if pat.search(rule_s):
            issues.append(msg)

    priority = explicit_priority if explicit_priority is not None else len(rule_s)
    return {
        "rule": rule_s,
        "valid_v3": len(issues) == 0,
        "default_priority": len(rule_s),
        "effective_priority": priority,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Traefik v3 match rule string and compute its priority."
    )
    parser.add_argument(
        "--rule",
        default="Host(`api.example.com`) && PathPrefix(`/v1`)",
        help="Traefik match rule expression",
    )
    parser.add_argument("--priority", type=int, default=None, help="Optional explicit priority")
    args = parser.parse_args()
    result = validate_rule(args.rule, args.priority)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
