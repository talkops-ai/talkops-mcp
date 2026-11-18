---
name: troubleshooting-traefik-routing
description: Diagnoses and remediates Traefik v3 routing failures, 404/421/429/500/502/503/504 HTTP errors, TLS SAN/handshake mismatches, shadowed rules, cross-namespace middleware/ExternalName blocks, empty canary endpoints, GitOps drift hazards, access/controller log anomalies, and Kubernetes Gateway API status condition errors. Use when debugging broken IngressRoutes, HTTPRoutes, Gateways, 4xx/5xx error spikes, 30s upstream gateway timeouts, or parsing Traefik access logs. Do not use for greenfield canary/blue-green onboarding (use managing-traefik-traffic-routing), proactive 20-check cluster security posture scoring (use auditing-traefik-security-posture), NGINX Ingress migration planning (use adopting-traefik-nginx-ingress-provider), or Grafana Loki LogQL application log queries (use triaging-loki-incidents-and-errors).
---

# Troubleshooting Traefik v3 Routing & Gateway API

This skill provides a deterministic, symptom-driven triage workflow across Kubernetes CRDs, Traefik's live runtime API, EndpointSlices, X.509 certificates, Prometheus metrics, and access/controller logs. Always use MCP resources and tools rather than raw `kubectl`.

## Preconditions

1. Read `traefik://server/capabilities`, `traefik://cluster/contexts`, and `traefik://runtime/health` to inspect `cluster_connected`, `runtime_api_reachable`, `prometheus.reachable`, `allow_write`, active kubeconfig context, and router/service/middleware runtime errors.
2. Read `traefik://instance/static-config` when checking provider flags (`allowCrossNamespace`, `allowExternalNameServices`, `ingressClass`) or static entryPoints.
3. Read `traefik://routes/{namespace}` and `traefik://manifests/{kind}/{namespace}/{name}` (or `traefik://gateway/{namespace}` for Gateway API `Gateway`/`HTTPRoute` resources) to inspect manifests and ownership metadata (`ARGO_ROLLOUT_MANAGED`, `GITOPS_MANAGED`) without running `kubectl get ... -o yaml`.

## Execution Checklist

- [ ] **Step 1 — Check runtime health, context & route inventory**: Read `traefik://server/capabilities`, `traefik://cluster/contexts`, `traefik://runtime/health`, and `traefik://routes/{namespace}` (or `traefik://gateway/{namespace}`), plus `traefik://manifests/{kind}/{namespace}/{name}` for the failing route.
- [ ] **Step 2 — Run deep N-to-1 route diagnosis (`traefik_diagnose_route`)**: Call `traefik_diagnose_route(name=..., kind=..., namespace=..., include=["runtime", "endpoints", "tls", "metrics", "events"], detail="full")` and consult [traefik-error-catalog.md](references/traefik-error-catalog.md) and [symptom-decision-trees.md](references/symptom-decision-trees.md).
- [ ] **Step 3 — Trace request matching & correlate logs/metrics**:
  - Call `traefik_trace_request` on the failing URL/Host/Path to detect `PRIORITY_SHADOWED` or rule mismatches.
  - Call `traefik_analyze_logs(source="access"|"controller", ...)` AND **always call `traefik_compare_traffic_metrics(..., scope="service", include_backend_split=True)`** (plus `traefik://metrics/{namespace}/{service}/summary`) whenever troubleshooting `503` / `5xx` error rates or weighted `TraefikService` backend splits!
  - When given exported JSON/CLF access log lines to aggregate and redact, execute [parse_access_log.py](scripts/parse_access_log.py) (`--log-file` or `--lines`):
    ```bash
    python3 .agents/skills/troubleshooting-traefik-routing/scripts/parse_access_log.py --group-by router --lines '<jsonl>'
    ```
