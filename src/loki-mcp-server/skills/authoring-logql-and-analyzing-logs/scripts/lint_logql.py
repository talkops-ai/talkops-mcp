#!/usr/bin/env python3
"""Deterministic static linter for Grafana Loki LogQL queries."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

HIGH_CARDINALITY_LABELS = {
    "trace_id",
    "traceid",
    "span_id",
    "spanid",
    "request_id",
    "requestid",
    "user_id",
    "userid",
    "session_id",
    "pod_ip",
    "client_ip",
    "ip",
    "uuid",
    "order_id",
}

SELECTOR_RE = re.compile(r"\{([^{}]*)\}")
LABEL_MATCHER_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*"([^"]*)"')
PARSER_RE = re.compile(r"\|\s*(json|logfmt|regexp|pattern|unpack)\b")
LINE_FILTER_RE = re.compile(r"(\|=|!=|\|~|!~)\s*\"|(\|=|!=|\|~|!~)\s*`")
UNWRAP_RE = re.compile(r"\|\s*unwrap\b")
ERROR_GUARD_RE = re.compile(r"__error__\s*=\s*\"\"")


def lint_logql(query: str) -> dict[str, Any]:
    """Lint a LogQL query and return structured findings."""
    q = (query or "").strip()
    errors: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []

    if not q:
        errors.append("Query is empty.")
        return {"valid": False, "query": q, "errors": errors, "warnings": warnings, "suggestions": suggestions}

    if re.search(r"\bclamp_(?:min|max)\s*\(", q):
        errors.append(
            "PromQL-only function 'clamp_min'/'clamp_max' is not supported in LogQL grammar (causes HTTP 400 parse error in Loki). "
            "Protect ratio denominators in LogQL using '(sum(...) > 0)' instead."
        )

    if q.count("{") != q.count("}"):
        errors.append("Unbalanced curly braces '{}' in stream selector.")

    selector_match = SELECTOR_RE.search(q)
    if not selector_match:
        errors.append("Missing stream selector '{...}'. Every LogQL query must include a stream selector.")
    else:
        selector_body = selector_match.group(1).strip()
        if not selector_body:
            errors.append("Empty stream selector '{}' is rejected by Loki. Bound at least one indexed label.")
        else:
            matchers = LABEL_MATCHER_RE.findall(selector_body)
            if not matchers:
                errors.append(f"Invalid label matcher syntax inside selector: {{{selector_body}}}")
            else:
                has_positive_non_wildcard = False
                for label, op, val in matchers:
                    if label.lower() in HIGH_CARDINALITY_LABELS:
                        warnings.append(
                            f"High-cardinality field '{label}' used inside stream selector '{{}}'. "
                            f"Move '{label}' to Loki 3.x structured metadata filter ('| {label}=\"{val}\"') or line filter ('|= \"{val}\"')."
                        )
                    if op == "=" and val != "":
                        has_positive_non_wildcard = True
                    elif op == "=~" and val not in (".*", ".+", ""):
                        has_positive_non_wildcard = True
                if not has_positive_non_wildcard:
                    warnings.append(
                        "Stream selector only uses negative or wildcard regex matchers; bind at least one exact label (e.g., service_name or namespace)."
                    )

        # Inspect pipeline after selector
        pipeline = q[selector_match.end() :]
        parser_match = PARSER_RE.search(pipeline)
        line_filter_match = LINE_FILTER_RE.search(pipeline)

        if parser_match:
            if not line_filter_match:
                warnings.append(
                    f"Parser '| {parser_match.group(1)}' used without a preceding line filter ('|=', '|~'). "
                    "Add a literal line filter before parsing to leverage Loki 3.x Bloom filters and reduce CPU cost."
                )
            elif line_filter_match.start() > parser_match.start():
                warnings.append(
                    f"Parser '| {parser_match.group(1)}' appears before line filter. "
                    "Enforce the 4-stage pipeline order: {selector} -> |= line filter -> | parser -> | label filter."
                )

            if parser_match.group(1) == "json" and re.search(r"\|\s*json\s*(\||$|\[|\))", pipeline):
                suggestions.append(
                    "Consider targeted JSON extraction (e.g., '| json status=\"status\", msg=\"msg\"') instead of bare '| json' to skip parsing unused keys."
                )

        if UNWRAP_RE.search(pipeline) and not ERROR_GUARD_RE.search(pipeline):
            warnings.append(
                "Query uses '| unwrap' without '| __error__=\"\"'. Malformed log lines will cause SampleExtractionErr."
            )

    return {
        "valid": len(errors) == 0,
        "query": q,
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggestions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint a Grafana Loki LogQL query for correctness and cost.")
    parser.add_argument("--query", required=True, help="LogQL query string to lint")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    result = lint_logql(args.query)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "VALID" if result["valid"] else "INVALID"
        print(f"[{status}] {result['query']}")
        for err in result["errors"]:
            print(f"  ERROR: {err}")
        for warn in result["warnings"]:
            print(f"  WARN:  {warn}")
        for sug in result["suggestions"]:
            print(f"  TIP:   {sug}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
