---
name: configuring-traefik-middlewares
description: Configures, lints, and composes Traefik v3 HTTP Middlewares, TCP MiddlewareTCPs, reusable Middleware chains, and backend ServersTransports on Kubernetes. Use when adding rate limiting, circuit breakers, retry policies, security headers, CORS, forwardAuth/basicAuth, IP allow/deny filtering, path rewrites, gRPC-Web, payload buffering, plugin middlewares, or backend transport connection pools and timeouts. Do not use for weighted canary/blue-green traffic splitting or shadow mirroring (use managing-traefik-traffic-routing), TLSOption cipher hardening or X.509 certificate rotation (use securing-traefik-tls-and-certificates), NGINX Ingress annotation migration (use adopting-traefik-nginx-ingress-provider), or cluster-wide security posture scoring (use auditing-traefik-security-posture).
---

# Configuring Traefik v3 Middlewares & Transports

This skill governs HTTP `Middleware` CRDs, TCP `MiddlewareTCP` CRDs, ordered middleware chains, and `ServersTransport` / `ServersTransportTCP` backend transport policies on Kubernetes (`traefik.io/v1alpha1`). Never use raw `kubectl` when MCP resources or tools cover the operation.

## Preconditions

1. Read `traefik://server/capabilities` to check `cluster_connected`, `allow_write`, active `toolsets`, and `crds_installed.traefik.io`.
2. Read `traefik://schema/Middleware` (and `traefik://schema/MiddlewareTCP` for TCP) to inspect installed CRD `spec_properties` before using schema-gated fields (for example, `ipDenyList` is **not** a native field in upstream Traefik v3 OSS `middlewares.traefik.io` CRDs!).
3. Read `traefik://instance/static-config` to verify:
   - `entryPoints.*.forwardedHeaders.trustedIPs` when configuring `ip_allow_list` or `rate_limit` behind a cloud load balancer (AWS ALB/NLB).
   - `plugins` registration before creating any `type="plugin"` Middleware (referencing an unregistered plugin key causes `MIDDLEWARE_RUNTIME_ERROR` and disables attached routers!).
   - `providers.kubernetesCRD.allowCrossNamespace` before referencing cross-namespace middlewares.
4. Read `traefik://policies/{namespace}` and `traefik://manifests/{kind}/{namespace}/{name}` (instead of `kubectl get middleware -o yaml`) to inspect existing policies, chains, and route references, and read `traefik://runtime/http` (or `traefik://runtime/tcp`) when checking per-pod backend health/middleware runtime status.

## Execution Checklist

- [ ] **Step 1 — Inspect capabilities, CRD schema, static config & existing policies**: Read `traefik://server/capabilities`, `traefik://schema/Middleware`, `traefik://instance/static-config`, and `traefik://policies/{namespace}` (plus `traefik://manifests/{kind}/{namespace}/{name}` when modifying an existing route or policy).
- [ ] **Step 2 — Consult reference guides & run deterministic scripts**: Read the matching reference doc under `references/` and run [lint_middleware_spec.py](scripts/lint_middleware_spec.py) / [render_middleware_manifest.py](scripts/render_middleware_manifest.py) when validating specs/chains or generating GitOps YAML.
- [ ] **Step 3 — Enforce zero-secret & chain-ordering guardrails**: Reject inline `basicAuth.users` / `digestAuth.users` credentials outright (always reference a Kubernetes `Secret` via `secret`), reject circular `chain` references (`MIDDLEWARE_CHAIN_CYCLE`), and enforce canonical middleware ordering.
- [ ] **Step 4 — Preview middleware or transport (`dry_run=True`)**: Never skip `dry_run=True`, even if pressured by an operator. Call `traefik_configure_middleware` or `traefik_configure_servers_transport` with `dry_run=True`.
- [ ] **Step 5 — `[GATE]` Apply or hold safely**:
  - If the operator asked for a preview/lint only, if `allow_write: false`, or if an unsafe shortcut was requested (inline `users` password hashes, skipping `dry_run`, `insecure_skip_verify: true`, unregistered `plugin` key, or unsupported `ipDenyList` CRD field), **stop** and provide the hardened configuration/fallback.
  - When the operator explicitly requested creating, updating, attaching, or detaching a valid policy live, **proceed immediately in the same turn** from `dry_run=True` to `dry_run=False`.
- [ ] **Step 6 — Attach/detach on route & verify**: Preview and apply via `traefik_update_route(..., dry_run=True -> False)` and confirm runtime status via `traefik_diagnose_route` and `traefik://runtime/http`.

## Core Workflows

### 1. Creating HTTP & TCP Middlewares (`traefik_configure_middleware`)

Consult [middleware-catalog.md](references/middleware-catalog.md) and [rate-limit-and-circuit-breaker-tuning.md](references/rate-limit-and-circuit-breaker-tuning.md) for production sizing (`burst = 2x average`, `source_criterion.ip_strategy.depth: 1` behind 1 LB layer, `ResponseCodeRatio(500, 600, 0, 600) > 0.25` circuit breakers).

