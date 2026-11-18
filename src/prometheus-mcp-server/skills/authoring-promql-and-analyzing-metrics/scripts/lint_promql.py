#!/usr/bin/env python3
"""Offline deterministic PromQL linter and anti-pattern detector."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List

SAFE_WRAPPERS = {"rate", "irate", "increase", "resets", "changes", "deriv", "idelta"}


def lint_promql(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"valid": False, "errors": ["Query is empty."], "warnings": []}

    errors: List[str] = []
    warnings: List[str] = []

    # Check balanced parentheses, brackets, and braces
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: List[str] = []
    in_quotes = False
    for ch in q:
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes:
            if ch in "([{":
                stack.append(ch)
            elif ch in ")]}":
                if not stack or stack[-1] != pairs[ch]:
                    errors.append(f"Unbalanced delimiter '{ch}' in PromQL expression.")
                    break
                stack.pop()
    if stack:
        errors.append(f"Unclosed delimiter '{stack[-1]}' in PromQL expression.")

    # Check unbounded __name__ regex
    if re.search(
        r'__name__\s*=~\s*(?:"\^?(?:\.\*|\.\+|\.\.\*|\.\+\.\*|\[\^"\]\*|\[\^"\]\+)\$?"|\'\^?(?:\.\*|\.\+|\.\.\*|\.\+\.\*)\$?\')',
        q,
    ):
        errors.append(
            "Unbounded selector '{__name__=~\".+\"}' detected; specify concrete metric names."
        )

    # Check rate(sum(...)) anti-pattern
    if re.search(r"\b(?:rate|irate|increase)\s*\(\s*(?:sum|avg|min|max)\b", q):
        errors.append(
            "Anti-pattern: rate()/increase() wraps sum()/avg(). Always apply rate() inside sum(): sum(rate(metric[5m]))."
        )

    # Check classic histogram_quantile missing 'le' in sum by (...)
    if "histogram_quantile" in q and "_bucket" in q:
        by_match = re.search(r"\b(?:by|without)\s*\(([^)]*)\)", q)
        if by_match:
            labels = [lbl.strip() for lbl in by_match.group(1).split(",")]
            if "by" in by_match.group(0) and "le" not in labels:
                errors.append(
                    "Classic histogram_quantile over *_bucket series is missing 'le' in 'by (...)' clause."
                )

    # Check counter suffix metrics not wrapped in rate/irate/increase
    counter_tokens = re.findall(r"\b([a-zA-Z_:][a-zA-Z0-9_:]*_(?:total|bucket))\b", q)
    for token in set(counter_tokens):
        if not any(w in q for w in SAFE_WRAPPERS):
            warnings.append(
                f"Counter metric '{token}' appears without rate(), irate(), or increase()."
            )

    return {
        "valid": len(errors) == 0,
        "query": q,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint a PromQL expression offline.")
    parser.add_argument("--query", required=True, help="PromQL expression string")
    args = parser.parse_args()

    result = lint_promql(args.query)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
