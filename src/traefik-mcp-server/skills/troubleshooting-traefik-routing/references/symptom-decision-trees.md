# Symptom Decision Trees (404, 421, 429, 500, 502, 503, 504, TLS)

## Table of Contents

1. [HTTP 404 Not Found](#1-http-404-not-found)
2. [HTTP 421 Misdirected Request / TLS Alert](#2-http-421-misdirected-request--tls-alert)
3. [HTTP 429 Too Many Requests](#3-http-429-too-many-requests)
4. [HTTP 500 Internal Server Error (Router/Middleware Fault)](#4-http-500-internal-server-error-routermiddleware-fault)
5. [HTTP 502 Bad Gateway / 503 Service Unavailable / 504 Gateway Timeout](#5-http-502-bad-gateway--503-service-unavailable--504-gateway-timeout)

## 1. HTTP 404 Not Found

1. Call `traefik_trace_request(request={"url": ...})`:
   - **`matched: false`**: Inspect `near_misses` to see which clause (`Host`, `PathPrefix`, `Header`) failed.
   - **`matched: true` (unexpected router)**: `PRIORITY_SHADOWED` — a higher-priority catch-all router intercepted the request.
2. Call `traefik_diagnose_route` on the expected `IngressRoute`:
   - Check for `ROUTE_IGNORED_BY_PROVIDER`, `ROUTER_DISABLED`, `LEGACY_API_GROUP`, or `RULE_SYNTAX_V2`.
   - Check if a `strip_prefix` middleware stripped a prefix required by the upstream application.

## 2. HTTP 421 Misdirected Request / TLS Alert

1. Call `traefik_diagnose_route(include=["tls"])` and read `traefik://certificates/{namespace}`:
   - Check `TLS_SAN_MISMATCH`, `TLS_SECRET_MISSING`, or `TLS_CERT_EXPIRED`.
   - When `sniStrict: true` is active on a `TLSOption`, Traefik rejects handshakes if no certificate SAN matches the requested SNI.

## 3. HTTP 429 Too Many Requests

1. Call `traefik_trace_request` to list the `middleware_chain`.
2. Read `traefik://policies/{namespace}` to inspect `rateLimit` (`average`, `burst`) and `inFlightReq` (`amount`).
3. Verify `ipStrategy` / `sourceCriterion` when Traefik sits behind a load balancer.

## 4. HTTP 500 Internal Server Error (Router/Middleware Fault)

1. Call `traefik_diagnose_route` — check for `MIDDLEWARE_MISSING`, `MIDDLEWARE_RUNTIME_ERROR`, or `MIDDLEWARE_CHAIN_CYCLE`.
2. Call `traefik_analyze_logs(source="access", filters={"status_range": "5xx"})` — if `ServiceName` is `-` and `Duration` is `< 1ms`, a middleware (`forwardAuth`, plugin) failed before reaching the backend.

## 5. HTTP 502 Bad Gateway / 503 Service Unavailable / 504 Gateway Timeout

- **502 Bad Gateway**: Backend connection refused, wrong `port` (`BACKEND_PORT_MISMATCH`), or `scheme` mismatch (`http` vs `https`/`h2c`).
- **503 Service Unavailable**: `NO_READY_ENDPOINTS`, `WEIGHT_TO_EMPTY_BACKEND`, `BACKEND_HEALTHCHECK_DOWN`, or an open `circuitBreaker` middleware.
- **504 Gateway Timeout**: Upstream exceeded `ServersTransport.spec.forwardingTimeouts.responseHeaderTimeout` — inspect latency in `traefik_compare_traffic_metrics`.
