---
name: auditing-observability-security-posture
description: Audits OpenTelemetry Collectors, Instrumentation CRDs, Kubernetes RBAC ClusterRoles, and eBPF instrumentation DaemonSets for plaintext secrets, insecure TLS skips, exposed debug extensions, writable hostPath mounts, missing PII scrubbing, root containers, and excessive RBAC permissions. Use when conducting SOC 2, PCI-DSS, or CIS Kubernetes security reviews, hardening OpenTelemetry pipelines for Pod Security Admission restricted compliance, or remediating collector security findings. Do not use for pure cardinality or noise reduction without security review (use controlling-telemetry-cardinality-and-noise), Alertmanager silence/routing governance (use auditing-alertmanager-governance), Traefik ingress security audits, or Helm chart template reviews.
---

# Auditing Observability Security Posture

## Preconditions

- Read `otel://server/capabilities` and `otel://cluster/contexts` to check active toolsets, target cluster context, Kubernetes API connectivity, and whether cluster mutations (`allow_write`) are enabled.
- Execute all cluster discovery, security audits, and remediations exclusively via OpenTelemetry MCP resources and tools—do not invoke raw `kubectl` CLI commands when MCP is connected.
- Enforce zero-secret hygiene (`hooks/secret-safety.py`): never read `.env` files, never dump Kubernetes `Secret` payloads (`kubectl get secret -o yaml`), and never pass inline plaintext passwords, API keys, or bearer tokens in tool arguments—always reference `${env:VAR_NAME}` backed by Kubernetes `secretKeyRef`.

## Security Audit & Hardening Workflow Checklist

- [ ] **Step 1 — Execute Cluster or Namespace Security Audit**:
  - Call `otel_audit_security_posture` (`namespace`, `scope=["collectors", "instrumentation", "ebpf", "rbac"]`) to evaluate all `OpenTelemetryCollector` CRs, `Instrumentation` CRs, `ClusterRole` RBAC policies, and eBPF DaemonSets (`obi` / `beyla`).
  - Inspect returned `SEC_*` findings (`SEC_INLINE_SECRET`, `SEC_INSECURE_EXPORTER`, `SEC_TLS_SKIP_VERIFY`, `SEC_PII_REDACTION_MISSING`, `SEC_OVERPRIVILEGED_RBAC`, `SEC_PRIVILEGED_CONTAINER`).
- [ ] **Step 2 — Generate Compliance Markdown Report**:
  - Save the JSON output from `otel_audit_security_posture` to a file and run `scripts/render_audit_report.py --input audit.json` to render a structured compliance markdown report with remediation priorities.
  - Consult `references/collector-security-hardening.md` and `references/ebpf-least-privilege-capabilities.md` for remediation blueprints.
- [ ] **Step 3 — Remediate Secrets, TLS & PII Scrubbing (`dry_run=True`)**:
  - Replace inline credentials (`SEC_INLINE_SECRET`) with `${env:OTEL_EXPORTER_AUTH_TOKEN}` backed by Kubernetes Secrets via `otel_patch_collector` (`dry_run=True`).
  - Enable TLS certificate verification (`SEC_TLS_SKIP_VERIFY`) via `otel_patch_collector`, and remediate PII/header leaks (`SEC_PII_REDACTION_MISSING`) in a **single combined `otel_configure_processing` call** covering both traces and logs: `otel_configure_processing(namespace=..., collector_name=..., signals=["traces", "logs"], rules={"mask_pii": ["email", "credit_card", "ssn", "jwt", "bearer_token"], "drop_attributes": ["http.request.header.authorization", "http.request.header.cookie", "http.response.header.set_cookie"]}, dry_run=True)` before applying with `dry_run=False`.
  - `[GATE]` Present the security remediation diff and secret migration plan to the user for approval before mutating cluster resources.
- [ ] **Step 4 — Apply Hardening & Re-Run Security Audit**:
  - Apply approved changes with `dry_run=False` and re-run `otel_audit_security_posture` to confirm `findings` is empty and `risk_level: "low"`.

## Reference & Script Inventory

- `references/collector-security-hardening.md` — Hardening guide for secret externalization (`${env:...}`), mTLS/TLS verification, receiver authentication (`oidc`/`bearertokenauth`), and non-root pod security contexts.
- `references/ebpf-least-privilege-capabilities.md` — Linux capability matrix (`BPF`, `PERFMON`, `SYS_PTRACE`) and RBAC least-privilege rules for eBPF agents and collectors.
- `scripts/render_audit_report.py` — Offline report generator that transforms `otel_audit_security_posture` JSON output into an executive compliance table.
