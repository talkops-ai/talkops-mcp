"""Traefik access log (JSON & CLF) and controller log parser with automatic secret redaction."""

from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from traefik_mcp_server.utils.redaction import REDACTED_PLACEHOLDER

_SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "id_token",
    "refresh_token",
    "api_key",
    "apikey",
    "key",
    "secret",
    "password",
    "sig",
    "signature",
}

_CLF_REGEX = re.compile(
    r'^(?P<client_ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+(?P<proto>[^"]+)"\s+'
    r'(?P<status>\d{3})\s+(?P<size>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)"\s+\S+\s+'
    r'"(?P<router>[^"]*)"\s+"(?P<upstream>[^"]*)"\s+(?P<duration_ms>\d+(?:\.\d+)?)ms)?'
)


def redact_url_path(raw_path: str) -> str:
    """Redact sensitive query parameters from a request URL or path."""
    if not raw_path or "?" not in raw_path:
        return raw_path
    try:
        parts = urlsplit(raw_path)
        q_items = parse_qsl(parts.query, keep_blank_values=True)
        redacted_q = [
            (k, REDACTED_PLACEHOLDER if k.lower() in _SENSITIVE_QUERY_KEYS else v)
            for k, v in q_items
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted_q, safe="[]"), parts.fragment))
    except Exception:
        return re.sub(
            r"([?&](?:token|access_token|api_key|apikey|secret|password|key)=)[^&\s]+",
            rf"\1{REDACTED_PLACEHOLDER}",
            raw_path,
            flags=re.I,
        )


def parse_single_access_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single Traefik access log line (JSON or Common Log Format) into normalized fields."""
    text = (line or "").strip()
    if not text:
        return None

    # 1. Try JSON access log format
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and (
                "DownstreamStatus" in obj
                or "OriginStatus" in obj
                or "RequestPath" in obj
                or "RequestMethod" in obj
            ):
                status = int(obj.get("DownstreamStatus") or obj.get("OriginStatus") or 0)
                # Traefik JSON Duration is in nanoseconds
                raw_dur = obj.get("Duration", 0)
                duration_ms = round(float(raw_dur) / 1_000_000.0, 2) if raw_dur and float(raw_dur) > 10000 else float(raw_dur or 0)
                raw_path = str(obj.get("RequestPath") or obj.get("RequestURI") or "/")
                clean_path = redact_url_path(raw_path)

                entry: Dict[str, Any] = {
                    "client_ip": str(obj.get("ClientHost") or obj.get("ClientAddr", "").split(":")[0] or "-"),
                    "method": str(obj.get("RequestMethod") or "GET"),
                    "host": str(obj.get("RequestHost") or obj.get("RequestAddr") or "-").split(":")[0],
                    "path": clean_path,
                    "path_prefix": clean_path.split("?")[0] or "/",
                    "uri": clean_path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "router": str(obj.get("RouterName") or "-"),
                    "service": str(obj.get("ServiceName") or "-"),
                    "upstream": str(obj.get("ServiceAddr") or obj.get("ServiceURL") or "-"),
                    "time": str(obj.get("StartUTC") or obj.get("time") or ""),
                }
                # Redact any request_* or origin_* header fields
                redacted_headers: Dict[str, str] = {}
                for k, v in obj.items():
                    if k.startswith(("request_", "origin_")):
                        hdr_name = k.split("_", 1)[1].lower()
                        if hdr_name in ("authorization", "cookie", "set-cookie", "x-api-key") or "token" in hdr_name:
                            redacted_headers[k] = REDACTED_PLACEHOLDER
                        else:
                            redacted_headers[k] = str(v)
                if redacted_headers:
                    entry["headers"] = redacted_headers
                entry["raw"] = dict(entry)
                return entry
        except Exception:
            pass

    # 2. Try CLF access log format
    m = _CLF_REGEX.match(text)
    if m:
        gd = m.groupdict()
        clean_uri = redact_url_path(gd.get("path") or "/")
        entry = {
            "client_ip": gd.get("client_ip") or "-",
            "method": gd.get("method") or "GET",
            "host": "-",
            "path": clean_uri,
            "path_prefix": clean_uri.split("?")[0] or "/",
            "uri": clean_uri,
            "status": int(gd.get("status") or 0),
            "duration_ms": float(gd.get("duration_ms") or 0.0),
            "router": gd.get("router") or "-",
            "service": "-",
            "upstream": gd.get("upstream") or "-",
            "time": gd.get("time") or "",
        }
        entry["raw"] = dict(entry)
        return entry

    return None


def parse_single_controller_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single Traefik controller log line (JSON or logfmt/text)."""
    text = (line or "").strip()
    if not text:
        return None

    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and ("level" in obj or "msg" in obj or "message" in obj):
                return {
                    "level": str(obj.get("level") or "info").lower(),
                    "message": redact_url_path(str(obj.get("msg") or obj.get("message") or "")),
                    "router": str(obj.get("routerName") or obj.get("router") or "-"),
                    "service": str(obj.get("serviceName") or obj.get("service") or "-"),
                    "middleware": str(obj.get("middlewareName") or obj.get("middleware") or "-"),
                    "provider": str(obj.get("providerName") or obj.get("provider") or "-"),
                    "time": str(obj.get("time") or ""),
                }
        except Exception:
            pass

    if "level=" in text or "ERR " in text or "WRN " in text or "error" in text.lower():
        level_m = re.search(r"\blevel=([a-zA-Z]+)|\b(ERR|WRN|INF|DBG)\b", text)
        msg_m = re.search(r'\bmsg="([^"]+)"', text)
        router_m = re.search(r'\brouterName=([^\s"]+)', text)
        svc_m = re.search(r'\bserviceName=([^\s"]+)', text)
        mw_m = re.search(r'\bmiddlewareName=([^\s"]+)', text)
        prov_m = re.search(r'\bproviderName=([^\s"]+)', text)
        raw_lvl = (level_m.group(1) or level_m.group(2) if level_m else "info").lower()
        lvl_map = {"err": "error", "wrn": "warning", "inf": "info", "dbg": "debug"}
        return {
            "level": lvl_map.get(raw_lvl, raw_lvl),
            "message": redact_url_path(msg_m.group(1) if msg_m else text),
            "router": router_m.group(1) if router_m else "-",
            "service": svc_m.group(1) if svc_m else "-",
            "middleware": mw_m.group(1) if mw_m else "-",
            "provider": prov_m.group(1) if prov_m else "-",
            "time": "",
        }
    return None


