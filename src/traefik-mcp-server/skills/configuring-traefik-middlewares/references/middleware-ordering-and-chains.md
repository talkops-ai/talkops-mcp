# Middleware Ordering and Chain Composition

## Table of Contents

1. [Canonical Execution Order](#1-canonical-execution-order)
2. [Common Ordering Anti-Patterns](#2-common-ordering-anti-patterns)
3. [Reusable `chain` Middlewares & Cycle Detection](#3-reusable-chain-middlewares--cycle-detection)

## 1. Canonical Execution Order

Traefik executes middlewares in the exact array order declared on `IngressRoute.spec.routes[].middlewares`. Place edge filtering and rate limits first, authentication second, path rewrites third, and backend resilience last:

1. `ip_allow_list` / `ip_deny_list`
2. `redirect_scheme` / `redirect_regex`
3. `rate_limit` / `in_flight_req`
4. `headers` (CORS preflight & security response headers)
5. `forward_auth` / `basic_auth` / `digest_auth`
6. `strip_prefix` / `add_prefix` / `replace_path`
7. `compress`
8. `retry` / `circuit_breaker` / `buffering` / `errors`

## 2. Common Ordering Anti-Patterns

- **Authentication before Rate Limiting**: Placing `basic_auth` or `forward_auth` before `rate_limit` allows unauthenticated floods to overwhelm the external auth server.
- **`strip_prefix` before `forward_auth`**: Stripping `/admin` before `forward_auth` causes the auth service to see `/` instead of `/admin` in `X-Forwarded-Uri`.
- **`retry` before `rate_limit`**: Not applicable at the router level (since `retry` wraps backend forwarding), but keep resilience middlewares at the tail of the chain for clarity.

## 3. Reusable `chain` Middlewares & Cycle Detection

Instead of repeating 4–5 middlewares across every `IngressRoute`, bundle them into a single-layer `chain` Middleware:
- `traefik_configure_middleware` automatically runs a depth-first cycle detector (`detect_middleware_chain_cycles`, raising `MIDDLEWARE_CHAIN_CYCLE`) before applying any `chain` spec; circular `chain` CRDs in Kubernetes invalidate every router referencing either chain at runtime.
- **Flatten Nested Chains**: Always flatten nested chains (`chain-a -> chain-b`) into a **single-layer acyclic `chain` referencing leaf middlewares directly in canonical order** so cycles can never occur.
- Use `traefik_update_route` with `changes={"middlewares": {"action": "replace", "refs": [...]}}` to fix ordering on an existing route.
