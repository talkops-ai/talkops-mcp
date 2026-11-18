#!/usr/bin/env python3
"""Offline Alertmanager routing tree & inhibition simulator (`amtool config routes test` parity).

Usage:
  python3 test_routes.py \
    --config alertmanager.yml \
    --labels '{"alertname":"HighLatency","service":"checkout","severity":"critical","env":"prod"}'
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None

SINGLE_MATCHER_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*(.*?)\s*$", re.DOTALL
)

WEEKDAY_MAP = {
    "sunday": 0, "sun": 0, "0": 0,
    "monday": 1, "mon": 1, "1": 1,
    "tuesday": 2, "tue": 2, "2": 2,
    "wednesday": 3, "wed": 3, "3": 3,
    "thursday": 4, "thu": 4, "4": 4,
    "friday": 5, "fri": 5, "5": 5,
    "saturday": 6, "sat": 6, "6": 6,
}

MONTH_MAP = {
    "january": 1, "jan": 1, "1": 1,
    "february": 2, "feb": 2, "2": 2,
    "march": 3, "mar": 3, "3": 3,
    "april": 4, "apr": 4, "4": 4,
    "may": 5, "5": 5,
    "june": 6, "jun": 6, "6": 6,
    "july": 7, "jul": 7, "7": 7,
    "august": 8, "aug": 8, "8": 8,
    "september": 9, "sep": 9, "9": 9,
    "october": 10, "oct": 10, "10": 10,
    "november": 11, "nov": 11, "11": 11,
    "december": 12, "dec": 12, "12": 12,
}


def split_matcher_tokens(text: str) -> list[str]:
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    if not s:
        return []
    parts: list[str] = []
    buf: list[str] = []
    in_quote: str | None = None
    escaped = False
    for ch in s:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            buf.append(ch)
            escaped = True
            continue
        if in_quote is not None:
            buf.append(ch)
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ('"', "'"):
            in_quote = ch
            buf.append(ch)
            continue
        if ch == ",":
            tok = "".join(buf).strip()
            if tok:
                parts.append(tok)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def compile_matcher_token(token: str) -> dict[str, Any]:
    m = SINGLE_MATCHER_RE.match(token.strip())
    if not m:
        raise ValueError(f"Invalid matcher syntax '{token}'.")
    name, op, raw_val = m.group(1), m.group(2), m.group(3).strip()
    if (len(raw_val) >= 2 and raw_val[0] == '"' and raw_val[-1] == '"') or (
        len(raw_val) >= 2 and raw_val[0] == "'" and raw_val[-1] == "'"
    ):
        val = raw_val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    else:
        val = raw_val
    is_regex = op in ("=~", "!~")
    is_equal = op in ("=", "=~")
    compiled_re = re.compile(f"^(?:{val})$", re.DOTALL) if is_regex else None
    return {
        "name": name,
        "value": val,
        "op": op,
        "is_regex": is_regex,
        "is_equal": is_equal,
        "re": compiled_re,
        "text": f'{name}{op}"{val}"',
    }


def extract_block_matchers(
    block: Mapping[str, Any],
    *,
    match_key: str = "match",
    match_re_key: str = "match_re",
    matchers_key: str = "matchers",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    raw_match = block.get(match_key)
    if isinstance(raw_match, Mapping):
        for k, v in raw_match.items():
            out.append(compile_matcher_token(f'{k}="{v}"'))
    raw_match_re = block.get(match_re_key)
    if isinstance(raw_match_re, Mapping):
        for k, v in raw_match_re.items():
            out.append(compile_matcher_token(f'{k}=~"{v}"'))
    raw_matchers = block.get(matchers_key)
    if isinstance(raw_matchers, Sequence) and not isinstance(raw_matchers, (str, bytes)):
        for expr in raw_matchers:
            if isinstance(expr, str):
                for tok in split_matcher_tokens(expr):
                    out.append(compile_matcher_token(tok))
    return out


def matchers_match(matchers: Sequence[dict[str, Any]], labels: Mapping[str, str]) -> bool:
    for m in matchers:
        cand = str(labels.get(m["name"], ""))
        if m["is_regex"]:
            hit = bool(m["re"].match(cand))
        else:
            hit = cand == m["value"]
        if not (hit if m["is_equal"] else not hit):
            return False
    return True


def _match_interval_entry(entry: Mapping[str, Any], at_time: datetime) -> bool:
    loc = str(entry.get("location") or "UTC").strip()
    try:
        tz = ZoneInfo(loc)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    dt = at_time.astimezone(tz)

    times = entry.get("times") or []
    if times:
        cur_m = dt.hour * 60 + dt.minute + (dt.second / 60.0)
        ok_t = False
        for t in times:
            sh, sm = (int(x) for x in str(t.get("start_time", "00:00")).split(":"))
            eh, em = (int(x) for x in str(t.get("end_time", "24:00")).split(":"))
            s_m = 1440 if (sh == 24 and sm == 0) else sh * 60 + sm
            e_m = 1440 if (eh == 24 and em == 0) else eh * 60 + em
            if s_m <= cur_m < e_m:
                ok_t = True
                break
        if not ok_t:
            return False

    weekdays = entry.get("weekdays") or []
    if weekdays:
        am_w = (dt.weekday() + 1) % 7
        ok_w = False
        for w in weekdays:
            tok = str(w).strip().lower()
            if ":" in tok:
                l_s, r_s = tok.split(":", 1)
                lw, rw = WEEKDAY_MAP[l_s.strip()], WEEKDAY_MAP[r_s.strip()]
                if (lw <= rw and lw <= am_w <= rw) or (lw > rw and (am_w >= lw or am_w <= rw)):
                    ok_w = True
                    break
            elif am_w == WEEKDAY_MAP[tok]:
                ok_w = True
                break
        if not ok_w:
            return False

    doms = entry.get("days_of_month") or []
    if doms:
        max_d = calendar.monthrange(dt.year, dt.month)[1]
        ok_d = False
        for d in doms:
            tok = str(d).strip()
            if ":" in tok:
                l_s, r_s = tok.split(":", 1)
                ld = int(l_s) if int(l_s) >= 0 else max_d + 1 + int(l_s)
                rd = int(r_s) if int(r_s) >= 0 else max_d + 1 + int(r_s)
                if ld <= dt.day <= rd:
                    ok_d = True
                    break
            else:
                vd = int(tok) if int(tok) >= 0 else max_d + 1 + int(tok)
                if dt.day == vd:
                    ok_d = True
                    break
        if not ok_d:
            return False

    months = entry.get("months") or []
    if months:
        ok_m = False
        for mo in months:
            tok = str(mo).strip().lower()
            if ":" in tok:
                l_s, r_s = tok.split(":", 1)
                if MONTH_MAP[l_s.strip()] <= dt.month <= MONTH_MAP[r_s.strip()]:
                    ok_m = True
                    break
            elif dt.month == MONTH_MAP[tok]:
                ok_m = True
                break
        if not ok_m:
            return False

    years = entry.get("years") or []
    if years:
        ok_y = False
        for yr in years:
            tok = str(yr).strip()
            if ":" in tok:
                l_s, r_s = tok.split(":", 1)
                if int(l_s) <= dt.year <= int(r_s):
                    ok_y = True
                    break
            elif dt.year == int(tok):
                ok_y = True
                break
        if not ok_y:
            return False

    return True


def simulate_config_routing(
    config: Mapping[str, Any],
    labels: Mapping[str, str],
    *,
    at_time: datetime | None = None,
    active_alerts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    eval_dt = (
        at_time.astimezone(timezone.utc)
        if at_time and at_time.tzinfo
        else datetime.now(timezone.utc)
    )

    intervals: dict[str, list[Mapping[str, Any]]] = {}
    for sec in ("time_intervals", "mute_time_intervals"):
        for item in config.get(sec) or []:
            if isinstance(item, Mapping) and item.get("name"):
                intervals[str(item["name"])] = list(item.get("time_intervals") or [])

    def _build_node(
        raw: Mapping[str, Any], path: str, parent: dict[str, Any] | None
    ) -> dict[str, Any]:
        is_root = parent is None
        receiver = str(
            raw.get("receiver") or (parent["receiver"] if parent else "default")
        )
        group_by = (
            [str(x) for x in raw.get("group_by") or []]
            if "group_by" in raw and raw.get("group_by") is not None
            else (list(parent["group_by"]) if parent else [])
        )
        node: dict[str, Any] = {
            "path": path,
            "is_root": is_root,
            "receiver": receiver,
            "group_by": group_by,
            "group_wait": str(
                raw.get("group_wait")
                or (parent["group_wait"] if parent else "30s")
            ),
            "group_interval": str(
                raw.get("group_interval")
                or (parent["group_interval"] if parent else "5m")
            ),
            "repeat_interval": str(
                raw.get("repeat_interval")
                or (parent["repeat_interval"] if parent else "4h")
            ),
            "continue": bool(raw.get("continue", False)),
            "mute_time_intervals": [
                str(x) for x in raw.get("mute_time_intervals") or []
            ],
            "active_time_intervals": [
                str(x) for x in raw.get("active_time_intervals") or []
            ],
            "matchers": extract_block_matchers(raw),
            "children": [],
        }
        for idx, ch in enumerate(raw.get("routes") or []):
            if isinstance(ch, Mapping):
                node["children"].append(_build_node(ch, f"{path}/{idx}", node))
        return node

    root_raw = config.get("route")
    if not isinstance(root_raw, Mapping):
        root_raw = {"receiver": "default"}
    root_node = _build_node(root_raw, "root", None)

    def _match(node: dict[str, Any]) -> list[dict[str, Any]]:
        if not (node["is_root"] and not node["matchers"]):
            if not matchers_match(node["matchers"], labels):
                return []
        matched_children: list[dict[str, Any]] = []
        for ch in node["children"]:
            sub = _match(ch)
            if sub:
                matched_children.extend(sub)
                if not ch["continue"]:
                    break
        if not matched_children:
            return [node]
        return matched_children

    selected = _match(root_node)
    matched_routes: list[dict[str, Any]] = []
    receivers: list[str] = []
    active_receivers: list[str] = []
    muted_receivers: list[str] = []

    for node in selected:
        mute_reasons: list[str] = []
        act_names = node["active_time_intervals"]
        if act_names:
            if not any(
                any(_match_interval_entry(e, eval_dt) for e in intervals.get(n, []))
                for n in act_names
            ):
                mute_reasons.append(
                    "outside active_time_intervals: " + ", ".join(act_names)
                )
        mute_names = node["mute_time_intervals"]
        if mute_names:
            hit_m = [
                n
                for n in mute_names
                if any(_match_interval_entry(e, eval_dt) for e in intervals.get(n, []))
            ]
            if hit_m:
                mute_reasons.append(
                    "inside mute_time_intervals: " + ", ".join(hit_m)
                )
        is_muted = len(mute_reasons) > 0
        matched_routes.append(
            {
                "path": node["path"],
                "receiver": node["receiver"],
                "group_by": node["group_by"],
                "group_wait": node["group_wait"],
                "group_interval": node["group_interval"],
                "repeat_interval": node["repeat_interval"],
                "muted": is_muted,
                "mute_reasons": mute_reasons,
                "is_default_route": node["is_root"],
            }
        )
        if node["receiver"] not in receivers:
            receivers.append(node["receiver"])
        if is_muted:
            if node["receiver"] not in muted_receivers:
                muted_receivers.append(node["receiver"])
        else:
            if node["receiver"] not in active_receivers:
                active_receivers.append(node["receiver"])

    # Evaluate inhibition rules against active_alerts
    inhibited = False
    inhibiting_rules: list[int] = []
    norm_target = {str(k): str(v) for k, v in labels.items()}
    for idx, rule in enumerate(config.get("inhibit_rules") or []):
        if not isinstance(rule, Mapping):
            continue
        src_m = extract_block_matchers(
            rule,
            match_key="source_match",
            match_re_key="source_match_re",
            matchers_key="source_matchers",
        )
        tgt_m = extract_block_matchers(
            rule,
            match_key="target_match",
            match_re_key="target_match_re",
            matchers_key="target_matchers",
        )
        eq_labels = [str(x) for x in rule.get("equal") or []]
        if not tgt_m or not matchers_match(tgt_m, norm_target):
            continue
        for src_alert in active_alerts:
            raw_l = src_alert.get("labels", src_alert)
            if not isinstance(raw_l, Mapping):
                continue
            src_l = {str(k): str(v) for k, v in raw_l.items()}
            if src_l == norm_target:
                continue
            if not src_m or not matchers_match(src_m, src_l):
                continue
            if not all(src_l.get(k, "") == norm_target.get(k, "") for k in eq_labels):
                continue
            if matchers_match(tgt_m, src_l):
                continue
            inhibited = True
            inhibiting_rules.append(idx)
            break

    return {
        "matched_routes": matched_routes,
        "receivers": receivers,
        "active_receivers": active_receivers,
        "muted_receivers": muted_receivers,
        "fell_back_to_default": len(selected) == 1 and selected[0]["is_root"],
        "default_receiver": root_node["receiver"],
        "is_inhibited": inhibited,
        "inhibiting_rule_indices": inhibiting_rules,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulate Alertmanager routing tree and inhibition rules offline."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to Alertmanager YAML or JSON configuration file",
    )
    parser.add_argument(
        "--labels",
        required=True,
        help="Alert labels as JSON object or comma-separated key=value pairs",
    )
    parser.add_argument(
        "--at-time",
        default=None,
        help="Optional RFC3339 timestamp to evaluate time intervals at",
    )
    parser.add_argument(
        "--active-alerts",
        default=None,
        help="Optional JSON array of active alerts for inhibition testing",
    )
    return parser


def _parse_labels_arg(raw: str) -> dict[str, str]:
    s = raw.strip()
    if s.startswith("{"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass
    out: dict[str, str] = {}
    for tok in split_matcher_tokens(s):
        cm = compile_matcher_token(tok)
        out[cm["name"]] = cm["value"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        raw_cfg = Path(args.config).read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw_cfg) if yaml is not None else json.loads(raw_cfg)
        labels = _parse_labels_arg(args.labels)
        at_dt = None
        if args.at_time:
            t_str = args.at_time.strip()
            t_norm = t_str[:-1] + "+00:00" if t_str.endswith(("Z", "z")) else t_str
            at_dt = datetime.fromisoformat(t_norm)
        active_alerts = json.loads(args.active_alerts) if args.active_alerts else []
        res = simulate_config_routing(
            cfg, labels, at_time=at_dt, active_alerts=active_alerts
        )
        print(json.dumps(res, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
