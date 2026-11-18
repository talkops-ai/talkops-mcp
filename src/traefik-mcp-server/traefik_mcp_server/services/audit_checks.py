"""Deterministic security, TLS, reliability, hygiene, v3-migration, and Gateway API audit checks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from traefik_mcp_server.models.schemas import AuditFinding, AuditReport
from traefik_mcp_server.services.rule_engine import compute_default_priority, lint_v3_rule

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_DEDUCTION = {"low": 2, "medium": 5, "high": 12, "critical": 25}

ALL_AUDIT_CHECK_IDS: tuple[str, ...] = (
    "SEC-001",
    "SEC-002",
    "SEC-003",
    "SEC-004",
    "SEC-005",
    "TLS-001",
    "TLS-002",
    "TLS-003",
    "TLS-004",
    "TLS-005",
    "TLS-006",
    "REL-001",
    "REL-002",
    "HYG-001",
    "HYG-002",
    "HYG-003",
    "HYG-004",
    "V3M-001",
    "V3M-002",
    "GW-001",
)


def run_configuration_audit(
    *,
    static_config: Dict[str, Any],
    routes: List[Dict[str, Any]],
    policies: List[Dict[str, Any]],
    certificates: List[Dict[str, Any]],
    gateways: List[Dict[str, Any]],
    existing_services: set[tuple[str, str]],
    has_legacy_containo_crds: bool = False,
    cert_expiry_warning_days: int = 21,
    categories: Optional[Sequence[str]] = None,
    min_severity: str = "low",
    max_findings: int = 50,
) -> Dict[str, Any]:
    """Execute Traefik configuration audit checks across the requested categories."""
    active_cats = set(
        categories
        or ("security", "tls", "reliability", "hygiene", "v3_migration", "gateway_api")
    )
    min_sev_rank = SEVERITY_ORDER.get(min_severity.lower(), 1)
    findings: List[AuditFinding] = []

    def _add(finding: AuditFinding) -> None:
        if finding.category not in active_cats:
            return
        if SEVERITY_ORDER.get(finding.severity, 1) < min_sev_rank:
            return
        if not finding.check_id:
            finding.check_id = finding.id
        findings.append(finding)

    # Index middlewares by (ns, name) -> policy entry
    mw_by_key: Dict[tuple[str, str], Dict[str, Any]] = {}
    for pol in policies:
        if pol.get("kind") in ("Middleware", "MiddlewareTCP"):
            mw_by_key[(pol.get("namespace", "default"), pol.get("name", ""))] = pol

    # ── 1. SECURITY CHECKS ─────────────────────────────────────────────────────
    api_cfg = static_config.get("api") or {}
    if api_cfg.get("insecure") is True:
        _add(
            AuditFinding(
                id="SEC-001",
                severity="critical",
                category="security",
                title="Traefik API and Dashboard exposed with api.insecure=true",
                evidence="Static configuration has api.insecure=true, exposing /api/* and /dashboard without authentication.",
                resource_uri="traefik://instance/static-config",
                remediation_tool="traefik_configure_middleware",
                skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
            )
        )

    for ep_name, ep_cfg in (static_config.get("entryPoints") or {}).items():
        if not isinstance(ep_cfg, dict):
            continue
        fh = ep_cfg.get("forwardedHeaders") or {}
        if fh.get("insecure") is True:
            _add(
                AuditFinding(
                    id="SEC-002",
                    severity="high",
                    category="security",
                    title=f"EntryPoint '{ep_name}' trusts all X-Forwarded-* headers (forwardedHeaders.insecure=true)",
                    evidence=f"entryPoints.{ep_name}.forwardedHeaders.insecure=true allows client IP spoofing.",
                    resource_uri="traefik://instance/static-config",
                    remediation_tool=None,
                    skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
                )
            )

    for pol in policies:
        p_spec = pol.get("spec") or {}
        ns = pol.get("namespace", "default")
        name = pol.get("name", "")
        if pol.get("kind") in ("Middleware", "MiddlewareTCP") and (pol.get("type") == "ipAllowList" or "ipAllowList" in p_spec):
            ranges = (p_spec.get("ipAllowList") or {}).get("sourceRange") or []
            if "0.0.0.0/0" in ranges or "::/0" in ranges:
                _add(
                    AuditFinding(
                        id="SEC-003",
                        severity="high",
                        category="security",
                        title=f"ipAllowList '{ns}/{name}' permits 0.0.0.0/0 or ::/0",
                        evidence=f"sourceRange={ranges} allows unrestricted internet traffic.",
                        resource_uri=f"traefik://manifests/{pol.get('kind')}/{ns}/{name}",
                        remediation_tool="traefik_configure_middleware",
                        skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
                    )
                )
        if pol.get("kind") == "Middleware" and "headers" in p_spec:
            hdr_s = p_spec.get("headers") or {}
            origins = hdr_s.get("accessControlAllowOriginList") or []
            if "*" in origins and hdr_s.get("accessControlAllowCredentials") is True:
                _add(
                    AuditFinding(
                        id="SEC-005",
                        severity="high",
                        category="security",
                        title=f"Middleware '{ns}/{name}' combines wildcard CORS origin '*' with allowCredentials=true",
                        evidence="accessControlAllowOriginList=['*'] with accessControlAllowCredentials=true is insecure.",
                        resource_uri=f"traefik://manifests/Middleware/{ns}/{name}",
                        remediation_tool="traefik_configure_middleware",
                        skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
                    )
                )
        if pol.get("kind") == "Middleware" and "retry" in p_spec:
            att = int((p_spec.get("retry") or {}).get("attempts", 1))
            if att > 4:
                _add(
                    AuditFinding(
                        id="REL-001",
                        severity="medium",
                        category="reliability",
                        title=f"Retry Middleware '{ns}/{name}' has excessive attempts ({att} > 4)",
                        evidence=f"retry.attempts={att} can cause retry amplification storms.",
                        resource_uri=f"traefik://manifests/Middleware/{ns}/{name}",
                        remediation_tool="traefik_configure_middleware",
                        skill_reference="skills/configuring-traefik-middlewares/references/rate-limit-and-circuit-breaker-tuning.md",
                    )
                )

    prov_crd = (static_config.get("providers") or {}).get("kubernetesCRD") or {}
    if prov_crd.get("allowCrossNamespace") is True:
        _add(
            AuditFinding(
                id="SEC-003",
                severity="medium",
                category="security",
                title="Cross-namespace CRD references enabled (allowCrossNamespace=true)",
                evidence="providers.kubernetesCRD.allowCrossNamespace=true.",
                resource_uri="traefik://instance/static-config",
                remediation_tool=None,
                skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
            )
        )
    if prov_crd.get("allowExternalNameServices") is True:
        _add(
            AuditFinding(
                id="SEC-004",
                severity="medium",
                category="security",
                title="ExternalName Services enabled (allowExternalNameServices=true)",
                evidence="providers.kubernetesCRD.allowExternalNameServices=true.",
                resource_uri="traefik://instance/static-config",
                remediation_tool=None,
                skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
            )
        )
    if prov_crd.get("allowCrossNamespace") is True or prov_crd.get("allowExternalNameServices") is True:
        _add(
            AuditFinding(
                id="SEC-005",
                severity="medium",
                category="security",
                title="Permissive kubernetesCRD provider flags enabled",
                evidence=(
                    f"allowCrossNamespace={prov_crd.get('allowCrossNamespace', False)}, "
                    f"allowExternalNameServices={prov_crd.get('allowExternalNameServices', False)}"
                ),
                resource_uri="traefik://instance/static-config",
                remediation_tool=None,
                skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
            )
        )

    # ── 2. TLS & ROUTE CHECKS ──────────────────────────────────────────────────
    eps = static_config.get("entryPoints") or {}
    web_ep = eps.get("web") or {}
    if web_ep and not ((web_ep.get("http") or {}).get("redirections")):
        _add(
            AuditFinding(
                id="TLS-002",
                severity="medium",
                category="tls",
                title="HTTP 'web' entryPoint has no permanent HTTPS redirection",
                evidence="entryPoints.web.http.redirections is not configured.",
                resource_uri="traefik://instance/static-config",
                remediation_tool="traefik_configure_middleware",
                skill_reference="skills/securing-traefik-tls-and-certificates/references/tls-option-baselines.md",
            )
        )

    for pol in policies:
        ns = pol.get("namespace", "default")
        name = pol.get("name", "")
        if pol.get("kind") == "TLSOption":
            t_spec = pol.get("spec") or {}
            min_v = t_spec.get("minVersion", "")
            if min_v in ("VersionTLS10", "VersionTLS11"):
                _add(
                    AuditFinding(
                        id="TLS-001",
                        severity="high",
                        category="tls",
                        title=f"TLSOption '{ns}/{name}' permits legacy {min_v}",
                        evidence=f"spec.minVersion='{min_v}' is below the TLS 1.2 production baseline.",
                        resource_uri=f"traefik://manifests/TLSOption/{ns}/{name}",
                        remediation_tool="traefik_configure_tls_policy",
                        skill_reference="skills/securing-traefik-tls-and-certificates/references/tls-option-baselines.md",
                    )
                )
            ciphers = t_spec.get("cipherSuites") or []
            if any("CBC" in c or "3DES" in c or "RC4" in c or c.startswith("TLS_RSA_") for c in ciphers):
                _add(
                    AuditFinding(
                        id="TLS-002",
                        severity="medium",
                        category="tls",
                        title=f"TLSOption '{ns}/{name}' includes weak cipher suites",
                        evidence=f"Weak cipher suites found in {ciphers}.",
                        resource_uri=f"traefik://manifests/TLSOption/{ns}/{name}",
                        remediation_tool="traefik_configure_tls_policy",
                        skill_reference="skills/securing-traefik-tls-and-certificates/references/tls-option-baselines.md",
                    )
                )
        if pol.get("kind") in ("ServersTransport", "ServersTransportTCP"):
            spec = pol.get("spec") or {}
            insec = spec.get("insecureSkipVerify") or (spec.get("tls") or {}).get("insecureSkipVerify")
            if insec is True:
                _add(
                    AuditFinding(
                        id="TLS-003",
                        severity="high",
                        category="tls",
                        title=f"{pol.get('kind')} '{ns}/{name}' disables backend TLS verification (insecureSkipVerify=true)",
                        evidence="insecureSkipVerify=true exposes backend connections to MITM attacks.",
                        resource_uri=f"traefik://manifests/{pol.get('kind')}/{ns}/{name}",
                        remediation_tool="traefik_configure_servers_transport",
                        skill_reference="skills/configuring-traefik-middlewares/references/servers-transport-and-healthchecks.md",
                    )
                )

    for cert in certificates:
        ns = cert.get("namespace", "default")
        sec_name = cert.get("secret_name") or cert.get("name") or "tls-secret"
        days = cert.get("days_remaining")
        if cert.get("is_traefik_default_cert"):
            _add(
                AuditFinding(
                    id="TLS-006",
                    severity="medium",
                    category="tls",
                    title=f"TLS Secret '{ns}/{sec_name}' uses Traefik self-signed default certificate",
                    evidence="Certificate issuer/subject is TRAEFIK DEFAULT CERT.",
                    resource_uri=f"traefik://certificates/{ns}",
                    remediation_tool="traefik_update_route",
                    skill_reference="skills/securing-traefik-tls-and-certificates/references/cert-rotation-runbook.md",
                )
            )
        if cert.get("expired") or (days is not None and days <= 0):
            _add(
                AuditFinding(
                    id="TLS-005",
                    severity="critical",
                    category="tls",
                    title=f"TLS Certificate '{ns}/{sec_name}' has expired",
                    evidence=f"notAfter={cert.get('not_after')}, days_remaining={days}.",
                    resource_uri=f"traefik://certificates/{ns}",
                    remediation_tool="traefik_update_route",
                    skill_reference="skills/securing-traefik-tls-and-certificates/references/cert-rotation-runbook.md",
                )
            )
        elif days is not None and days <= cert_expiry_warning_days:
            _add(
                AuditFinding(
                    id="TLS-005",
                    severity="high",
                    category="tls",
                    title=f"TLS Certificate '{ns}/{sec_name}' expires in {days} days",
                    evidence=f"notAfter={cert.get('not_after')} (threshold={cert_expiry_warning_days}d).",
                    resource_uri=f"traefik://certificates/{ns}",
                    remediation_tool="traefik_update_route",
                    skill_reference="skills/securing-traefik-tls-and-certificates/references/cert-rotation-runbook.md",
                )
            )

    # Route-level checks
    seen_rule_priorities: Dict[tuple[str, str, int], str] = {}

    for rt in routes:
        r_kind = rt.get("kind", "IngressRoute")
        r_name = rt.get("name", "")
        r_ns = rt.get("namespace", "default")
        r_eps = rt.get("entryPoints") or rt.get("entry_points") or []
        has_tls = bool(rt.get("tls"))
        mws = list(rt.get("middlewares") or [])

        # Extract rules & backends from either list_routes format or nested rules format
        rule_entries: List[tuple[str, Optional[int]]] = []
        backends = list(rt.get("backends") or [])
        has_nested_rules = bool(rt.get("rules"))
        for r_item in rt.get("rules") or []:
            if isinstance(r_item, dict):
                if r_item.get("match"):
                    rule_entries.append((r_item["match"], r_item.get("priority")))
                if not rt.get("middlewares"):
                    mws.extend(r_item.get("middlewares") or [])
                if not rt.get("backends"):
                    backends.extend(r_item.get("services") or [])
        if not has_nested_rules:
            for rm in rt.get("rules_match") or []:
                rule_entries.append((rm, rt.get("priority")))

        if r_kind == "TraefikService":
            w_svcs = (((rt.get("spec") or {}).get("weighted") or {}).get("services")) or []
            backends.extend(w_svcs)
            if rt.get("referenced_by_count") == 0 and not (rt.get("referenced_by") or []):
                _add(
                    AuditFinding(
                        id="HYG-003",
                        severity="low",
                        category="hygiene",
                        title=f"Unused TraefikService '{r_ns}/{r_name}' (0 route references)",
                        evidence=f"TraefikService '{r_ns}/{r_name}' is not referenced by any IngressRoute.",
                        resource_uri=f"traefik://routes/{r_ns}",
                        remediation_tool="traefik_delete_resource",
                        skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
                    )
                )

        if "containo.us" in str(rt.get("api_version") or rt.get("apiVersion") or ""):
            _add(
                AuditFinding(
                    id="V3M-001",
                    severity="high",
                    category="v3_migration",
                    title=f"{r_kind} '{r_ns}/{r_name}' uses legacy traefik.containo.us API group",
                    evidence=f"apiVersion='{rt.get('api_version') or rt.get('apiVersion')}'",
                    resource_uri=f"traefik://manifests/{r_kind}/{r_ns}/{r_name}",
                    remediation_tool="traefik_configure_http_route",
                    skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
                )
            )

        mw_types = set()
        has_hsts = False
        for mw_ref in mws:
            mw_n = mw_ref.get("name") if isinstance(mw_ref, dict) else str(mw_ref)
            mw_ns = (mw_ref.get("namespace") if isinstance(mw_ref, dict) else None) or r_ns
            pol_obj = mw_by_key.get((mw_ns, mw_n))
            if pol_obj:
                mw_types.add(pol_obj.get("type", ""))
                hdr_spec = (pol_obj.get("spec") or {}).get("headers") or {}
                if hdr_spec.get("stsSeconds", 0) > 0:
                    has_hsts = True

        if r_kind == "IngressRoute":
            if ("websecure" in r_eps or "web" in r_eps) and not has_tls:
                _add(
                    AuditFinding(
                        id="TLS-004",
                        severity="medium",
                        category="tls",
                        title=f"IngressRoute '{r_ns}/{r_name}' has no TLS configuration",
                        evidence=f"entryPoints={r_eps} without spec.tls.",
                        resource_uri=f"traefik://manifests/IngressRoute/{r_ns}/{r_name}",
                        remediation_tool="traefik_update_route",
                        skill_reference="skills/securing-traefik-tls-and-certificates/references/tls-option-baselines.md",
                    )
                )
            if ("websecure" in r_eps or "web" in r_eps) and not ({"rateLimit", "inFlightReq"} & mw_types):
                _add(
                    AuditFinding(
                        id="SEC-004",
                        severity="medium",
                        category="security",
                        title=f"IngressRoute '{r_ns}/{r_name}' has no rateLimit or inFlightReq middleware",
                        evidence="Route does not attach rate limiting.",
                        resource_uri=f"traefik://manifests/IngressRoute/{r_ns}/{r_name}",
                        remediation_tool="traefik_update_route",
                        skill_reference="skills/configuring-traefik-middlewares/references/rate-limit-and-circuit-breaker-tuning.md",
                    )
                )
            if "websecure" in r_eps and has_tls and not has_hsts:
                _add(
                    AuditFinding(
                        id="TLS-004",
                        severity="medium",
                        category="tls",
                        title=f"HTTPS IngressRoute '{r_ns}/{r_name}' does not enforce HSTS headers",
                        evidence="No attached 'headers' middleware sets stsSeconds > 0.",
                        resource_uri=f"traefik://manifests/IngressRoute/{r_ns}/{r_name}",
                        remediation_tool="traefik_configure_middleware",
                        skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
                    )
                )

        # Check rules for v2 syntax and duplicate rule+priority
        for rule_str, explicit_prio in rule_entries:
            valid_v3, v3_issues, _ = lint_v3_rule(rule_str, protocol="tcp" if "TCP" in r_kind else "http")
            if not valid_v3:
                _add(
                    AuditFinding(
                        id="V3M-002",
                        severity="high",
                        category="v3_migration",
                        title=f"{r_kind} '{r_ns}/{r_name}' contains invalid or legacy v2 match rule syntax",
                        evidence=f"Rule '{rule_str}': {'; '.join(v3_issues)}",
                        resource_uri=f"traefik://manifests/{r_kind}/{r_ns}/{r_name}",
                        remediation_tool="traefik_configure_http_route",
                        skill_reference="skills/managing-traefik-traffic-routing/references/v3-rule-syntax-and-priority.md",
                    )
                )
            prio = compute_default_priority(rule_str, explicit_prio if explicit_prio is not None else rt.get("priority"))
            for ep in r_eps or ["default"]:
                key = (ep, rule_str, prio)
                if key in seen_rule_priorities and seen_rule_priorities[key] != f"{r_ns}/{r_name}":
                    _add(
                        AuditFinding(
                            id="HYG-004",
                            severity="medium",
                            category="hygiene",
                            title=f"Duplicate match rule and priority ({prio}) between '{r_ns}/{r_name}' and '{seen_rule_priorities[key]}'",
                            evidence=f"entryPoint='{ep}', rule='{rule_str}', priority={prio}",
                            resource_uri=f"traefik://manifests/{r_kind}/{r_ns}/{r_name}",
                            remediation_tool="traefik_update_route",
                            skill_reference="skills/managing-traefik-traffic-routing/references/v3-rule-syntax-and-priority.md",
                        )
                    )
                else:
                    seen_rule_priorities[key] = f"{r_ns}/{r_name}"

        # Check backends for missing Services & missing healthChecks on weighted routes
        is_weighted = len(backends) > 1 or any(b.get("weight") is not None for b in backends)
        for b in backends:
            b_kind = b.get("kind", "Service")
            b_name = b.get("name", "")
            b_ns = b.get("namespace") or r_ns
            if b_kind == "Service" and (b_ns, b_name) not in existing_services:
                _add(
                    AuditFinding(
                        id="HYG-003",
                        severity="low",
                        category="hygiene",
                        title=f"{r_kind} '{r_ns}/{r_name}' targets missing Service '{b_ns}/{b_name}'",
                        evidence=f"Kubernetes Service '{b_ns}/{b_name}' was not found.",
                        resource_uri=f"traefik://manifests/{r_kind}/{r_ns}/{r_name}",
                        remediation_tool="traefik_diagnose_route",
                        skill_reference="skills/troubleshooting-traefik-routing/references/traefik-error-catalog.md",
                    )
                )
            has_ts_hc_ann = bool((rt.get("annotations") or {}).get("talkops.io/health-check"))
            if is_weighted and not b.get("healthCheck") and not b.get("health_check") and not has_ts_hc_ann:
                _add(
                    AuditFinding(
                        id="REL-002",
                        severity="low",
                        category="reliability",
                        title=f"Weighted backend '{b_name}' on '{r_ns}/{r_name}' has no active healthCheck",
                        evidence="Weighted canary/blue-green backends without healthCheck will not emit traefik_service_server_up or eject failing pods early.",
                        resource_uri=f"traefik://manifests/{r_kind}/{r_ns}/{r_name}",
                        remediation_tool="traefik_configure_weighted_service",
                        skill_reference="skills/configuring-traefik-middlewares/references/servers-transport-and-healthchecks.md",
                    )
                )

    for pol in policies:
        if pol.get("kind") == "TLSStore" and pol.get("name") == "default":
            continue
        if pol.get("kind") == "TLSOption" and pol.get("name") == "default":
            continue
        refs = pol.get("referenced_by") or []
        ref_count = pol.get("referenced_by_count", len(refs))
        if ref_count == 0 and not refs:
            ns = pol.get("namespace", "default")
            name = pol.get("name", "")
            chk_id = "HYG-002" if pol.get("kind") == "TLSOption" else "HYG-001"
            _add(
                AuditFinding(
                    id=chk_id,
                    severity="low",
                    category="hygiene",
                    title=f"Unused {pol.get('kind')} '{ns}/{name}' (0 route references)",
                    evidence=f"{pol.get('kind')} '{ns}/{name}' is not referenced by any route or chain.",
                    resource_uri=f"traefik://policies/{ns}",
                    remediation_tool="traefik_delete_resource",
                    skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
                )
            )

    provs = static_config.get("providers") or {}
    k8s_ing = provs.get("kubernetesIngress") or {}
    nginx_ing = provs.get("kubernetesIngressNGINX") or {}
    if k8s_ing.get("enabled") and nginx_ing.get("enabled"):
        if k8s_ing.get("ingressClass") == nginx_ing.get("ingressClass") and k8s_ing.get("ingressClass"):
            _add(
                AuditFinding(
                    id="HYG-004",
                    severity="high",
                    category="hygiene",
                    title="Overlapping kubernetesIngress and kubernetesIngressNGINX providers watch the same ingressClass",
                    evidence=f"Both providers target ingressClass='{k8s_ing.get('ingressClass')}', causing standard Ingress parsing to shadow NGINX annotations.",
                    resource_uri="traefik://instance/static-config",
                    remediation_tool=None,
                    skill_reference="skills/adopting-traefik-nginx-ingress-provider/references/provider-configuration-and-coexistence.md",
                )
            )

    if has_legacy_containo_crds:
        _add(
            AuditFinding(
                id="V3M-002",
                severity="high",
                category="v3_migration",
                title="Legacy 'traefik.containo.us' CRDs detected in cluster",
                evidence="Deprecated Traefik v2 CRDs (traefik.containo.us/v1alpha1) coexist with traefik.io/v1alpha1.",
                resource_uri="traefik://server/capabilities",
                remediation_tool=None,
                skill_reference="skills/auditing-traefik-security-posture/references/hardening-checklist.md",
            )
        )

    for gw in gateways:
        gw_ns = gw.get("namespace", "default")
        gw_name = gw.get("name", "")
        if gw.get("accepted") is False or gw.get("programmed") is False or gw.get("resolved_refs") is False:
            _add(
                AuditFinding(
                    id="GW-001",
                    severity="high",
                    category="gateway_api",
                    title=f"Gateway API {gw.get('kind', 'Gateway')} '{gw_ns}/{gw_name}' is not Accepted/Programmed",
                    evidence=f"accepted={gw.get('accepted')}, programmed={gw.get('programmed')}, resolved_refs={gw.get('resolved_refs')}",
                    resource_uri=f"traefik://gateway/{gw_ns}",
                    remediation_tool="traefik_diagnose_route",
                    skill_reference="skills/troubleshooting-traefik-routing/references/gateway-api-diagnostics.md",
                )
            )

    # Sort findings by severity descending, then ID
    findings.sort(key=lambda f: (-SEVERITY_ORDER.get(f.severity, 1), f.id))
    trimmed = findings[: max(1, int(max_findings))]

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    deduction = 0
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
        deduction += SEVERITY_DEDUCTION.get(f.severity, 2)

    score = max(0, 100 - deduction)
    summary = (
        f"Audit posture score: {score}/100 across {len(findings)} finding(s) "
        f"(critical={counts['critical']}, high={counts['high']}, medium={counts['medium']}, low={counts['low']})."
    )
    report = AuditReport(
        score=score,
        summary=summary,
        counts=counts,
        counts_by_severity=counts,
        findings=trimmed,
    )
    return report.model_dump()