1. **Zero-Secret Rule**: **Never** pass inline `users` or `usersFile` in `basic_auth` or `digest_auth`; always pass `{"secret": "<k8s-secret-name>"}`.
2. **Schema Gating (`ipDenyList` & Plugins)**:
   - Check `traefik://schema/Middleware` first. If `ipDenyList` is absent from `spec_properties` (standard Traefik v3 OSS), do **not** apply `ip_deny_list` with `dry_run=False` (previewing `dry_run=True` will also trigger the schema gate); explain the limitation and provide Traefik v3 OSS alternatives: negated `!ClientIP(\`...\`)` match clauses on the `IngressRoute`, `ip_allow_list` (`ipAllowList`), or a registered `denyip` plugin.
   - Before creating `type="plugin"`, check `plugins` in `traefik://instance/static-config`. If the plugin key is missing from static config, warn that applying the CRD causes `MIDDLEWARE_RUNTIME_ERROR` and show the Helm `experimental.plugins.<key>` static config required first.
3. **TCP Middlewares (`MiddlewareTCP`)**: Pass `protocol="tcp"` to `traefik_configure_middleware`. Always state the L4 scope boundary clearly in your output: `MiddlewareTCP` (`apiVersion: traefik.io/v1alpha1`) supports **only** TCP connection-level `ipAllowList` and `inFlightConn` (HTTP-only middlewares such as `headers`, `stripPrefix`, `forwardAuth`, or `rateLimit` are NOT supported on `MiddlewareTCP`). Render GitOps YAML with [render_middleware_manifest.py](scripts/render_middleware_manifest.py):
   ```bash
   python3 .agents/skills/configuring-traefik-middlewares/scripts/render_middleware_manifest.py --name valkey-cart-acl --namespace otel-demo --protocol tcp --kind MiddlewareTCP --type ip_allow_list --spec-json '{"sourceRange": ["10.42.0.0/16"]}'
   ```

### 2. Canonical Middleware Ordering, Linting & Detach Rollbacks

Consult [middleware-ordering-and-chains.md](references/middleware-ordering-and-chains.md) for execution order and cycle prevention:

```text
ip_allow_list -> redirect_scheme -> rate_limit / in_flight_req -> headers / CORS -> forward_auth / basic_auth -> strip_prefix / replace_path -> compress -> retry -> circuit_breaker -> buffering
```

- `rate_limit` **must** precede `forward_auth` (protects the auth service from unauthenticated floods).
- `forward_auth` **must** precede `strip_prefix` (so `X-Forwarded-Uri` retains the original path prefix such as `/flagd`).
- **Chain Cycle Remediation (`MIDDLEWARE_CHAIN_CYCLE`)**: Circular `chain` references (`chain-a -> chain-b -> chain-a`) fail `traefik_configure_middleware` DFS cycle checks and disable every router referencing either chain. Always remediate by **flattening nested chains into a single-layer acyclic `chain` Middleware that references leaf middlewares directly in canonical execution order** (do not recommend multi-layer nested chain-to-chain indirection).
- When linting a proposed spec or chain order, execute [lint_middleware_spec.py](scripts/lint_middleware_spec.py):
  ```bash
  python3 .agents/skills/configuring-traefik-middlewares/scripts/lint_middleware_spec.py --spec-json '<json>' --chain 'stripPrefix,forwardAuth,rateLimit,ipAllowList'
  ```
- Attach or selectively detach middlewares on an existing route by reading `traefik://manifests/IngressRoute/{namespace}/{name}`, previewing `traefik_update_route(name=..., namespace=..., changes={"middlewares": {"action": "attach"|"detach", "refs": [{"name": ...}]}}, dry_run=True)`, applying `dry_run=False`, and verifying with `traefik_diagnose_route`.

### 3. Configuring Backend `ServersTransport` & `nativeLB` (`traefik_configure_servers_transport`)

Consult [servers-transport-and-healthchecks.md](references/servers-transport-and-healthchecks.md) for connection pool tuning (`max_idle_conns_per_host: 64`), `forwarding_timeouts` (`dial: "5s"`, `response_header: "30s"`, `idle_conn: "90s"`), upstream `root_cas` TLS verification (`insecure_skip_verify: False`), and `nativeLB: false` (direct `EndpointSlice` pod IP load balancing + per-pod Traefik health checks visible in `traefik://runtime/http`) vs `nativeLB: true` (`ClusterIP` kube-proxy routing).

## Reference Documentation

- [Middleware Catalog (24 HTTP + 2 TCP Types)](references/middleware-catalog.md)
- [Middleware Ordering and Chain Composition](references/middleware-ordering-and-chains.md)
- [Rate Limit and Circuit Breaker Tuning](references/rate-limit-and-circuit-breaker-tuning.md)
- [ServersTransport and Backend HealthChecks](references/servers-transport-and-healthchecks.md)
