#!/usr/bin/env python3
"""Offline CLI script to extract W3C traceparent and 32-hex trace IDs from log lines."""

import argparse
import json
import re
import sys
from typing import Dict, List

TRACEPARENT_RE = re.compile(
    r"\b00-([0-9a-fA-F]{32})-([0-9a-fA-F]{16})-([0-9a-fA-F]{2})\b"
)
KEYED_TRACE_RE = re.compile(
    r'(?:trace_id|traceId|otelTraceID|traceid)["\'\s:=]+([0-9a-fA-F]{32})\b'
)

DEFAULT_SAMPLE_LOG = (
    'level=error msg="checkout failed" '
    "traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 "
    'service=checkout status=500'
)


def extract_from_text(text: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    seen = set()
    for match in TRACEPARENT_RE.finditer(text):
        tid = match.group(1).lower()
        if tid != "0" * 32 and tid not in seen:
            seen.add(tid)
            results.append(
                {
                    "trace_id": tid,
                    "span_id": match.group(2).lower(),
                    "trace_flags": match.group(3).lower(),
                    "source": "traceparent",
                }
            )
    for match in KEYED_TRACE_RE.finditer(text):
        tid = match.group(1).lower()
        if tid != "0" * 32 and tid not in seen:
            seen.add(tid)
            results.append({"trace_id": tid, "source": "keyed_field"})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract W3C traceparent and 32-hex trace IDs from log text."
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_SAMPLE_LOG,
        help="Log text to parse (defaults to built-in sample log line).",
    )
    args = parser.parse_args()
    extracted = extract_from_text(args.text)
    print(json.dumps({"count": len(extracted), "extracted": extracted}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
