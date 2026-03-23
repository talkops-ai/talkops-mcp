"""Gateway API migration — generate HTTPRoute and Gateway manifests.

Parallels migrator_traefik.py but targets the Gateway API standard
(gateway.networking.k8s.io/v1) instead of Traefik-proprietary CRDs.
Uses the GATEWAY_API_MAPPINGS from analyzer.py to drive filter generation.
"""

from typing import Any, Dict, List, Optional, Set

import yaml as pyyaml

from traefik_mcp_server.migration_nginx.scanner import IngressInfo, ScanResult
from traefik_mcp_server.migration_nginx.analyzer import AnalysisReport, GATEWAY_API_MAPPINGS
from traefik_mcp_server.migration_nginx.migration_plan import (
    filter_ingress_for_plan,
    parse_migration_plan,
    plan_entry_for_ingress,
)
from traefik_mcp_server.migration_nginx.migrator_traefik import (
    GeneratedFile,
    _generate_shadow_traefik_service,
)


GATEWAY_API_VERSION = "gateway.networking.k8s.io/v1"

# Default namespace for the shared Gateway resource.  HTTPRoutes in other
# namespaces use cross-namespace parentRefs to attach to it.
GATEWAY_NAMESPACE = "traefik-system"

_MIGRATION_LABEL = "migration.source"


# ── Filter generators ──────────────────────────────────────────────────────────

def _ssl_redirect_filter(permanent: bool = False) -> Dict[str, Any]:
    """RequestRedirect filter for ssl-redirect / force-ssl-redirect."""
    return {
        "type": "RequestRedirect",
        "requestRedirect": {
            "scheme": "https",
            "statusCode": 301 if permanent else 302,
        },
    }


def _url_rewrite_filter(target: str) -> Dict[str, Any]:
    """URLRewrite filter for rewrite-target."""
    return {
        "type": "URLRewrite",
        "urlRewrite": {
            "path": {
                "type": "ReplacePrefixMatch",
                "replacePrefixMatch": target,
            },
        },
    }


def _permanent_redirect_filter(url: str) -> Dict[str, Any]:
    """RequestRedirect filter for permanent-redirect."""
    return {
        "type": "RequestRedirect",
        "requestRedirect": {
            "path": {
                "type": "ReplaceFullPath",
                "replaceFullPath": url,
            },
            "statusCode": 301,
        },
    }


def _temporal_redirect_filter(url: str) -> Dict[str, Any]:
    """RequestRedirect filter for temporal-redirect."""
    return {
        "type": "RequestRedirect",
        "requestRedirect": {
            "path": {
                "type": "ReplaceFullPath",
                "replaceFullPath": url,
            },
            "statusCode": 302,
        },
    }


