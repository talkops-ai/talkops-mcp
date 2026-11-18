#!/usr/bin/env python3
"""Offline helper to compute RFC3339 UTC maintenance silence windows with safety buffers.

Usage:
  python3 plan_maintenance_window.py \
    --start "2026-03-29T10:00:00+05:30" \
    --duration-minutes 120 \
    --buffer-before-minutes 5 \
    --buffer-after-minutes 15 \
    --matchers 'service="checkout",env="prod"' \
    --created-by "sre@example.com" \
    --comment "CHG-1042: Planned checkout DB migration"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_SINGLE_MATCHER_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*(.*?)\s*$"
)


def parse_start_time(raw: str, tz_name: str | None) -> datetime:
    text = raw.strip()
    if text.lower() == "now":
        return datetime.now(timezone.utc)
    norm = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    dt = datetime.fromisoformat(norm)
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        if not tz_name:
            raise ValueError(
                f"Timestamp '{raw}' has no timezone offset and --timezone was not provided."
            )
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone '{tz_name}'.") from exc
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


def parse_matchers_arg(raw: str | None) -> list[dict[str, object]]:
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    if text.startswith("["):
        return json.loads(text)
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    out: list[dict[str, object]] = []
    for part in text.split(","):
        tok = part.strip()
        if not tok:
            continue
        m = _SINGLE_MATCHER_RE.match(tok)
        if not m:
            raise ValueError(f"Invalid matcher token '{tok}'.")
        name, op, val = m.group(1), m.group(2), m.group(3).strip().strip('"').strip("'")
        out.append(
            {
                "name": name,
                "value": val,
                "isRegex": op in ("=~", "!~"),
                "isEqual": op in ("=", "=~"),
            }
        )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute RFC3339 UTC Alertmanager maintenance window timestamps."
    )
    parser.add_argument(
        "--start",
        default="now",
        help="Maintenance start time in ISO-8601/RFC3339 or 'now' (default: now)",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help="IANA timezone name if --start omits an offset (e.g. 'Asia/Kolkata', 'America/New_York')",
    )
    parser.add_argument(
        "--duration-minutes",
        type=int,
        required=True,
        help="Core maintenance duration in minutes (> 0)",
    )
    parser.add_argument(
        "--buffer-before-minutes",
        type=int,
        default=0,
        help="Pre-maintenance buffer in minutes (default: 0)",
    )
    parser.add_argument(
        "--buffer-after-minutes",
        type=int,
        default=10,
        help="Post-maintenance recovery buffer in minutes (default: 10)",
    )
    parser.add_argument(
        "--max-duration-minutes",
        type=int,
        default=1440,
        help="Maximum allowed total duration in minutes (default: 1440)",
    )
    parser.add_argument(
        "--matchers",
        default=None,
        help="Optional matcher list or comma-separated matcher expressions",
    )
    parser.add_argument(
        "--created-by",
        default=None,
        help="Optional operator email or handle",
    )
    parser.add_argument(
        "--comment",
        default=None,
        help="Optional change ticket / maintenance comment",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.duration_minutes <= 0:
            raise ValueError("--duration-minutes must be positive.")
        if args.buffer_before_minutes < 0 or args.buffer_after_minutes < 0:
            raise ValueError("Buffer minutes cannot be negative.")

        core_start = parse_start_time(args.start, args.timezone)
        core_end = core_start + timedelta(minutes=args.duration_minutes)

        effective_start = core_start - timedelta(
            minutes=args.buffer_before_minutes
        )
        effective_end = core_end + timedelta(minutes=args.buffer_after_minutes)
        total_minutes = int(
            (effective_end - effective_start).total_seconds() // 60
        )

        if total_minutes > args.max_duration_minutes:
            raise ValueError(
                f"Total window ({total_minutes}m including buffers) exceeds "
                f"--max-duration-minutes ({args.max_duration_minutes}m)."
            )

        matchers = parse_matchers_arg(args.matchers)
        result = {
            "valid": True,
            "starts_at": effective_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ends_at": effective_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "core_starts_at": core_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "core_ends_at": core_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_minutes": total_minutes,
            "buffer_before_minutes": args.buffer_before_minutes,
            "buffer_after_minutes": args.buffer_after_minutes,
            "matchers": matchers,
            "created_by": args.created_by,
            "comment": args.comment,
        }
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps({"valid": False, "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
