#!/usr/bin/env python3
"""Infer the optimal Grafana Loki LogQL parser stage from sample log lines."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

NGINX_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[[^\]]+\]\s+"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+(?P<proto>[^"]+)"\s+(?P<status>\d{3})\s+(?P<bytes>\d+|-)'
)
ENVOY_RE = re.compile(
    r'^\[[^\]]+\]\s+"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+(?P<proto>[^"]+)"\s+(?P<status>\d{3})\s+(?P<flags>\S+)\s+\d+\s+\d+\s+\d+'
)
KLOG_RE = re.compile(r"^[IWEF]\d{4}\s+\d{2}:\d{2}:\d{2}\.\d+\s+\d+\s+[^:\]]+:\d+\]")
LOGFMT_KV_RE = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_.-]*)=("[^"]*"|\S+)')


def infer_parser_for_line(line: str) -> dict[str, Any]:
    """Inspect a sample log line and return the recommended LogQL parser stage."""
    raw = (line or "").strip()
    if not raw:
        return {
            "format": "empty",
            "recommended_parser": "",
            "fields": [],
            "explanation": "Empty log line provided.",
        }

    # 1. JSON check
    if raw.startswith("{") and raw.endswith("}"):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                keys = list(obj.keys())[:8]
                targeted = ", ".join(f'{k.replace(".", "_")}="{k}"' for k in keys[:4])
                return {
                    "format": "json",
                    "recommended_parser": f"| json {targeted}" if targeted else "| json",
                    "fields": keys,
                    "explanation": "Valid JSON object detected. Prefer targeted field extraction in '| json' to minimize CPU overhead.",
                }
        except json.JSONDecodeError:
            pass

    # 2. Nginx / Apache combined access log
    if NGINX_RE.match(raw):
        return {
            "format": "nginx_access",
            "recommended_parser": '| pattern `<client_ip> - <user> [<_>] "<method> <path> <protocol>" <status> <bytes> <_>`',
            "fields": ["client_ip", "user", "method", "path", "protocol", "status", "bytes"],
            "explanation": "Nginx/Apache access log structure detected. Use '| pattern' (5-10x faster than '| regexp').",
        }

    # 3. Envoy access log
    if ENVOY_RE.match(raw):
        return {
            "format": "envoy_access",
            "recommended_parser": '| pattern `[<_>] "<method> <path> <protocol>" <status> <response_flags> <bytes_rx> <bytes_tx> <duration_ms> <_>`',
            "fields": ["method", "path", "protocol", "status", "response_flags", "bytes_rx", "bytes_tx", "duration_ms"],
            "explanation": "Envoy proxy access log detected. Use '| pattern' for high-throughput positional extraction.",
        }

    # 4. Kubernetes klog
    if KLOG_RE.match(raw):
        return {
            "format": "klog",
            "recommended_parser": '| pattern `<severity><date> <time> <_> <source>] <msg>`',
            "fields": ["severity", "date", "time", "source", "msg"],
            "explanation": "Kubernetes klog header detected. Use '| pattern' (optionally chained with '| logfmt' for structured klog).",
        }

    # 5. Logfmt check (>= 3 key=value pairs)
    kv_matches = LOGFMT_KV_RE.findall(raw)
    if len(kv_matches) >= 2:
        keys = [k for k, _ in kv_matches[:8]]
        key_list = ", ".join(keys[:5])
        return {
            "format": "logfmt",
            "recommended_parser": f"| logfmt {key_list}",
            "fields": keys,
            "explanation": f"Detected {len(kv_matches)} key=value pairs. Use '| logfmt' with explicit key names.",
        }

    # 6. Anchor-delimited application text -> prefer '| pattern' first, '| regexp' fallback
    if " - " in raw or any(tok in raw for tok in (" triggered for ", " after ", " #")):
        return {
            "format": "anchored_text",
            "recommended_parser": '| pattern `<level> <_> - <event>`',
            "regexp_fallback": '| regexp `(?P<level>INFO|WARN|ERROR|DEBUG)\\s+(?P<msg>.*)`',
            "fields": ["level", "event"],
            "explanation": (
                "Fixed literal anchors detected: prefer '| pattern' (5-10x faster than '| regexp', zero RE2 backtracking) "
                "using fixed anchor literals and '<_>' wildcards; reserve Go RE2 '(?P<name>...)' '| regexp' (preceded by '|=') "
                "only as a fallback for variable/optional whitespace or optional segments."
            ),
        }

    # 7. Fallback to pattern / regexp
    return {
        "format": "unstructured",
        "recommended_parser": '| pattern `<level> <msg>`',
        "regexp_fallback": '| regexp `(?P<level>INFO|WARN|ERROR|DEBUG)\\s+(?P<msg>.*)`',
        "fields": ["level", "msg"],
        "explanation": "Unstructured text line. Call 'loki_get_log_patterns' to discover repeating '<_>' templates for '| pattern' (5-10x faster than '| regexp'), and reserve '| regexp' for variable segments.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Infer optimal LogQL parser stage from sample log lines.")
    parser.add_argument("--sample", help="Sample log line string")
    parser.add_argument("--input", help="File containing sample log line(s)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    sample_line = args.sample or ""
    if not sample_line and args.input and os.path.exists(args.input):
        with open(args.input, encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    sample_line = ln.strip()
                    break

    result = infer_parser_for_line(sample_line)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Detected Format:     {result['format']}")
        print(f"Recommended Parser:  {result['recommended_parser']}")
        print(f"Extracted Fields:    {', '.join(result['fields'])}")
        print(f"Explanation:         {result['explanation']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