def analyze_log_lines(
    lines: List[str],
    source: str = "access",
    filters: Optional[Dict[str, Any]] = None,
    group_by: str = "status",
    limit_samples: int = 5,
) -> Dict[str, Any]:
    """Filter, aggregate, and sample Traefik access or controller log lines."""
    flt = filters or {}
    total_scanned = len(lines)
    matched_entries: List[Dict[str, Any]] = []

    if source == "controller":
        for line in lines:
            parsed = parse_single_controller_log_line(line)
            if not parsed:
                continue
            if flt.get("level") and str(flt["level"]).lower() != parsed["level"].lower():
                continue
            if flt.get("router") and flt["router"].lower() not in parsed["router"].lower():
                continue
            if flt.get("service") and flt["service"].lower() not in parsed["service"].lower():
                continue
            matched_entries.append(parsed)

        counter: Counter[str] = Counter()
        for item in matched_entries:
            key = str(item.get(group_by) or item.get("message") or item.get("level") or "-")
            counter[key] += 1

        top_aggregates = [{"key": k, "count": c} for k, c in counter.most_common(10)]
        return {
            "source": "controller",
            "group_by": group_by,
            "total_lines_scanned": total_scanned,
            "matched_lines": len(matched_entries),
            "groups": top_aggregates,
            "top_aggregates": top_aggregates,
            "samples": matched_entries[: max(1, int(limit_samples))],
        }

    # Access logs
    for line in lines:
        parsed = parse_single_access_log_line(line)
        if not parsed:
            continue
        if flt.get("router") and flt["router"].lower() not in parsed["router"].lower():
            continue
        if flt.get("service") and flt["service"].lower() not in parsed["service"].lower():
            continue
        if flt.get("host") and flt["host"].lower() != parsed["host"].lower():
            continue
        if flt.get("path_prefix") and not parsed["path"].startswith(flt["path_prefix"]):
            continue
        if flt.get("client_ip") and flt["client_ip"] != parsed["client_ip"]:
            continue
        if flt.get("min_duration_ms") is not None and parsed["duration_ms"] < float(flt["min_duration_ms"]):
            continue
        status = int(parsed.get("status", 0))
        status_range = flt.get("status_range") or flt.get("status_class")
        if status_range:
            sc = str(status_range).lower()
            prefix_digit = int(sc[0])
            if status // 100 != prefix_digit:
                continue
        if flt.get("status") is not None:
            if status != int(flt["status"]):
                continue
        if flt.get("status_codes"):
            if status not in [int(c) for c in flt["status_codes"]]:
                continue

        matched_entries.append(parsed)

    counter = Counter()
    for item in matched_entries:
        key = str(item.get(group_by, "-"))
        counter[key] += 1

    top_aggregates = [{"key": k, "count": c} for k, c in counter.most_common(10)]
    return {
        "source": "access",
        "group_by": group_by,
        "total_lines_scanned": total_scanned,
        "matched_lines": len(matched_entries),
        "groups": top_aggregates,
        "top_aggregates": top_aggregates,
        "samples": matched_entries[: max(1, int(limit_samples))],
    }


parse_access_log_line = parse_single_access_log_line
parse_controller_log_line = parse_single_controller_log_line

