#!/usr/bin/env python3
"""Offline CLI script to compute critical path and self-time hotspots from an OTLP JSON trace."""

import argparse
import json
import sys
from typing import Any, Dict, List, Tuple

SAMPLE_TRACE: Dict[str, Any] = {
    "batches": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "api-gateway"}}
                ]
            },
            "scopeSpans": [
                {
                    "spans": [
                        {
                            "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
                            "spanId": "0000000000000001",
                            "name": "GET /checkout",
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000000500000000",
                        },
                        {
                            "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
                            "spanId": "0000000000000002",
                            "parentSpanId": "0000000000000001",
                            "name": "SELECT * FROM orders",
                            "startTimeUnixNano": "1700000000050000000",
                            "endTimeUnixNano": "1700000000450000000",
                        },
                    ]
                }
            ],
        }
    ]
}


def merge_intervals(intervals: List[Tuple[int, int]]) -> int:
    if not intervals:
        return 0
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    cur_s, cur_e = sorted_iv[0]
    total = 0
    for s, e in sorted_iv[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += max(0, cur_e - cur_s)
            cur_s, cur_e = s, e
    total += max(0, cur_e - cur_s)
    return total


def analyze_trace(payload: Dict[str, Any]) -> Dict[str, Any]:
    spans: List[Dict[str, Any]] = []
    batches = payload.get("batches") or payload.get("resourceSpans") or []
    for batch in batches:
        for scope in batch.get("scopeSpans") or batch.get("instrumentationLibrarySpans") or []:
            for s in scope.get("spans", []):
                start = int(s.get("startTimeUnixNano", 0))
                end = int(s.get("endTimeUnixNano", start))
                spans.append(
                    {
                        "span_id": s.get("spanId", ""),
                        "parent_span_id": s.get("parentSpanId", ""),
                        "name": s.get("name", ""),
                        "start": start,
                        "end": max(start, end),
                        "duration_ms": (max(start, end) - start) / 1_000_000.0,
                    }
                )
    total_trace_ms = (
        (max(s["end"] for s in spans) - min(s["start"] for s in spans)) / 1_000_000.0
        if spans
        else 0.0
    )
    children_by_parent: Dict[str, List[Tuple[int, int]]] = {}
    for s in spans:
        pid = s["parent_span_id"]
        if pid:
            children_by_parent.setdefault(pid, []).append((s["start"], s["end"]))

    hotspots = []
    for s in spans:
        child_ns = merge_intervals(children_by_parent.get(s["span_id"], []))
        self_ms = max(0.0, s["duration_ms"] - (child_ns / 1_000_000.0))
        ratio = (self_ms / total_trace_ms) if total_trace_ms > 0 else 0.0
        hotspots.append(
            {
                "span_id": s["span_id"],
                "name": s["name"],
                "duration_ms": round(s["duration_ms"], 3),
                "self_time_ms": round(self_ms, 3),
                "self_time_ratio": round(ratio, 4),
            }
        )
    hotspots.sort(key=lambda x: x["self_time_ms"], reverse=True)
    return {
        "span_count": len(spans),
        "total_duration_ms": round(total_trace_ms, 3),
        "self_time_hotspots": hotspots,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute self-time hotspots from an OTLP JSON trace file or sample."
    )
    parser.add_argument("--file", help="Path to OTLP JSON trace file (optional).")
    parser.add_argument("--json", dest="json_str", help="Inline OTLP JSON trace payload (optional).")
    args = parser.parse_args()
    if args.json_str:
        data = json.loads(args.json_str)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = SAMPLE_TRACE
    print(json.dumps(analyze_trace(data), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
