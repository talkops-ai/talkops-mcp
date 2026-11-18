---
name: adopting-traefik-nginx-ingress-provider
description: Adopts and operates Traefik v3.6+'s built-in kubernetesIngressNGINX provider to serve existing Kubernetes Ingress manifests carrying nginx.ingress.kubernetes.io/* annotations without rewriting them into CRDs, while converting Tier-3 snippet/Lua/WAF annotations into native Traefik v3 CRDs. Use when retiring ingress-nginx, verifying Traefik v3.6+ compatibility, classifying nginx.ingress.kubernetes.io/* annotations into Tier 1/2/3, resolving mixed NGINX/Traefik annotation conflicts, or executing zero-downtime side-by-side ingress-nginx cutovers and DNS rollbacks. Do not use for greenfield native IngressRoute/TraefikService canary setups (use managing-traefik-traffic-routing), pure Traefik middleware tuning (use configuring-traefik-middlewares), Deployment-to-Argo-Rollout migrations (use onboarding-and-migrating-to-argo-rollouts), or cluster-wide security posture scoring (use auditing-traefik-security-posture).
---

# Adopting Traefik's Built-In NGINX Ingress Provider (`kubernetesIngressNGINX`)

Traefik v3.6+ includes a native **`providers.kubernetesIngressNGINX`** compatibility provider that watches standard `networking.k8s.io/v1` `Ingress` objects (`ingressClassName: nginx`) and reconciles `nginx.ingress.kubernetes.io/*` annotations in-place without YAML rewrites for ~85% of standard `ingress-nginx` workloads. Never shell out to `kubectl` when MCP resources or tools cover the operation.

## Preconditions

1. Read `traefik://server/capabilities` and `traefik://instance/static-config` to verify:
   - Controller version is **`>= 3.6.0`**. **Hard Version Gate**: `providers.kubernetesIngressNGINX` was introduced in **Traefik v3.6.0**—if a target cluster runs `< 3.6.0` (e.g., `v3.4.x` or `v3.5.x`), **halt and refuse** applying `kubernetesIngressNGINX` flags until Traefik is upgraded to `>= 3.6.0` (or convert the `Ingress` to native `IngressRoute`).
   - `providers.kubernetesIngressNGINX.enabled` status and `ingressClass` isolation from `providers.kubernetesIngress`.
2. Read `traefik://routes/{namespace}`, `traefik://certificates/{namespace}` (to confirm any TLS or `auth-tls-secret` CA `Secret` exists in the namespace without reading private keys), and `traefik://manifests/Ingress/{namespace}/{name}` (instead of `kubectl get ingress -o yaml`) to inspect live `Ingress` manifests and `nginx.ingress.kubernetes.io/*` annotations.

## Execution Checklist

- [ ] **Step 1 — Verify Traefik `>= 3.6.0`, provider isolation & TLS/CA Secrets**: Read `traefik://server/capabilities`, `traefik://instance/static-config`, `traefik://routes/{namespace}`, `traefik://certificates/{namespace}`, and `traefik://manifests/Ingress/{namespace}/{name}`.
- [ ] **Step 2 — Consult references & run deterministic annotation classifier**: Read [annotation-support-matrix.md](references/annotation-support-matrix.md) and execute [classify_nginx_annotations.py](scripts/classify_nginx_annotations.py) on the target annotations:
  ```bash
  python3 .agents/skills/adopting-traefik-nginx-ingress-provider/scripts/classify_nginx_annotations.py --annotations-json '<json>'
  ```
- [ ] **Step 3 — Enforce Tier 1 / Tier 2 / Tier 3 rules & provider isolation**:
  - **Coexistence Guard (`INGRESS_PROVIDER_CONFLICT`)**: Never mix `nginx.ingress.kubernetes.io/*` and `traefik.ingress.kubernetes.io/*` annotations on the same `Ingress` object!
  - **Tier 1 Native**: Leave untouched on `Ingress` (`rewrite-target`, `ssl-redirect`, `auth-url`, `auth-signin-redirect-param` [case-insensitive], `auth-tls-verify-client`, `auth-tls-secret`, `backend-protocol`, `enable-cors`, `canary`, `canary-weight`, `canary-by-header`, `canary-by-cookie`). When `auth-tls-secret` or `backend-protocol: "HTTPS"` is used, report the verified `Secret` metadata from `traefik://certificates/{namespace}` and run `traefik_diagnose_route(kind="Ingress", name=..., namespace=..., include=["tls", "runtime", "endpoints"])` + `traefik_trace_request` to confirm live runtime mTLS, router claiming, and backend port/endpoint binding!
  - **Tier 2 Behavioral Caveats**: Flag Go RE2 vs PCRE regex differences (Go RE2 rejects PCRE lookaheads like `(?!...)`), per-replica `limit-rps` token buckets (`burst = rps * multiplier`), and `proxy-body-size: "0"` (unlimited body size).
  - **Tier 3 Unsupported (`ready_for_in_place_provider: false`)**: Never silently drop security/WAF/TCP/tracing annotations (`configuration-snippet`, `server-snippet`, `stream-snippet`, `enable-modsecurity`, `lua-resty-*`, `opentracing-*`)! Map `lua-resty-*` / `enable-modsecurity` to a Coraza WAF `plugin` middleware, map `opentracing-*` to Traefik v3 static OpenTelemetry OTLP tracing (`tracing.otlp.grpc.endpoint`, citing the cluster's collector endpoint such as `opentelemetry-otel-collector:4317`), and preview native Traefik v3 CRD replacements (`traefik_configure_middleware`, `traefik_configure_tls_policy`, `traefik_configure_http_route`, `traefik_configure_tcp_udp_route`) with `dry_run=True`.
- [ ] **Step 4 — `[GATE]` Apply or hold safely**:
  - If `< 3.6.0` blocker, `allow_write: false`, or an unregistered WAF plugin (which requires static Helm registration first), stop after the `dry_run=True` preview and present the migration plan.
  - When migrating `stream-snippet` TCP proxies to `IngressRouteTCP` (after confirming the static TCP `entryPoint` exists in `traefik://instance/static-config`) or replacing Tier-3 HTTP snippets with native CRDs (`Middleware`, `TLSOption`, `IngressRoute`), **proceed immediately in the same turn** from `dry_run=True` to `dry_run=False` and validate with `traefik_diagnose_route`!
- [ ] **Step 5 — Runtime claiming verification, side-by-side cutover & instant DNS rollback**: Follow [provider-configuration-and-coexistence.md](references/provider-configuration-and-coexistence.md) and [cutover-and-rollback-runbook.md](references/cutover-and-rollback-runbook.md)—for every Tier-1 in-place `Ingress` migration check, **always** run **both** `traefik_diagnose_route(kind="Ingress", name=..., namespace=..., include=["tls", "runtime", "endpoints"])` **and** `traefik_trace_request(request={"url": "https://<host>/..."})` to prove runtime route claiming and backend target resolution; during cutover, monitor `traefik_compare_traffic_metrics` and `traefik_analyze_logs(source="access")`, and revert DNS/LB weights 100% back to `ingress-nginx` immediately if 5xx spikes.

## Reference Documentation

- [Traefik v3.6+ NGINX Annotation Support Matrix](references/annotation-support-matrix.md)
- [Provider Configuration and Coexistence Rules](references/provider-configuration-and-coexistence.md)
- [Zero-Downtime Cutover and Rollback Runbook](references/cutover-and-rollback-runbook.md)
