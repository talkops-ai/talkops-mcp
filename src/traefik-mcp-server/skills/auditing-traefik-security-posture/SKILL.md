---
name: auditing-traefik-security-posture
description: Audits Traefik v3 static and dynamic Kubernetes configuration across 20 deterministic security, TLS, reliability, hygiene, v3-migration, and Gateway API checks, renders scored Markdown compliance reports, and executes preview-first remediations. Use when running cluster-wide or namespace Traefik security posture reviews, SOC2/CIS compliance assessments, orphaned Middleware/TLSOption/TraefikService hygiene cleanups, legacy traefik.containo.us v2-to-v3 audits, or formatting executive posture score reports. Do not use for targeted single-route mTLS setup (use securing-traefik-tls-and-certificates), live 502/503/504 incident debugging (use troubleshooting-traefik-routing), OpenTelemetry Collector/eBPF RBAC security audits (use auditing-observability-security-posture), or pre-install Helm chart security reviews (use reviewing-helm-release-security).
---

# Auditing Traefik v3 Security & Configuration Posture

This skill runs the 20 deterministic audit checks in `traefik_audit_configuration` (`SEC-001..005`, `TLS-001..006`, `REL-001..002`, `HYG-001..004`, `V3M-001..002`, `GW-001`), renders executive Markdown reports, and orchestrates preview-first remediations. Never read `tls.key` private keys or shell out to raw `kubectl` when MCP resources/tools cover the task.

## Preconditions

1. Read `traefik://server/capabilities`, `traefik://cluster/contexts`, and `traefik://runtime/health` to verify `cluster_connected`, `allow_write`, active kubeconfig context, installed CRDs (`traefik.io`, `gateway.networking.k8s.io`, `legacy_containo_us_present`), and runtime router/middleware health.
2. Read `traefik://instance/static-config` to inspect controller startup posture (`api.insecure`, `entryPoints.*.forwardedHeaders.insecure`, `providers.kubernetesCRD.allowCrossNamespace`, `allowExternalNameServices`).
3. Read `traefik://routes/{namespace}`, `traefik://policies/{namespace}`, `traefik://certificates/{namespace}`, `traefik://gateway/{namespace}` (or `_all`), and `traefik://manifests/{kind}/{namespace}/{name}` when verifying resource references and manifests before mutating or deleting.

## Execution Checklist

- [ ] **Step 1 — Read capabilities, context, runtime health & static config**: Read `traefik://server/capabilities`, `traefik://cluster/contexts`, `traefik://runtime/health`, and `traefik://instance/static-config`.
- [ ] **Step 2 — Run deterministic audit (`traefik_audit_configuration`)**: Call `traefik_audit_configuration(namespaces=..., categories=..., min_severity="low", max_findings=100)` and consult [hardening-checklist.md](references/hardening-checklist.md) and [audit-report-template.md](references/audit-report-template.md).
- [ ] **Step 3 — Render executive Markdown report**: Whenever generating or formatting an executive posture report (including from raw `AuditReport` JSON), execute [render_audit_report.py](scripts/render_audit_report.py):
  ```bash
  python3 .agents/skills/auditing-traefik-security-posture/scripts/render_audit_report.py --report-json '<audit_json>'
  ```
- [ ] **Step 4 — Preview remediations (`dry_run=True`) & verify references**:
  - Before deleting orphaned hygiene resources (`HYG-001` `Middleware`, `HYG-002` non-`default` `TLSOption`, `HYG-003` `TraefikService`), verify `referenced_by` is empty in `traefik://routes/{namespace}` and `traefik://policies/{namespace}` (and never delete a `TLSOption` or `TLSStore` named `default`).
  - Respect the **Gateway API Read-Only Boundary** (`GW-001`): never attempt to mutate `Gateway`, `HTTPRoute`, or `ReferenceGrant` CRDs via `traefik_*` write tools—inspect `traefik://gateway/{namespace}` + `traefik_diagnose_route(kind="HTTPRoute", ...)` and output declarative `ReferenceGrant` / `Gateway` YAML for GitOps.