- [ ] **Step 4 — Check ownership & boundary guardrails before remediating**:
  - **Gateway API Read-Only Boundary**: Consult [gateway-api-diagnostics.md](references/gateway-api-diagnostics.md). Gateway API (`Gateway`, `HTTPRoute`, `GRPCRoute`, `ReferenceGrant`) is **strictly read-and-diagnose only** in Traefik MCP—never attempt to mutate Gateway API CRDs via `traefik_*` write tools; output declarative `gateway.networking.k8s.io` YAML for GitOps instead.
  - **GitOps Drift Warning (`GITOPS_MANAGED`)**: When `argocd.argoproj.io/tracking-id` (or Flux metadata) is present, warn explicitly that ArgoCD `selfHeal: true` will revert imperative `traefik_update_route` hotfixes within seconds unless committed to Git (or `selfHeal` is temporarily paused); provide **both** the `dry_run=True` preview and the Git YAML diff.
  - **Argo Rollouts & GitOps Ownership Check (`ARGO_ROLLOUT_MANAGED` / `GITOPS_MANAGED`)**: Before shifting weights on any `TraefikService` (such as mitigating `WEIGHT_TO_EMPTY_BACKEND` 503s to `100/0`), **always** inspect `traefik_diagnose_route(kind="TraefikService", ...)` and `traefik://manifests/TraefikService/{namespace}/{name}` and explicitly state in your response whether `ARGO_ROLLOUT_MANAGED` or `GITOPS_MANAGED` ownership is present—if `ARGO_ROLLOUT_MANAGED`, delegate to `argo_manage_rollout_lifecycle(action="abort")`; if standalone, shift weights via `traefik_set_traffic_weights(..., dry_run=True -> False)`.
- [ ] **Step 5 — `[GATE]` Always generate a `dry_run=True` remediation preview & apply when requested**:
  - **Mandatory Remediation Preview**: For every non-Gateway-API CRD defect diagnosed (`PRIORITY_SHADOWED`, `MIDDLEWARE_MISSING` / `MIDDLEWARE_RUNTIME_ERROR`, `BACKEND_PORT_MISMATCH`, `WEIGHT_TO_EMPTY_BACKEND`, `ROUTE_IGNORED_BY_PROVIDER`, `504` timeout), **always execute a `dry_run=True` tool call** (`traefik_update_route`, `traefik_set_traffic_weights`, `traefik_configure_middleware`, `traefik_configure_servers_transport`, or `traefik_configure_http_route`) even when the operator only asked "why" it is failing, so your root-cause report includes a server-validated diff!
  - If the operator explicitly asked to fix or mitigate a non-GitOps/non-Rollout route live, proceed immediately in the same turn from `dry_run=True` to `dry_run=False` and re-run `traefik_diagnose_route` to verify recovery; format incident notes per [incident-summary-template.md](references/incident-summary-template.md).

## Symptom Quick-Reference

- **`404` on valid path**: `PRIORITY_SHADOWED` (longer regex/header rule has higher `len(match)` priority -> set explicit `priority` via `traefik_update_route`), `ROUTE_IGNORED_BY_PROVIDER` (`kubernetes.io/ingress.class` mismatch vs `traefik://instance/static-config`), or `stripPrefix` over-stripping.
- **`421 Misdirected Request` / TLS alert**: HTTP/2 connection coalescing across hosts with `TLS_SAN_MISMATCH` or distinct `TLSOption` (`clientAuth` / `sniStrict`)—inspect `traefik://certificates/{namespace}` and align SANs/`TLSOption`.
- **`500` with zero backend logs**: In `traefik_analyze_logs(source="access")`, `ServiceName == "-"` and `Duration < 1ms` prove a Traefik middleware fault (`MIDDLEWARE_MISSING`, `MIDDLEWARE_RUNTIME_ERROR`, `MIDDLEWARE_CHAIN_CYCLE`, `MIDDLEWARE_CROSS_NAMESPACE_BLOCKED` when `allowCrossNamespace: false`).
- **`502 Bad Gateway`**: `BACKEND_PORT_MISMATCH` (wrong Service port) or HTTP/1.1 vs `scheme: "h2c"` gRPC mismatch.
- **`503 Service Unavailable`**: `NO_READY_ENDPOINTS`, `WEIGHT_TO_EMPTY_BACKEND` (partial 503% matching canary weight!), or `EXTERNALNAME_NOT_ALLOWED` (`allowExternalNameServices: false`—route to in-cluster Service instead of weakening cluster-wide flags).
- **`504 Gateway Timeout` at exactly `30.0s`**: Matches `ServersTransport.spec.forwardingTimeouts.responseHeaderTimeout` (`30s` default)—create a route-scoped `ServersTransport` (`response_header: "60s"`) rather than raising global entryPoint timeouts.

## Reference Documentation

- [Traefik Error & Diagnosis Code Catalog (All 41 Codes)](references/traefik-error-catalog.md)
- [Symptom Decision Trees (404, 421, 429, 500, 502, 503, 504, TLS)](references/symptom-decision-trees.md)
- [Kubernetes Gateway API Read & Diagnose Playbook](references/gateway-api-diagnostics.md)
- [Incident Summary Template](references/incident-summary-template.md)
