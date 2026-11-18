"""Traefik v3 match rule compiler, v2-to-v3 syntax linter, priority calculator, and static request evaluator."""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from traefik_mcp_server.exceptions.custom import TraefikRouteConfigError
from traefik_mcp_server.models.schemas import RouteMatch

# Legacy Traefik v2 matchers removed or changed in v3
_V2_LEGACY_PATTERNS: List[Tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bHeaders\s*\("),
        "Traefik v2 matcher 'Headers(...)' was renamed to 'Header(...)' in Traefik v3.",
        "Header(",
    ),
    (
        re.compile(r"\bHeadersRegexp\s*\("),
        "Traefik v2 matcher 'HeadersRegexp(...)' was renamed to 'HeaderRegexp(...)' in Traefik v3.",
        "HeaderRegexp(",
    ),
    (
        re.compile(r"\bHostHeader\s*\("),
        "Traefik v2 matcher 'HostHeader(...)' was removed in Traefik v3; use 'Host(...)'.",
        "Host(",
    ),
    (
        re.compile(r"\bPathStrip\s*\(|\bPathPrefixStrip\s*\("),
        "PathStrip/PathPrefixStrip matchers were removed; use PathPrefix(...) + a stripPrefix Middleware.",
        "PathPrefix(",
    ),
    (
        re.compile(r"\b(?:Host|Path|PathPrefix|Method|Headers?)\s*:\s*\S+"),
        "Traefik v1/v2 colon syntax (e.g. 'Host:example.com') is invalid in v3; use function syntax Host(`example.com`).",
        "",
    ),
    (
        re.compile(r"\bHost\s*\(\s*`[^`]+`\s*,\s*`[^`]+`"),
        "Traefik v3 matchers accept a single argument; join multiple with ||: (Host(`a`) || Host(`b`)).",
        "",
    ),
    (
        re.compile(r"\bPathPrefix\s*\(\s*`[^`]+`\s*,\s*`[^`]+`"),
        "Traefik v3 matchers accept a single argument; join multiple with ||: (PathPrefix(`a`) || PathPrefix(`b`)).",
        "",
    ),
    (
        re.compile(r"\{[a-zA-Z0-9_]+:[^}]+\}"),
        "Traefik v2 curly-brace regex syntax '{name:pattern}' was removed in v3; use Go RE2 in HostRegexp/PathRegexp.",
        "",
    ),
    (
        re.compile(r"\bQuery\s*\(\s*`[^`]*=[^`]*`\s*\)"),
        "Traefik v2 single-argument Query(`key=value`) syntax changed in v3 to two arguments: Query(`key`, `value`).",
        "",
    ),
]

_VALID_HTTP_MATCHERS = {
    "Host",
    "HostRegexp",
    "Path",
    "PathPrefix",
    "PathRegexp",
    "Method",
    "Header",
    "HeaderRegexp",
    "Query",
    "QueryRegexp",
    "ClientIP",
}

_VALID_TCP_MATCHERS = {
    "HostSNI",
    "HostSNIRegexp",
    "ClientIP",
    "ALPN",
}