- [ ] **Step 5 — `[GATE]` Apply requested remediations & re-verify**:
  - When the operator asked for an audit/plan only (or static-config Helm `values.yaml` fixes for `SEC-001..004` / v2-to-v3 migration plans), present the prioritized plan and YAML diffs.
  - When the operator explicitly asked to remediate dynamic CRD findings or delete verified orphaned resources live, run `dry_run=True` first, **proceed immediately in the same turn** to `dry_run=False` (and `confirm=True` for `traefik_delete_resource`), and re-run `traefik_audit_configuration` to confirm posture score improvement!

## Remediation Playbook by Check Family

Consult [hardening-checklist.md](references/hardening-checklist.md) for all 20 check IDs. **Architectural Explanation Rule**: Whenever remediating a finding, always explain **why** the misconfiguration is dangerous in your response before/alongside the fix:

- **`SEC-001`..`SEC-004` (Static Config)**: Set `api.insecure: false` (expose `api@internal` only via an authenticated `IngressRoute` with `forwardAuth` or secret-backed `basicAuth`), `entryPoints.*.forwardedHeaders.insecure: false` with explicit LB `trustedIPs` (preventing `X-Forwarded-For` spoofing), `providers.kubernetesCRD.allowCrossNamespace: false`, and `allowExternalNameServices: false`.
- **`SEC-005` (Wildcard `*` CORS + `accessControlAllowCredentials: true`)**: Explain explicitly why pairing `accessControlAllowOriginList: ["*"]` with `accessControlAllowCredentials: true` is an insecure CORS posture (credentialed origin reflection / exposing authenticated responses across untrusted origins), then replace `"*"` with explicit origin allowlists via `traefik_configure_middleware(..., type="headers", dry_run=True -> False)`.
- **`TLS-001` / `TLS-002` (Legacy TLS 1.0/1.1 or weak CBC/3DES/RSA ciphers)**: Enforce `VersionTLS12`+ AEAD ECDHE (`intermediate`) or `VersionTLS13` (`modern`) via `traefik_configure_tls_policy(kind="TLSOption", ..., dry_run=True -> False)`.
- **`TLS-003` (`insecureSkipVerify: true` on `ServersTransport`)**: Set `insecure_skip_verify: False` + `root_cas: ["<ca-secret>"]` via `traefik_configure_servers_transport(..., dry_run=True -> False)`.
- **`TLS-004` (HTTP route missing HTTPS redirect / missing HSTS)**: Create `redirect_scheme` (`scheme: "https"`, `permanent: True`) via `traefik_configure_middleware` and attach via `traefik_update_route(..., dry_run=True -> False)`.
- **`TLS-005` / `TLS-006` (Expiring/expired cert or `TRAEFIK DEFAULT CERT`)**: Inspect `traefik://certificates/{namespace}` (never `tls.key`!), check `cert-manager` renewal or rotate `tls.secret_name` via `traefik_update_route` + `traefik_diagnose_route(..., include=["tls"])`.
- **`REL-001` (`retry.attempts > 4`) & `REL-002` (Weighted `TraefikService` missing `healthCheck`)**: Explain explicitly how `retry.attempts > 4` causes **retry amplification and cascading failure storms** across the attached backend service (citing the concrete route/backend service name, e.g., `frontend-proxy`) and its downstream microservices during latency spikes or partial outages, then cap `attempts <= 3` via `traefik_configure_middleware(..., type="retry")` and add `health_check={"path": "/", "interval": "10s", "timeout": "3s"}` via `traefik_configure_weighted_service(..., dry_run=True -> False)`.
- **`HYG-001`..`HYG-003` (Orphaned `Middleware`, `TLSOption`, `TraefikService`)**: Delete via `traefik_delete_resource(..., confirm=True)` after confirming zero references.
- **`HYG-004` (Duplicate match rule + priority collision)**: Set distinct explicit `priority` via `traefik_update_route(..., dry_run=True -> False)` and confirm deterministic winner via `traefik_trace_request`.
- **`V3M-001` / `V3M-002` (`traefik.containo.us/v1alpha1` & v2 `Host(a, b)` / `Headers` / `ipWhiteList`)**: Migrate to `traefik.io/v1alpha1`, v3 `(Host(\`a\`) || Host(\`b\`)) && Header(...)`, and `ipAllowList` (`dry_run=True -> False`) before retiring legacy v2 objects.

## Reference Documentation

- [Hardening Checklist (All 20 Check IDs)](references/hardening-checklist.md)
- [Audit Report Markdown Template](references/audit-report-template.md)
