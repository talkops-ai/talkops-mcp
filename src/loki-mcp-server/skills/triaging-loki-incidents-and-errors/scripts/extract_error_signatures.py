#!/usr/bin/env python3
"""Cluster raw log lines into normalized error signatures and extract trace/request IDs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from typing import Any

UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HEX32_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")
HEX16_RE = re.compile(r"\b[0-9a-fA-F]{16}\b")
ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b")
NUM_RE = re.compile(r"\b\d+\b")

TRACE_ID_KV_RE = re.compile(r'(?:trace_id|traceId|traceID)\s*[=:]\s*["\']?([0-9a-fA-F-]{16,36})["\']?')
REQ_ID_KV_RE = re.compile(r'(?:request_id|requestId|req_id)\s*[=:]\s*["\']?([0-9a-zA-Z-]{8,64})["\']?')
SESSION_UUID_RE = re.compile(
    r'(?:(?:session_id|sessionId|session)\s*(?:[=:]|\s)\s*["\']?)?([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
)


def normalize_log_line(line: str) -> str:
    """Replace dynamic tokens in a log line to produce a canonical signature."""
    s = line.strip()
    s = ISO_TS_RE.sub("<TIMESTAMP>", s)
    s = UUID_RE.sub("<UUID>", s)
    s = HEX32_RE.sub("<TRACE_HEX>", s)
    s = HEX16_RE.sub("<SPAN_HEX>", s)
    s = IPV4_RE.sub("<IP>", s)
    s = NUM_RE.sub("<NUM>", s)
    return s


def extract_signatures(lines: list[str]) -> dict[str, Any]:
    """Cluster log lines by normalized signature and extract correlation IDs."""
    counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    trace_ids: list[str] = []
    request_ids: list[str] = []
    session_ids: list[str] = []

    for raw in lines:
        if not raw or not raw.strip():
            continue
        sig = normalize_log_line(raw)
        counts[sig] += 1
        if sig not in examples:
            examples[sig] = raw.strip()

        for tid in TRACE_ID_KV_RE.findall(raw):
            if tid not in trace_ids:
                trace_ids.append(tid)
        for rid in REQ_ID_KV_RE.findall(raw):
            if rid not in request_ids:
                request_ids.append(rid)
        for sid in SESSION_UUID_RE.findall(raw):
            if sid not in session_ids:
                session_ids.append(sid)

    clusters = [
        {
            "signature": sig,
            "count": count,
            "pct": round(count / max(len(lines), 1) * 100.0, 2),
            "sample": examples[sig],
        }
        for sig, count in counts.most_common(25)
    ]

    return {
        "total_lines": len(lines),
        "unique_signatures": len(counts),
        "clusters": clusters,
        "trace_ids": trace_ids[:20],
        "request_ids": request_ids[:20],
        "session_ids": session_ids[:20],
    }


def _load_lines(input_arg: str | None, extra_lines: list[str]) -> list[str]:
    lines: list[str] = list(extra_lines or [])
    if not input_arg:
        return lines

    content = input_arg
    if os.path.exists(input_arg):
        with open(input_arg, encoding="utf-8") as f:
            content = f.read()

    stripped = content.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, str):
                        lines.append(item)
                    elif isinstance(item, dict):
                        lines.append(str(item.get("line") or item.get("message") or item))
                return lines
            if isinstance(parsed, dict):
                for item in parsed.get("lines", parsed.get("logs", [])):
                    lines.append(str(item.get("line") if isinstance(item, dict) else item))
                return lines
        except json.JSONDecodeError:
            pass

    lines.extend([ln for ln in content.splitlines() if ln.strip()])
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cluster log lines into normalized error signatures.")
    parser.add_argument("--input", help="Path to log file/JSON or inline JSON/text string")
    parser.add_argument("--line", action="append", default=[], help="Individual log line (repeatable)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    lines = _load_lines(args.input, args.line)
    result = extract_signatures(lines)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Total lines: {result['total_lines']} | Unique signatures: {result['unique_signatures']}")
        for c in result["clusters"]:
            print(f"  [{c['count']}x | {c['pct']}%] {c['signature']}")
        if result["trace_ids"]:
            print(f"Extracted trace_ids: {', '.join(result['trace_ids'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
