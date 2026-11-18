#!/usr/bin/env python3
"""Offline deterministic validator for Alertmanager silence requests (`SP001`–`SP009`).

Maintains 100% rule parity with `alertmanager_mcp_server.domain.silence_policy.SilencePolicy`.

Usage:
  python3 validate_silence_request.py \
    --matchers '[{"name":"service","value":"checkout","isRegex":false,"isEqual":true}]' \
    --duration-minutes 120 \
    --created-by "sre@example.com" \
    --comment "CHG-1042: Planned DB upgrade"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
UNSUPPORTED_RE2_RE = re.compile(r"\(\?(?:=|!|<=|<!|>|\()|\\[1-9]")
SINGLE_MATCHER_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*(.*?)\s*$", re.DOTALL
)
TICKET_HINT_RE = re.compile(
    r"(?:[A-Z][A-Z0-9]+-\d+|INC\d+|CHG\d+|PR-\d+|#\d+|https?://)",
    re.IGNORECASE,
)

FORBIDDEN_SOLE_LABELS = frozenset(
    {"severity", "env", "environment", "cluster", "region", "datacenter"}
)
WATCHDOG_NAMES = frozenset(
    {"watchdog", "deadmansswitch", "alertmanagerwatchdog"}
)
PLACEHOLDER_AUTHORS = frozenset(
    {"", "mcp", "anonymous", "unknown", "default", "none"}
)


def parse_matchers_input(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s.startswith("[") or s.startswith("{"):
            try:
                parsed = json.loads(s)
                return parse_matchers_input(parsed)
            except json.JSONDecodeError:
                pass
        if s.startswith("{") and s.endswith("}"):
            s = s[1:-1].strip()
        tokens = [t.strip() for t in s.split(",") if t.strip()]
        out: list[dict[str, Any]] = []
        for tok in tokens:
            m = SINGLE_MATCHER_RE.match(tok)
            if not m:
                raise ValueError(f"Invalid matcher syntax '{tok}'.")
            name, op, val = m.group(1), m.group(2), m.group(3).strip()
            if (len(val) >= 2 and val[0] == '"' and val[-1] == '"') or (
                len(val) >= 2 and val[0] == "'" and val[-1] == "'"
            ):
                val = val[1:-1]
            out.append(
                {
                    "name": name,
                    "value": val,
                    "isRegex": op in ("=~", "!~"),
                    "isEqual": op in ("=", "=~"),
                }
            )
        return out

    if isinstance(raw, dict):
        if "name" in raw and "value" in raw:
            return [raw]
        return [
            {
                "name": str(k),
                "value": str(v),
                "isRegex": False,
                "isEqual": True,
            }
            for k, v in raw.items()
        ]

    if isinstance(raw, list):
        result: list[dict[str, Any]] = []
        for item in raw:
            result.extend(parse_matchers_input(item))
        return result

    raise ValueError(f"Unsupported matchers input type: {type(raw).__name__}")


def validate_silence_payload(
    *,
    matchers_raw: Any,
    starts_at: str | None = None,
    ends_at: str | None = None,
    duration_minutes: int | None = None,
    created_by: str | None = None,
    comment: str | None = None,
    max_duration_minutes: int = 1440,
    comment_pattern: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    compiled_matchers: list[dict[str, Any]] = []

    try:
        parsed_list = parse_matchers_input(matchers_raw)
        for m in parsed_list:
            name = str(m.get("name", "")).strip()
            value = str(m.get("value", ""))
            is_regex = bool(m.get("isRegex", m.get("is_regex", False)))
            is_equal = bool(m.get("isEqual", m.get("is_equal", True)))
            if not LABEL_NAME_RE.match(name):
                raise ValueError(f"Invalid label name '{name}'.")
            compiled_re = None
            if is_regex:
                if UNSUPPORTED_RE2_RE.search(value):
                    raise ValueError(
                        f"Regex '{value}' uses PCRE constructs unsupported by Go RE2."
                    )
                try:
                    compiled_re = re.compile(f"^(?:{value})$", re.DOTALL)
                except re.error as exc:
                    raise ValueError(
                        f"Invalid regular expression '{value}': {exc}"
                    ) from exc
            compiled_matchers.append(
                {
                    "name": name,
                    "value": value,
                    "isRegex": is_regex,
                    "isEqual": is_equal,
                    "_re": compiled_re,
                }
            )
    except ValueError as exc:
        errors.append(
            {
                "rule_id": "SP001",
                "severity": "error",
                "message": str(exc),
                "remediation": "Provide valid Alertmanager matchers with RE2-compatible regular expressions.",
            }
        )

    if not compiled_matchers and not errors:
        errors.append(
            {
                "rule_id": "SP001",
                "severity": "error",
                "message": "Silence must contain at least one label matcher.",
                "remediation": "Add at least one positive matcher such as alertname or service.",
            }
        )

    if compiled_matchers:
        # SP003: Wildcard regex check
        for m in compiled_matchers:
            if (
                m["isRegex"]
                and m["isEqual"]
                and m["value"].strip()
                in (".*", ".+", "^.*$", "^.+$", "(.*)", "(.+)")
            ):
                errors.append(
                    {
                        "rule_id": "SP003",
                        "severity": "error",
                        "message": f"Matcher '{m['name']}=~\"{m['value']}\"' uses a wildcard regex.",
                        "remediation": "Replace wildcard regex with explicit values or bounded alternation.",
                    }
                )

        # SP002: Positive non-empty matcher check
        def _matches_val(m: dict[str, Any], cand: str) -> bool:
            if m["isRegex"]:
                matched = bool(m["_re"].match(cand))
            else:
                matched = cand == m["value"]
            return matched if m["isEqual"] else not matched

        non_empty_pos = [
            m
            for m in compiled_matchers
            if m["isEqual"] and not _matches_val(m, "")
        ]
        if not non_empty_pos:
            errors.append(
                {
                    "rule_id": "SP002",
                    "severity": "error",
                    "message": "Silence has no positive matcher that excludes empty label values.",
                    "remediation": "Include at least one positive matcher (= or =~) that does not match ''.",
                }
            )
        else:
            pos_names = {m["name"].lower() for m in non_empty_pos}
            if pos_names.issubset(FORBIDDEN_SOLE_LABELS):
                errors.append(
                    {
                        "rule_id": "SP004",
                        "severity": "error",
                        "message": f"Silence is scoped solely by broad labels ({sorted(pos_names)}).",
                        "remediation": "Add a narrowing matcher such as 'alertname', 'service', 'instance', or 'job'.",
                    }
                )

        # SP005: Watchdog check
        for m in compiled_matchers:
            if m["name"] == "alertname" and m["isEqual"]:
                is_wc = m["isRegex"] and m["value"].strip() in (
                    ".*",
                    ".+",
                    "^.*$",
                    "^.+$",
                    "(.*)",
                    "(.+)",
                )
                if not is_wc:
                    if not m["isRegex"] and m["value"].lower() in WATCHDOG_NAMES:
                        errors.append(
                            {
                                "rule_id": "SP005",
                                "severity": "error",
                                "message": f"Silencing heartbeat alert '{m['value']}' is prohibited.",
                                "remediation": "Never silence Watchdog/DeadMansSwitch alerts.",
                            }
                        )
                    elif m["isRegex"] and _matches_val(m, "Watchdog"):
                        errors.append(
                            {
                                "rule_id": "SP005",
                                "severity": "error",
                                "message": "Regex matcher on alertname matches heartbeat alert 'Watchdog'.",
                                "remediation": "Exclude Watchdog from the alertname regex.",
                            }
                        )

    # SP006 & SP007: Time window & duration cap
    ref_now = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    starts_utc: str | None = None
    ends_utc: str | None = None
    total_mins: float | None = None

    try:
        if starts_at is not None:
            s_raw = starts_at.strip()
            if "T" not in s_raw and " " not in s_raw:
                raise ValueError("starts_at must be a full RFC3339 timestamp.")
            s_norm = s_raw[:-1] + "+00:00" if s_raw.endswith(("Z", "z")) else s_raw
            start_dt = datetime.fromisoformat(s_norm)
            if start_dt.tzinfo is None or start_dt.tzinfo.utcoffset(start_dt) is None:
                raise ValueError("starts_at is missing an explicit timezone offset ('Z' or '±HH:MM').")
            start_dt = start_dt.astimezone(timezone.utc)
        else:
            start_dt = ref_now

        if ends_at is not None:
            e_raw = ends_at.strip()
            if "T" not in e_raw and " " not in e_raw:
                raise ValueError("ends_at must be a full RFC3339 timestamp.")
            e_norm = e_raw[:-1] + "+00:00" if e_raw.endswith(("Z", "z")) else e_raw
            end_dt = datetime.fromisoformat(e_norm)
            if end_dt.tzinfo is None or end_dt.tzinfo.utcoffset(end_dt) is None:
                raise ValueError("ends_at is missing an explicit timezone offset ('Z' or '±HH:MM').")
            end_dt = end_dt.astimezone(timezone.utc)
        else:
            dur = duration_minutes if duration_minutes is not None else 120
            if dur <= 0:
                raise ValueError(f"duration_minutes must be positive (got {dur}).")
            end_dt = start_dt + timedelta(minutes=dur)

        if end_dt <= start_dt:
            raise ValueError("ends_at must be strictly after starts_at.")
        if end_dt <= ref_now:
            raise ValueError("ends_at is in the past.")

        starts_utc = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        ends_utc = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        total_mins = (end_dt - start_dt).total_seconds() / 60.0

        if total_mins > max_duration_minutes:
            errors.append(
                {
                    "rule_id": "SP007",
                    "severity": "error",
                    "message": (
                        f"Silence duration ({total_mins:.1f}m) exceeds maximum "
                        f"allowed duration ({max_duration_minutes}m)."
                    ),
                    "remediation": f"Reduce duration so the total window is <= {max_duration_minutes} minutes.",
                }
            )
    except ValueError as exc:
        errors.append(
            {
                "rule_id": "SP006",
                "severity": "error",
                "message": str(exc),
                "remediation": "Provide valid RFC3339 timestamps with explicit timezone offsets.",
            }
        )

    # SP008: Author attribution
    author_clean = (created_by or "").strip()
    if author_clean.lower() in PLACEHOLDER_AUTHORS:
        errors.append(
            {
                "rule_id": "SP008",
                "severity": "error",
                "message": f"Silence requires explicit author attribution in 'created_by' (got '{created_by or ''}').",
                "remediation": "Provide operator identity or email in created_by.",
            }
        )

    # SP009: Comment / ticket reference
    comment_clean = (comment or "").strip()
    if len(comment_clean) < 3:
        errors.append(
            {
                "rule_id": "SP009",
                "severity": "error",
                "message": "Silence requires a descriptive 'comment' (minimum 3 characters).",
                "remediation": "Include the ticket ID or maintenance reason in comment.",
            }
        )
    elif comment_pattern and not re.search(comment_pattern, comment_clean):
        errors.append(
            {
                "rule_id": "SP009",
                "severity": "error",
                "message": f"Comment does not match required pattern '{comment_pattern}'.",
                "remediation": f"Include a ticket reference matching '{comment_pattern}'.",
            }
        )
    elif not TICKET_HINT_RE.search(comment_clean):
        warnings.append(
            {
                "rule_id": "SP009",
                "severity": "warning",
                "message": "Silence comment does not reference an incident or change ticket ID.",
                "remediation": "Consider adding a ticket ID (e.g. JIRA-123, CHG-42, #123).",
            }
        )

    clean_matchers = [
        {
            "name": m["name"],
            "value": m["value"],
            "isRegex": m["isRegex"],
            "isEqual": m["isEqual"],
        }
        for m in compiled_matchers
    ]

    return {
        "valid": len(errors) == 0,
        "violations": errors,
        "warnings": warnings,
        "matchers": clean_matchers,
        "starts_at": starts_utc,
        "ends_at": ends_utc,
        "duration_minutes": round(total_mins, 2) if total_mins is not None else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate an Alertmanager silence request against policy rules SP001-SP009."
    )
    parser.add_argument(
        "--matchers",
        required=True,
        help="Matchers as JSON array, JSON object, or comma-separated matcher expressions",
    )
    parser.add_argument(
        "--starts-at",
        default=None,
        help="Optional RFC3339 start timestamp with timezone offset",
    )
    parser.add_argument(
        "--ends-at",
        default=None,
        help="Optional RFC3339 end timestamp with timezone offset",
    )
    parser.add_argument(
        "--duration-minutes",
        type=int,
        default=None,
        help="Optional duration in minutes (default: 120 when --ends-at is omitted)",
    )
    parser.add_argument(
        "--created-by",
        default="",
        help="Creator identity (required by SP008)",
    )
    parser.add_argument(
        "--comment",
        default="",
        help="Justification / ticket reference (required by SP009)",
    )
    parser.add_argument(
        "--max-duration-minutes",
        type=int,
        default=1440,
        help="Maximum allowed silence duration in minutes (default: 1440)",
    )
    parser.add_argument(
        "--comment-pattern",
        default=None,
        help="Optional regex pattern that --comment must match",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = validate_silence_payload(
        matchers_raw=args.matchers,
        starts_at=args.starts_at,
        ends_at=args.ends_at,
        duration_minutes=args.duration_minutes,
        created_by=args.created_by,
        comment=args.comment,
        max_duration_minutes=args.max_duration_minutes,
        comment_pattern=args.comment_pattern,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