def _cors_response_header_filter(ann: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """ResponseHeaderModifier filter for CORS headers."""
    headers: List[Dict[str, str]] = []
    mapping = {
        "cors-allow-origin": "Access-Control-Allow-Origin",
        "cors-allow-methods": "Access-Control-Allow-Methods",
        "cors-allow-headers": "Access-Control-Allow-Headers",
        "cors-allow-credentials": "Access-Control-Allow-Credentials",
        "cors-expose-headers": "Access-Control-Expose-Headers",
        "cors-max-age": "Access-Control-Max-Age",
    }
    for nginx_key, http_header in mapping.items():
        if nginx_key in ann:
            headers.append({"name": http_header, "value": ann[nginx_key]})

    if not headers:
        return None
    return {
        "type": "ResponseHeaderModifier",
        "responseHeaderModifier": {
            "set": headers,
        },
    }


def _custom_headers_filter(ann: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """RequestHeaderModifier for upstream-vhost or custom-headers (placeholder)."""
    if "upstream-vhost" in ann:
        return {
            "type": "RequestHeaderModifier",
            "requestHeaderModifier": {
                "set": [{"name": "Host", "value": ann["upstream-vhost"]}],
            },
        }
    return None


# ── HTTPRoute generation ──────────────────────────────────────────────────────

def _generate_filters(ann: Dict[str, str]) -> List[Dict[str, Any]]:
    """Build Gateway API filters from nginx annotations."""
    filters: List[Dict[str, Any]] = []

    if ann.get("force-ssl-redirect") == "true":
        filters.append(_ssl_redirect_filter(permanent=True))
    elif ann.get("ssl-redirect") == "true":
        filters.append(_ssl_redirect_filter(permanent=False))

    if target := ann.get("rewrite-target"):
        filters.append(_url_rewrite_filter(target))

    if url := ann.get("permanent-redirect"):
        filters.append(_permanent_redirect_filter(url))

    if url := ann.get("temporal-redirect"):
        filters.append(_temporal_redirect_filter(url))

    cors_filter = _cors_response_header_filter(ann)
    if ann.get("enable-cors") == "true" and cors_filter:
        filters.append(cors_filter)

    headers_filter = _custom_headers_filter(ann)
    if headers_filter:
        filters.append(headers_filter)

    return filters


def _generate_backend_refs(ing: IngressInfo, ann: Dict[str, str]) -> List[Dict[str, Any]]:
    """Build backendRefs, supporting canary weight splitting."""
    refs: List[Dict[str, Any]] = []
    is_canary = ann.get("canary") == "true"

    for path_info in ing.paths:
        ref: Dict[str, Any] = {
            "name": path_info.service_name,
            "port": path_info.service_port,
        }
        if is_canary:
            weight_str = ann.get("canary-weight", "0")
            try:
                weight = int(weight_str)
            except ValueError:
                weight = 0
            ref["weight"] = weight

        # Avoid duplicate backend refs
        if ref not in refs:
            refs.append(ref)

    return refs


def _generate_timeout_section(ann: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Build HTTPRoute timeouts from proxy timeout annotations."""
    timeouts: Dict[str, str] = {}
    if val := ann.get("proxy-read-timeout"):
        try:
            secs = int(val)
            timeouts["backendRequest"] = f"{secs}s"
        except ValueError:
            pass
    if val := ann.get("proxy-connect-timeout"):
        try:
            secs = int(val)
            timeouts["request"] = f"{secs}s"
        except ValueError:
            pass
    return timeouts if timeouts else None


def _generate_matches(ing: IngressInfo, ann: Dict[str, str]) -> List[Dict[str, Any]]:
    """Build HTTPRouteMatch entries from paths and canary header rules."""
    matches: List[Dict[str, Any]] = []

    for path_info in ing.paths:
        match: Dict[str, Any] = {}
        path_val = path_info.path or "/"
        if ann.get("use-regex") == "true":
            match["path"] = {"type": "RegularExpression", "value": path_val}
        elif path_info.path_type == "Exact":
            match["path"] = {"type": "Exact", "value": path_val}
        else:
            match["path"] = {"type": "PathPrefix", "value": path_val}

        # Canary header matching
        if header_name := ann.get("canary-by-header"):
            header_match: Dict[str, str] = {"name": header_name}
            if header_val := ann.get("canary-by-header-value"):
                header_match["value"] = header_val
                match.setdefault("headers", []).append(
                    {"type": "Exact", **header_match}
                )
            else:
                match.setdefault("headers", []).append(
                    {"type": "Exact", "name": header_name, "value": "always"}
                )

        matches.append(match)

    return matches if matches else [{"path": {"type": "PathPrefix", "value": "/"}}]


def _unsupported_annotations_comments(ann: Dict[str, str]) -> str:
    """Generate YAML comment block for unsupported/partial annotations."""
    lines: List[str] = []
    for key, value in sorted(ann.items()):
        if key in GATEWAY_API_MAPPINGS:
            status, _, note = GATEWAY_API_MAPPINGS[key]
            if status in ("unsupported", "partial"):
                lines.append(f"# NOTE ({status}): nginx/{key}={value!r} — {note}")
        else:
            lines.append(f"# WARNING: Unknown annotation nginx/{key}={value!r} — manual review required")
    return "\n".join(lines)


def generate_httproute(ing: IngressInfo) -> GeneratedFile:
    """Generate an HTTPRoute manifest for a single Ingress."""
    ann = ing.nginx_annotations
    filters = _generate_filters(ann)
    matches = _generate_matches(ing, ann)
    backend_refs = _generate_backend_refs(ing, ann)
    timeouts = _generate_timeout_section(ann)

    # Build HTTPRoute rule
    rule: Dict[str, Any] = {
        "matches": matches,
        "backendRefs": backend_refs,
    }
    if filters:
        rule["filters"] = filters
    if timeouts:
        rule["timeouts"] = timeouts

    # Build the HTTPRoute object
    httproute: Dict[str, Any] = {
        "apiVersion": GATEWAY_API_VERSION,
        "kind": "HTTPRoute",
        "metadata": {
            "name": ing.name,
            "namespace": ing.namespace,
            "labels": {_MIGRATION_LABEL: "nginx-ingress"},
        },
        "spec": {
            "parentRefs": [
                {
                    "name": "traefik-gateway",
                    "namespace": GATEWAY_NAMESPACE,
                },
            ],
            "rules": [rule],
        },
    }

    # Add hostnames if the Ingress has hosts
    if ing.hosts:
        httproute["spec"]["hostnames"] = ing.hosts

    yaml_str = pyyaml.dump(httproute, default_flow_style=False, sort_keys=False)

    # Prepend unsupported annotation comments
    comments = _unsupported_annotations_comments(ann)
    if comments:
        yaml_str = comments + "\n" + yaml_str

    key = f"{ing.namespace}-{ing.name}"
    return GeneratedFile(
        rel_path=f"02-httproutes/{key}.yaml",
        content=yaml_str,
        description=f"HTTPRoute for {ing.namespace}/{ing.name}",
        category="httproute",
    )


# ── Gateway manifest ──────────────────────────────────────────────────────────

def _generate_gateway(scan_result: ScanResult) -> GeneratedFile:
    """Generate a Gateway manifest with HTTP and HTTPS listeners."""
    # Collect all TLS secrets used across Ingresses
    tls_secrets: List[Dict[str, Any]] = []
    seen: Set[tuple] = set()
    for ing in scan_result.ingresses:
        if ing.tls_enabled:
            for secret in ing.tls_secrets:
                key = (ing.namespace, secret)
                if key not in seen:
                    seen.add(key)
                    tls_secrets.append({
                        "name": secret,
                        "namespace": ing.namespace,
                    })

    listeners: List[Dict[str, Any]] = [
        {
            "name": "http",
            "protocol": "HTTP",
            "port": 80,
            "allowedRoutes": {"namespaces": {"from": "All"}},
        },
    ]

    https_listener: Dict[str, Any] = {
        "name": "https",
        "protocol": "HTTPS",
        "port": 443,
        "allowedRoutes": {"namespaces": {"from": "All"}},
        "tls": {"mode": "Terminate"},
    }
    if tls_secrets:
        https_listener["tls"]["certificateRefs"] = [
            {"kind": "Secret", "name": s["name"], "namespace": s["namespace"]}
            for s in tls_secrets
        ]
    listeners.append(https_listener)

    gateway: Dict[str, Any] = {
        "apiVersion": GATEWAY_API_VERSION,
        "kind": "Gateway",
        "metadata": {
            "name": "traefik-gateway",
            "namespace": GATEWAY_NAMESPACE,
            "labels": {_MIGRATION_LABEL: "nginx-ingress"},
        },
        "spec": {
            "gatewayClassName": "traefik",
            "listeners": listeners,
        },
    }

    content = (
        "# Gateway resource — shared across namespaces (see HTTPRoute parentRefs).\n"
        "# HTTPRoutes in other namespaces typically need a ReferenceGrant in this\n"
        "# namespace authorizing those namespaces to attach to this Gateway.\n"
        "# Adjust gatewayClassName if not using Traefik.\n"
        + pyyaml.dump(gateway, default_flow_style=False, sort_keys=False)
    )

    return GeneratedFile(
        rel_path="03-gateway/gateway.yaml",
        content=content,
        description="Gateway resource with HTTP/HTTPS listeners",
        category="gateway",
    )


# ── Migrator ───────────────────────────────────────────────────────────────────

class GatewayAPIMigrator:
    """Generates Gateway API migration artifacts from NGINX Ingress resources."""

    def migrate(
        self,
        scan_result: ScanResult,
        analysis: Optional[AnalysisReport] = None,
        migration_plan: Optional[Dict[str, Any]] = None,
    ) -> List[GeneratedFile]:
        """Generate all migration files for a Gateway API target.

        Args:
            scan_result: Output from NginxMigrationScanner.scan()
            analysis: Optional AnalysisReport for report enrichment
            migration_plan: Optional per-Ingress overrides from the agent

        Returns:
            List of GeneratedFile objects with relative paths and YAML content.
        """
        files: List[GeneratedFile] = []
        plan = parse_migration_plan(migration_plan)

        # 1. HTTPRoutes per Ingress
        for ing in scan_result.ingresses:
            entry = plan_entry_for_ingress(plan, ing.namespace, ing.name)
            effective = (
                filter_ingress_for_plan(ing, list(entry.ignore_annotations))
                if entry.ignore_annotations
                else ing
            )
            files.append(generate_httproute(effective))

        # 1b. Shadow mode — generate TraefikService mirroring manifests
        for ing in scan_result.ingresses:
            entry = plan_entry_for_ingress(plan, ing.namespace, ing.name)
            if not entry.shadow_mode:
                continue
            shadow_file = _generate_shadow_traefik_service(
                ing, entry.shadow_mirror_percent,
            )
            files.append(shadow_file)

        # 2. Gateway resource
        files.append(_generate_gateway(scan_result))

        # 3. Verify script (simpler than Traefik — just tests hosts)
        files.append(self._generate_verify_script(scan_result))

        return files

    def _generate_verify_script(self, scan_result: ScanResult) -> GeneratedFile:
        """Generate a verification script to test Gateway API routes."""
        test_lines = []
        for ing in scan_result.ingresses:
            for host in ing.hosts:
                test_lines.append(
                    f'echo "Testing {ing.namespace}/{ing.name} → {host}"\n'
                    f'curl -s "http://{host}" -o /dev/null '
                    f'-w "HTTP %{{http_code}}\\n" || true'
                )

        tests_block = "\n\n".join(test_lines) if test_lines else 'echo "No hosts to test."'

        content = (
            "#!/bin/bash\n"
            "# Verify Gateway API HTTPRoutes are working correctly.\n"
            "set -e\n\n"
            'echo "=== Gateway API Migration Verification ==="\n'
            'echo ""\n\n'
            f"{tests_block}\n\n"
            'echo ""\n'
            'echo "If all tests pass, proceed with DNS cutover."\n'
        )

        return GeneratedFile(
            rel_path="04-verify.sh",
            content=content,
            description="Verification script for Gateway API routes",
            category="verify",
        )
