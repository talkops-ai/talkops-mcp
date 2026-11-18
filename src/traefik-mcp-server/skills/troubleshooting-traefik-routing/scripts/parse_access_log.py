#!/usr/bin/env python3
"""Offline Traefik JSON & CLF access log parser with secret/token redaction."""

import argparse
from collections import Counter
import json
import re
import sys


CLF_RE = re.compile(
    r'^(?P<client_ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+[^"]+"\s+'
    r'(?P<status>\d{3})\s+(?P<bytes>\d+|-)'
)
SENSITIVE_QUERY_RE = re.compile(
    r"(?i)((?:token|access_token|api_key|apikey|secret|password|sig)=)([^&\s\"']+)"
)


def redact_path(path: str) -> str:
    return SENSITIVE_QUERY_RE.sub(r"\1[REDACTED]", path or "/")


def parse_lines(lines: list[str], group_by: str = "status") -> dict:
    counts: Counter[str] = Counter()
    samples = []
    scanned = 0
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        scanned += 1
        rec = None
        if s.startswith("{"):
            try:
                obj = json.loads(s)
                rec = {
                    "status": str(obj.get("DownstreamStatus", obj.get("OriginStatus", 0))),
                    "router": str(obj.get("RouterName", "-")),
                    "service": str(obj.get("ServiceName", "-")),
                    "path": redact_path(str(obj.get("RequestPath", "/"))),
                    "client_ip": str(obj.get("ClientHost", "-")),
                }
            except Exception:
                pass
        if rec is None:
            m = CLF_RE.match(s)
            if m:
                rec = {
                    "status": m.group("status"),
                    "router": "-",
                    "service": "-",
                    "path": redact_path(m.group("path")),
                    "client_ip": m.group("client_ip"),
                }
        if rec:
            counts[rec.get(group_by, "-")] += 1
            if len(samples) < 5:
                samples.append(rec)

    return {
        "total_lines_scanned": scanned,
        "group_by": group_by,
        "groups": [{"key": k, "count": c} for k, c in counts.most_common()],
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse Traefik JSON or CLF access logs offline with automatic token redaction."
    )
    parser.add_argument("--log-file", default=None, help="Path to access log file")
    parser.add_argument("--lines", default=None, help="Inline multi-line JSON/CLF access log string")
    parser.add_argument(
        "--group-by",
        choices=("status", "router", "service", "path", "client_ip"),
        default="status",
        help="Dimension to group counts by",
    )
    args = parser.parse_args()

    if args.log_file:
        with open(args.log_file, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    elif args.lines:
        lines = args.lines.splitlines()
    else:
        lines = [
            '{"ClientHost":"10.0.0.5","RequestMethod":"GET","RequestPath":"/api/v1/orders?token=secret123","DownstreamStatus":200,"RouterName":"prod-orders@kubernetescrd","ServiceName":"prod-orders-svc"}',
            '{"ClientHost":"10.0.0.9","RequestMethod":"POST","RequestPath":"/api/v1/orders","DownstreamStatus":502,"RouterName":"prod-orders@kubernetescrd","ServiceName":"prod-orders-svc"}',
        ]
    sys.stdout.write(json.dumps(parse_lines(lines, args.group_by), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
