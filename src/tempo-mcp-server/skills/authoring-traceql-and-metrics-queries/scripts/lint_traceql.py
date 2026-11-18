#!/usr/bin/env python3
"""Offline CLI linter for TraceQL 2.x/3.x search and metrics queries."""

import argparse
import json
import re
import sys
from typing import Any, Dict, List

DEFAULT_QUERY = (
    '{ resource.service.name = "checkout" && status = error } '
    "| select(resource.service.name, span.http.route) with(most_recent=true)"
)

UNSCOPED_DOT_RE = re.compile(r"(?:^|[\{\(&\|!=\s])\.([a-zA-Z_][a-zA-Z0-9_.]*)")
QUOTED_ENUM_RE = re.compile(
    r'\b(status|kind)\s*(?:=|!=)\s*"([^"\n]*)"?'
)


def lint_query(query: str) -> Dict[str, Any]:
    q = query.strip()
    issues: List[str] = []
    warnings: List[str] = []

    open_braces = q.count("{")
    close_braces = q.count("}")
    if open_braces == 0 or close_braces == 0:
        issues.append("Query must contain at least one span selector block '{ ... }'.")
    if open_braces != close_braces:
        issues.append(f"Unbalanced curly braces: '{open_braces}' open vs '{close_braces}' close.")

    open_parens = q.count("(")
    close_parens = q.count(")")
    if open_parens != close_parens:
        issues.append(f"Unbalanced parentheses: '{open_parens}' open vs '{close_parens}' close.")

    if q.count('"') % 2 != 0:
        issues.append("Unbalanced double quotes in string literal.")

    for enum_match in QUOTED_ENUM_RE.finditer(q):
        field_name, enum_val = enum_match.group(1), enum_match.group(2)
        issues.append(
            f"Intrinsic field '{field_name}' takes an unquoted enum identifier "
            f"(e.g. '{field_name} = {enum_val.lower() or 'error'}'), not a quoted string literal."
        )

    if "link:traceId" in q or "link:spanId" in q:
        issues.append(
            "TraceQL span-link intrinsics require uppercase 'ID': use 'link:traceID' / 'link:spanID' instead of 'link:traceId' / 'link:spanId'."
        )

    for match in UNSCOPED_DOT_RE.finditer(q):
        attr = match.group(1)
        warnings.append(
            f"Unscoped attribute '.{attr}' scans both resource and span scopes; prefer 'resource.{attr}' or 'span.{attr}'."
        )

    if "=~" in q and "resource.service.name" not in q:
        warnings.append(
            "Regex filter '=~' without a 'resource.service.name' equality filter may cause high scan latency."
        )

    return {
        "query": q,
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint a TraceQL search or metrics query.")
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="TraceQL query string to validate.",
    )
    args = parser.parse_args()
    result = lint_query(args.query)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