def lint_v3_rule(rule: str, protocol: str = "http") -> Tuple[bool, List[str], Optional[str]]:
    """Validate a Traefik v3 rule expression and detect v2 syntax issues.

    Returns:
        (is_valid, issues, suggested_fix)
    """
    issues: List[str] = []
    if not rule or not rule.strip():
        return False, ["Rule expression cannot be empty."], None

    text = rule.strip()
    suggested = text

    # Check balanced parentheses and backticks
    if text.count("(") != text.count(")"):
        issues.append("Unbalanced parentheses '(' and ')' in match rule.")
    if text.count("`") % 2 != 0:
        issues.append("Unbalanced backticks '`' in match rule.")

    # Check v2 patterns
    for pattern, msg, replacement in _V2_LEGACY_PATTERNS:
        if pattern.search(text):
            issues.append(msg)
            if replacement:
                suggested = pattern.sub(replacement, suggested)

    # Convert multi-arg Host(`a`, `b`) in suggested fix
    multi_host = re.compile(r"\b(Host|PathPrefix|Path|HostSNI)\s*\(\s*(`[^`]+`(?:\s*,\s*`[^`]+`)+)\s*\)")
    for m in multi_host.finditer(suggested):
        fn_name = m.group(1)
        args = [a.strip() for a in m.group(2).split(",") if a.strip()]
        joined = "(" + " || ".join(f"{fn_name}({a})" for a in args) + ")"
        suggested = suggested.replace(m.group(0), joined)

    # Check function identifiers outside backtick string literals
    text_outside_ticks = re.sub(r"`[^`]*`", "``", text)
    fn_calls = re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*\(", text_outside_ticks)
    allowed = _VALID_TCP_MATCHERS if protocol.lower() == "tcp" else _VALID_HTTP_MATCHERS
    for fn in fn_calls:
        if fn not in allowed:
            if not any(fn in pat_msg for _, pat_msg, _ in _V2_LEGACY_PATTERNS):
                issues.append(
                    f"Unknown {protocol.upper()} matcher '{fn}(...)'. "
                    f"Valid Traefik v3 {protocol.upper()} matchers: {', '.join(sorted(allowed))}."
                )

    if not fn_calls and not issues:
        issues.append("Rule does not contain any valid Traefik v3 matcher function calls.")

    return (len(issues) == 0, issues, suggested if suggested != text else None)


def compile_route_match(
    match: Union[RouteMatch, str, Dict[str, Any]],
    protocol: str = "http",
) -> str:
    """Compile a RouteMatch model, dict, or raw string into a validated Traefik v3 rule expression."""
    if isinstance(match, str):
        valid, issues, suggestion = lint_v3_rule(match, protocol=protocol)
        if not valid:
            hint = f" Suggested v3 rule: {suggestion}" if suggestion else ""
            raise TraefikRouteConfigError(f"Invalid Traefik v3 match rule '{match}': {'; '.join(issues)}{hint}")
        return match.strip()

    if isinstance(match, dict):
        # TCP shorthand dict: {'sni': [...], 'client_ips': [...]}
        if protocol.lower() == "tcp" and ("sni" in match or "host_sni" in match):
            snis = match.get("sni") or match.get("host_sni") or ["*"]
            if isinstance(snis, str):
                snis = [snis]
            sni_clauses = [f"HostSNI(`{s}`)" for s in snis]
            clauses = [sni_clauses[0] if len(sni_clauses) == 1 else "(" + " || ".join(sni_clauses) + ")"]
            cips = match.get("client_ips") or []
            if cips:
                cip_clauses = [f"ClientIP(`{ip}`)" for ip in cips]
                clauses.append(cip_clauses[0] if len(cip_clauses) == 1 else "(" + " || ".join(cip_clauses) + ")")
            compiled_tcp = " && ".join(clauses)
            valid, issues, _ = lint_v3_rule(compiled_tcp, protocol="tcp")
            if not valid:
                raise TraefikRouteConfigError(f"Invalid TCP match rule: {'; '.join(issues)}")
            return compiled_tcp
        match_obj = RouteMatch.model_validate(match)
    else:
        match_obj = match

    raw_hosts = match_obj.hosts or getattr(match_obj, "host", None)
    if isinstance(raw_hosts, str):
        raw_hosts = [raw_hosts]
    raw_cookies = getattr(match_obj, "cookies", None)
    raw_client_ips = match_obj.client_ips or getattr(match_obj, "client_ip", None)
    if isinstance(raw_client_ips, str):
        raw_client_ips = [raw_client_ips]

    has_structured = any([
        raw_hosts,
        match_obj.path_prefix,
        match_obj.path,
        match_obj.path_regexp,
        match_obj.methods,
        match_obj.headers,
        match_obj.header_regexps,
        raw_cookies,
        match_obj.query,
        raw_client_ips,
    ])
    if match_obj.raw and has_structured:
        raise TraefikRouteConfigError(
            "RouteMatch.raw is mutually exclusive with structured fields (hosts, path_prefix, headers, etc.)."
        )
    if match_obj.raw:
        return compile_route_match(match_obj.raw, protocol=protocol)

    clauses: List[str] = []

    if raw_hosts:
        cleaned_hosts = [h.strip() for h in raw_hosts if h and h.strip()]
        if len(cleaned_hosts) == 1:
            clauses.append(f"Host(`{cleaned_hosts[0]}`)")
        elif len(cleaned_hosts) > 1:
            clauses.append("(" + " || ".join(f"Host(`{h}`)" for h in cleaned_hosts) + ")")

    if match_obj.path:
        clauses.append(f"Path(`{match_obj.path.strip()}`)")
    if match_obj.path_prefix:
        clauses.append(f"PathPrefix(`{match_obj.path_prefix.strip()}`)")
    if match_obj.path_regexp:
        clauses.append(f"PathRegexp(`{match_obj.path_regexp.strip()}`)")

    if match_obj.methods:
        m_clauses = [f"Method(`{m.strip().upper()}`)" for m in match_obj.methods if m and m.strip()]
        if len(m_clauses) == 1:
            clauses.append(m_clauses[0])
        elif len(m_clauses) > 1:
            clauses.append("(" + " || ".join(m_clauses) + ")")

    if match_obj.headers:
        for k, v in match_obj.headers.items():
            clauses.append(f"Header(`{k.strip()}`, `{v}`)")

    if match_obj.header_regexps:
        for k, pattern in match_obj.header_regexps.items():
            clauses.append(f"HeaderRegexp(`{k.strip()}`, `{pattern}`)")

    if raw_cookies and isinstance(raw_cookies, dict):
        for ck, cv in raw_cookies.items():
            clauses.append(f"HeaderRegexp(`Cookie`, `(?:^|;\\s*){ck.strip()}={cv}(?:;|$)`)")

    if match_obj.query:
        for k, v in match_obj.query.items():
            clauses.append(f"Query(`{k.strip()}`, `{v}`)")

    if raw_client_ips:
        ip_clauses = [f"ClientIP(`{ip.strip()}`)" for ip in raw_client_ips if ip and ip.strip()]
        if len(ip_clauses) == 1:
            clauses.append(ip_clauses[0])
        elif len(ip_clauses) > 1:
            clauses.append("(" + " || ".join(ip_clauses) + ")")

    if not clauses:
        raise TraefikRouteConfigError(
            "RouteMatch must specify at least one matching condition (e.g. hosts, path_prefix, or raw)."
        )

    compiled = " && ".join(clauses)
    valid, issues, _ = lint_v3_rule(compiled, protocol=protocol)
    if not valid:
        raise TraefikRouteConfigError(f"Compiled rule failed validation: {'; '.join(issues)}")
    return compiled


def compute_default_priority(rule: str, explicit_priority: Optional[int] = None) -> int:
    """Compute effective router priority in Traefik v3 (defaults to character length of the rule)."""
    if explicit_priority is not None and int(explicit_priority) > 0:
        return int(explicit_priority)
    return len(rule.strip())


def extract_hosts_from_rule(rule: str) -> List[str]:
    """Extract all Host(`...`) and HostSNI(`...`) hostnames from a rule string."""
    if not rule:
        return []
    hosts = re.findall(r"\b(?:Host|HostSNI)\s*\(\s*`([^`]+)`\s*\)", rule)
    return list(dict.fromkeys(h.strip() for h in hosts if h.strip()))


def _eval_single_atom(atom: str, req: Dict[str, Any]) -> Tuple[bool, str]:
    """Evaluate a single atomic matcher call against request fields."""
    atom = atom.strip()
    negated = False
    while atom.startswith("!"):
        negated = not negated
        atom = atom[1:].strip()

    m = re.match(r"^([A-Za-z]+)\s*\((.*)\)$", atom, re.DOTALL)
    if not m:
        return True, atom

    fn = m.group(1)
    args = re.findall(r"`([^`]*)`", m.group(2))

    host = (req.get("host") or "").lower().split(":")[0]
    sni = (req.get("sni") or host or "").lower()
    path = req.get("path") or "/"
    method = (req.get("method") or "GET").upper()
    headers = {str(k).lower(): str(v) for k, v in (req.get("headers") or {}).items()}
    query = {str(k): str(v) for k, v in (req.get("query") or {}).items()}
    client_ip = req.get("client_ip")

    result = False
    if fn == "Host" and args:
        result = any(host == a.lower() for a in args)
    elif fn == "HostRegexp" and args:
        result = any(bool(re.search(a, host, re.I)) for a in args)
    elif fn == "HostSNI" and args:
        result = any(a == "*" or sni == a.lower() for a in args)
    elif fn == "HostSNIRegexp" and args:
        result = any(bool(re.search(a, sni, re.I)) for a in args)
    elif fn == "Path" and args:
        result = any(path == a for a in args)
    elif fn == "PathPrefix" and args:
        result = any(path.startswith(a) for a in args)
    elif fn == "PathRegexp" and args:
        result = any(bool(re.search(a, path)) for a in args)
    elif fn == "Method" and args:
        result = any(method == a.upper() for a in args)
    elif fn == "Header" and len(args) >= 2:
        hdr_val = headers.get(args[0].lower())
        result = hdr_val == args[1]
    elif fn == "HeaderRegexp" and len(args) >= 2:
        hdr_val = headers.get(args[0].lower(), "")
        result = bool(re.search(args[1], hdr_val))
    elif fn == "Query" and args:
        if len(args) >= 2:
            result = query.get(args[0]) == args[1]
        elif "=" in args[0]:
            qk, qv = args[0].split("=", 1)
            result = query.get(qk) == qv
        else:
            result = args[0] in query
    elif fn == "ClientIP" and args:
        if not client_ip:
            result = False
        else:
            try:
                ip_obj = ipaddress.ip_address(client_ip)
                result = any(
                    ip_obj in ipaddress.ip_network(a, strict=False)
                    for a in args
                )
            except ValueError:
                result = False
    else:
        result = True

    if negated:
        result = not result
    return result, f"{'!' if negated else ''}{fn}({', '.join(f'`{a}`' for a in args)})"


def evaluate_rule_against_request(
    rule: str,
    request: Dict[str, Any],
) -> Tuple[bool, List[str], List[str]]:
    """Evaluate a Traefik v3 match rule against a request dictionary.

    Returns:
        (overall_matched, matched_clauses, failed_clauses)
    """
    if not rule or not rule.strip():
        return False, [], ["<empty rule>"]

    # Extract top-level AND clauses while respecting parentheses around OR groups
    matched_clauses: List[str] = []
    failed_clauses: List[str] = []

    # Split top-level &&
    parts: List[str] = []
    depth = 0
    in_tick = False
    buf: List[str] = []
    i = 0
    text = rule.strip()
    while i < len(text):
        ch = text[i]
        if ch == "`":
            in_tick = not in_tick
            buf.append(ch)
        elif not in_tick and ch == "(":
            depth += 1
            buf.append(ch)
        elif not in_tick and ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif not in_tick and depth == 0 and text[i : i + 2] == "&&":
            parts.append("".join(buf).strip())
            buf = []
            i += 2
            continue
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())

    for part in parts:
        clause = part.strip()
        while clause.startswith("(") and clause.endswith(")"):
            # Strip outer parens ONLY if they wrap the entire clause end-to-end
            inner = clause[1:-1]
            p_depth = 0
            in_t = False
            wraps_all = True
            for ch_idx, ch_c in enumerate(inner):
                if ch_c == "`":
                    in_t = not in_t
                elif not in_t and ch_c == "(":
                    p_depth += 1
                elif not in_t and ch_c == ")":
                    p_depth -= 1
                    if p_depth < 0:
                        wraps_all = False
                        break
            if wraps_all and p_depth == 0:
                clause = inner.strip()
            else:
                break

        # Handle || inside clause
        if "||" in clause:
            or_subclauses = [s.strip() for s in re.split(r"\|\|", clause) if s.strip()]
            any_ok = False
            for sub in or_subclauses:
                ok, _ = _eval_single_atom(sub, request)
                if ok:
                    any_ok = True
                    break
            if any_ok:
                matched_clauses.append(part.strip())
            else:
                failed_clauses.append(part.strip())
        else:
            ok, label = _eval_single_atom(clause, request)
            if ok:
                matched_clauses.append(label)
            else:
                failed_clauses.append(label)

    overall = len(failed_clauses) == 0 and len(matched_clauses) > 0
    return overall, matched_clauses, failed_clauses
