#!/usr/bin/env python3
"""Offline classifier for nginx.ingress.kubernetes.io/* annotations on Traefik v3.6+."""

import argparse
import json
import re
import sys

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None


NGINX_PREFIX = "nginx.ingress.kubernetes.io/"

TIER_1_NATIVE = {
    "rewrite-target",
    "use-regex",
    "app-root",
    "ssl-redirect",
    "force-ssl-redirect",
    "permanent-redirect",
    "permanent-redirect-code",
    "temporal-redirect",
    "temporal-redirect-code",
    "preserve-trailing-slash",
    "auth-type",
    "auth-secret",
    "auth-secret-type",
    "auth-realm",
    "auth-url",
    "auth-method",
    "auth-signin",
    "auth-signin-redirect-param",
    "auth-response-headers",
    "auth-tls-secret",
    "auth-tls-verify-client",
    "auth-tls-verify-depth",
    "auth-tls-pass-certificate-to-upstream",
    "enable-cors",
    "cors-allow-origin",
    "cors-allow-methods",
    "cors-allow-headers",
    "cors-expose-headers",
    "cors-allow-credentials",
    "cors-max-age",
    "affinity",
    "session-cookie-name",
    "session-cookie-path",
    "session-cookie-domain",
    "session-cookie-samesite",
    "session-cookie-secure",
    "session-cookie-max-age",
    "session-cookie-expires",
    "canary",
    "canary-by-header",
    "canary-by-header-value",
    "canary-by-header-pattern",
    "canary-by-cookie",
    "canary-weight",
    "canary-weight-total",
    "limit-rps",
    "limit-rpm",
    "limit-burst-multiplier",
    "limit-connections",
    "limit-whitelist",
    "whitelist-source-range",
    "backend-protocol",
    "proxy-connect-timeout",
    "proxy-read-timeout",
    "proxy-send-timeout",
    "proxy-body-size",
    "proxy-buffering",
    "proxy-ssl-secret",
    "proxy-ssl-verify",
    "proxy-ssl-name",
    "proxy-ssl-server-name",
    "upstream-vhost",
    "custom-headers",
    "x-forwarded-prefix",
}

TIER_2_CAVEAT = {
    "use-regex": "Traefik v3 uses Go RE2 regular expressions; verify no PCRE lookaheads/lookbehinds are used.",
    "limit-rps": "Evaluated per Traefik replica via token bucket.",
    "limit-rpm": "Evaluated per Traefik replica via token bucket.",
    "proxy-body-size": "Mapped to buffering.maxRequestBodyBytes when > 0 (0 = unlimited).",
}

TIER_3_REPLACEMENTS = {
    "configuration-snippet": "Convert to native Traefik Middleware via traefik_configure_middleware (headers / replace_path_regex / ip_allow_list).",
    "server-snippet": "Convert to native Traefik Middleware or TLSOption via traefik_configure_middleware / traefik_configure_tls_policy.",
    "auth-snippet": "Convert to forward_auth Middleware via traefik_configure_middleware(type='forward_auth').",
    "modsecurity-snippet": "Use Traefik Coraza WAF plugin Middleware via traefik_configure_middleware(type='plugin').",
    "enable-modsecurity": "Use Traefik Coraza WAF plugin Middleware via traefik_configure_middleware(type='plugin').",
    "stream-snippet": "Convert to IngressRouteTCP via traefik_configure_tcp_udp_route(protocol='tcp').",
}


def _extract_annotations_stdlib(raw_text: str) -> dict[str, str]:
    text = raw_text.strip()
    if text.startswith("{"):
        obj = json.loads(text)
        if "metadata" in obj and isinstance(obj["metadata"], dict):
            return {str(k): str(v) for k, v in (obj["metadata"].get("annotations") or {}).items()}
        return {str(k): str(v) for k, v in obj.items()}

    anns: dict[str, str] = {}
    in_anns = False
    anns_indent = -1
    lines = raw_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if re.match(r"^annotations:\s*$", stripped):
            in_anns = True
            anns_indent = indent
            i += 1
            continue
        if in_anns:
            if indent <= anns_indent:
                in_anns = False
                continue
            m = re.match(r'^["\']?([^"\':\s]+)["\']?\s*:\s*(.*)$', stripped)
            if m:
                k, v = m.group(1), m.group(2).strip()
                if v in ("|", "|-", ">", ">-"):
                    block_lines = []
                    i += 1
                    while i < len(lines):
                        bline = lines[i]
                        if bline.strip() and (len(bline) - len(bline.lstrip(" "))) <= indent:
                            break
                        block_lines.append(bline.strip())
                        i += 1
                    anns[k] = "\n".join(block_lines).strip()
                    continue
                anns[k] = v.strip("'\"")
        i += 1
    return anns


def classify_annotations(annotations: dict[str, str]) -> dict:
    tier_1 = []
    tier_2 = []
    tier_3 = []

    for full_key, val in (annotations or {}).items():
        if not full_key.startswith(NGINX_PREFIX):
            continue
        short_key = full_key[len(NGINX_PREFIX) :].lower()
        if short_key in TIER_1_NATIVE:
            tier_1.append({"annotation": full_key, "value": str(val), "action": "keep_in_place_on_ingress"})
            if short_key in TIER_2_CAVEAT:
                tier_2.append({
                    "annotation": full_key,
                    "value": str(val),
                    "caveat": TIER_2_CAVEAT[short_key],
                })
        else:
            tier_3.append({
                "annotation": full_key,
                "value": str(val),
                "remediation": TIER_3_REPLACEMENTS.get(
                    short_key,
                    "Annotation not natively supported by kubernetesIngressNGINX; replace with a Traefik Middleware or IngressRoute CRD.",
                ),
            })

    return {
        "ready_for_in_place_provider": len(tier_3) == 0,
        "tier_1_native_count": len(tier_1),
        "tier_2_caveat_count": len(tier_2),
        "tier_3_unsupported_count": len(tier_3),
        "tier_1_native": tier_1,
        "tier_2_caveats": tier_2,
        "tier_3_unsupported": tier_3,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify nginx.ingress.kubernetes.io/* annotations for Traefik v3.6+ kubernetesIngressNGINX adoption."
    )
    parser.add_argument("--ingress-file", default=None, help="Path to Kubernetes Ingress YAML file")
    parser.add_argument(
        "--annotations-json",
        default='{"nginx.ingress.kubernetes.io/rewrite-target": "/$1", "nginx.ingress.kubernetes.io/use-regex": "true", "nginx.ingress.kubernetes.io/ssl-redirect": "true"}',
        help="JSON dictionary of Ingress annotations",
    )
    args = parser.parse_args()

    if args.ingress_file:
        with open(args.ingress_file, "r", encoding="utf-8") as fh:
            raw_content = fh.read()
        if yaml is not None:
            doc = yaml.safe_load(raw_content) or {}
            anns = (doc.get("metadata") or {}).get("annotations") or {}
        else:
            anns = _extract_annotations_stdlib(raw_content)
    else:
        anns = json.loads(args.annotations_json)

    sys.stdout.write(json.dumps(classify_annotations(anns), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
