# Traefik MCP Server — Natural Language Prompt Reference

**For every tool and resource call documented in [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md), this guide provides ready-to-use natural language prompts you can give to an AI agent.**

Copy any prompt below exactly or adapt it for your app name, namespace, and image.

> **Design**: Read-only context uses **resources** (`traefik://...`). State-changing actions use **tools**.

---

## Table of Contents

1. [Workflow 1: Traffic Management](#workflow-1-traffic-management)
2. [Workflow 2: Header-Based Canary Routing](#workflow-2-header-based-canary-routing)
3. [Workflow 3: NGINX to Traefik Migration](#workflow-3-nginx-to-traefik-migration)
4. [Workflow 4: Shadow / Dark Launch](#workflow-4-shadow--dark-launch)
5. [Workflow 5: TCP Routing](#workflow-5-tcp-routing)
6. [General Monitoring](#general-monitoring)

---

## Workflow 1: Traffic Management

### Discover TraefikServices

> **Resource**: `traefik://traffic/routes/list`  
> Cluster-wide listing of all TraefikServices. Use when you need to find the TraefikService name before linking to an Argo Rollout.

```
List all Traefik services across all namespaces.
```
```
Show me all TraefikService resources — I need to find which one to link to my rollout.
```

---

### Create weighted route (with optional path, TLS, middlewares)

> **Tool**: `traefik_manage_weighted_routing` (action=create)

```
Create a weighted canary route "api-service-route" in "production" for hostname "api.example.com" — 100% stable, 0% canary.
```
```
Create route "frontend-route" in "staging" at "app.example.com" with path prefix "/api" — route only /api/* traffic to the canary.
```
```
Create a TLS-enabled route "checkout-route" at "checkout.example.com" with secret "checkout-tls" and attach "rate-limit" middleware.
```
```
Create route "api-route" for "api.example.com" with path "/v1" (exact match), TLS, and middlewares "auth" and "rate-limit".
```

---

### Check current traffic split and full route state

> **Resource**: `traefik://traffic/{namespace}/{route_name}/distribution`  
> Returns weights, percentages, middleware specs, IngressRoute match rule, entrypoints, and the linked Argo Rollout name — all in one call.

```
What is the current traffic split and full configuration for "api-service-route" in "production"?
```
```
Show me how traffic is distributed and what middlewares are on "frontend-route" in "staging".
```
```
Get the live traffic distribution for "api-service-route" in "production".
```

---

### Traffic mirroring (shadow launch)

> **Tool**: `traefik_manage_traffic_mirroring` — use `action`: `enable` | `disable` | `update`.

```
Enable traffic mirroring for "api-service-route" in "production" — mirror 20% of production traffic to the canary service (action=enable).
```
```
Set up shadow testing for "frontend" — copy 10% of production requests to the canary pod without affecting users.
```
```
Disable traffic mirroring for "api-service-route" in "production" (action=disable).
```
```
Remove the mirror TraefikService for "frontend-route" in "staging".
```
```
Update mirroring for "api-service-route" in "production" to 50% (action=update).
```
```
Reduce mirroring from 20% to 5% for "frontend-route" in "staging".
```

---

### TCP routing (PostgreSQL, Redis, etc.)

> **Tool**: `traefik_manage_tcp_routing` (action=create)

```
Create a TCP route "postgres-route" in "default" for service "postgres" on port 5432.
```
```
Create IngressRouteTCP "redis-route" for "redis" service on port 6379 with SNI "redis.example.com".
```

> **Tool**: `traefik_manage_tcp_routing` (action=delete)

```
Delete the TCP route "postgres-route" in "default".
```

> **Tool**: `traefik_configure_tcp_middleware`

```
Create a TCP IP allowlist middleware "db-allowlist" in "default" allowing 192.168.1.0/24 and 10.0.0.1.
```

---

### ServersTransport (backend timeouts / TLS)

> **Tool**: `traefik_manage_servers_transport`

```
Create a ServersTransport "api-backend-transport" in production with dial timeout 5s and response header timeout 60s.
```
```
Add a ServersTransport for HTTPS backends with insecure skip verify for debugging — name "grpc-transport", namespace default.
```
```
Delete ServersTransport "old-transport" in the staging namespace.
```

---

### Sticky sessions on Kubernetes Services

> **Tool**: `traefik_configure_service_affinity`

```
Enable Traefik sticky cookies on Service "api-svc" in production with cookie name SESSIONID and max age 3600.
```
```
Turn off sticky session annotations on Service "api-svc" in production.
```

---

### Anomaly detection

There is **no** `traefik_detect_anomalies` tool; use resources and metrics instead.

> **Resource**: `traefik://anomalies/detected`

```
Show me all currently detected traffic anomalies in the cluster.
```

> **Resource**: `traefik://anomalies/history/{namespace}`

```
Show me the anomaly history for the "production" namespace.
```

---

### Delete a route (post-deployment cleanup)

> **Tool**: `traefik_manage_weighted_routing` (action=delete)

```
Delete the "api-service-route" in "production" — the deployment is complete and we no longer need the canary route.
```
```
Clean up the Traefik canary route "frontend-route" in "staging".
```

---

### Rate limiting and Circuit breaker (middleware)

> **Tool**: `traefik_manage_middleware` (middleware_type=rate_limit / circuit_breaker)

```
Add a rate limiting middleware "api-limit" to average 100 requests per 1s with a burst of 200.
```
```
Create a circuit breaker "api-cb" in "production" that triggers if the error-rate is > 0.3. Set response_code=429 (instead of default 503) so we can tell a proxy CB rejection from a backend 503 error. (Allowed range: 400-599).
```
```
Update the existing circuit breaker "api-cb" to use response_code=429.
```

---

### Path prefix stripping (middleware)

> **Tool**: `traefik_manage_middleware` (middleware_type=strip_prefix)

```
Add a strip prefix middleware "api-strip" in "production" that strips "/api" from incoming request paths.
```
```
Create a stripPrefixRegex middleware called "backend-strip" for pattern "^/backend(/|$)".
```

---

## Workflow 2: Header-Based Canary Routing

> **Tool**: `traefik_manage_weighted_routing` (action=create) with `header_name` / `header_value` or `cookie_name` / `cookie_regex`

```
Create a weighted route "api-canary-header" in "production" at hostname "api.example.com" — match header "X-Canary: true" and send traffic to stable/canary per weights (e.g. 0% stable, 100% canary for header-only testers).
```
```
Set up cookie-based routing on a weighted route in "staging" at "app.example.com" — use cookie_name=canary and cookie_regex=.*yes.* so matching cookies hit this route's backends.
```
```
Create a weighted route "checkout-beta" at "checkout.example.com" with header_name=X-Beta and header_value=enabled combined with path_prefix and TLS as needed.
```

> **Tool**: `traefik_generate_routing_manifest` (manifest_type=ingress_for_traefik_service)

```
Create an IngressRoute for the "api-service-ts" TraefikService at hostname "api.example.com" in "production".
```
```
Generate an IngressRoute pointing to the "frontend-weighted" TraefikService at "app.example.com" in "staging".
```

---

## Workflow 3: NGINX to Traefik Migration

### Install Traefik alongside NGINX (Phase 1)

> **Resource**: `traefik://migration/nginx-runbook/{namespace}`

```
Install Traefik alongside our existing NGINX controller in the "traefik" namespace — Phase 1 of migration.
```
```
Start the NGINX to Traefik migration — install Traefik with kubernetesIngressNginx provider enabled.
```

---

### Verify Traefik routing (Phase 2)

> **Resource**: `traefik://migration/nginx-runbook/{namespace}`

```
Get the Traefik loadbalancer IP in the "traefik" namespace so I can test routing before switching DNS.
```
```
What is the external IP of the Traefik ingress controller? I need to test it with curl.
```

---

### NGINX Ingress → Traefik (full annotation support)

> **Tool**: `traefik_nginx_migration` — use `action=generate` for offline/GitOps (no cluster mutation unless you apply YAML yourself), or `action=apply` when `MCP_ALLOW_WRITE=true`.

> **Resources**: `traefik://migration/nginx-ingress-scan`, `traefik://migration/nginx-ingress-analyze`, `traefik://migration/nginx-runbook/{namespace}`

```
Generate the NGINX→Traefik migration bundle for namespace "production" without applying it (action=generate).
```
```
Run the full NGINX to Traefik migration for the Ingress "api" in "staging" (action=apply).
```
```
Read the migration runbook for namespace "production" and list what Middlewares will be created.
```

---

### Agentic Override (Migration Plan)

> **Tool**: `traefik_nginx_migration` (action=apply, with `migration_plan` object)

```
Apply the NGINX migration for "ecommerce" namespace, but ignore the "session-cookie-conditional-samesite-none" annotation and inject the "agent-custom-auth" middleware for the "ecommerce-shop" ingress.
```
```
Run the migration on the "default" namespace but configure the migration_plan to ignore the "auth-url" annotation.
```

---

### Generate mirroring manifest (YAML)

> **Tool**: `traefik_generate_routing_manifest` (manifest_type=mirroring)

```
Generate a mirroring TraefikService YAML for route "api-route" — main service "api-stable", mirror "api-canary", 20% mirror.
```

---

### Create, update, or delete IngressRoute with direct K8s Service backends

> **Tool**: `traefik_manage_simple_route` — `action=create` (upsert) or `action=delete`.

```
Deploy a simple Traefik IngressRoute "api-route" at "api.example.com" in "production" that routes "/" to service "api-service" on port 80 (action=create).
```
```
Update the existing "api-route" IngressRoute in "production" to point to "api-service-v2" on port 8080 (action=create with same route_name).
```

```
Delete the simple IngressRoute "api-route" in "production" (action=delete).
```

> **Tool**: `traefik_generate_routing_manifest` (manifest_type=ingress_for_services)

```
Generate an IngressRoute YAML for hostname "app.example.com" that routes "/api" to "api-service:80" and "/frontend" to "frontend-service:3000".
```

---

### Preserve IngressClass before NGINX removal (Phase 4a)

> **Resource**: `traefik://migration/nginx-runbook/{namespace}`

```
Preserve the "nginx" IngressClass before we uninstall the NGINX controller — make Traefik handle it.
```
```
Create a standalone nginx IngressClass pointing to Traefik so existing Ingress objects still work.
```

---

### Uninstall NGINX (Phase 4b)

> **Resource**: `traefik://migration/nginx-runbook/{namespace}`

```
Uninstall the NGINX Ingress Controller from "ingress-nginx" namespace — Traefik is fully in place.
```
```
Remove the NGINX controller from "ingress-nginx" — we've confirmed Traefik is handling all traffic.
```

> **Resource**: `traefik://migration/nginx-to-traefik`

```
Show me the full NGINX to Traefik migration guide.
```

> **Resource**: `traefik://migration/nginx-to-traefik/{phase}`

```
Show me Phase 2 of the NGINX to Traefik migration guide.
```
```
What are the Phase 4 steps for the NGINX to Traefik migration?
```

---

## Workflow 4: Shadow / Dark Launch

> **Tool**: `traefik_manage_traffic_mirroring`

```
Mirror 20% of production traffic to the canary service "api-service-canary" via route "api-service-route" in "production" (action=enable). Do not affect real users.
```
```
Ramp mirroring to 50% for "api-service-route" in "production" — shadow is performing well (action=update).
```

```
Disable traffic mirroring for "api-service-route" in "production" — shadow testing is complete (action=disable).
```

```
Update mirroring for "api-service-route" in "production" to 50% (action=update).
```
```
Reduce mirroring to 5% for "frontend-route" in "staging" (action=update).
```

> **Resource**: `traefik://traffic/{namespace}/{route_name}/distribution`

```
Show me the route state for "api-service-route" in "production" — I'm monitoring the shadow launch.
```

> **Resource**: `traefik://metrics/{namespace}/{service}/summary`

```
Show performance metrics for "api-service-canary" in "production" — I need to compare shadow vs stable.
```

> **Tool**: `traefik_manage_weighted_routing` (action=update, after shadow passes)

```
Shadow testing passed — start the real canary by shifting 5% of traffic to canary for "api-service-route" in "production".
```

---

## Workflow 5: TCP Routing

> **Tool**: `traefik_generate_routing_manifest` (manifest_type=ingress_route_tcp)

```
Generate an IngressRouteTCP YAML for "postgres-route" — service "postgres" on port 5432 in "default".
```
```
Generate IngressRouteTCP for "redis-route" with SNI "redis.example.com" and TLS passthrough.
```

> **Tool**: `traefik_generate_routing_manifest` (manifest_type=middleware_tcp)

```
Generate a MiddlewareTCP ipAllowList YAML "db-allowlist" allowing 192.168.1.0/24 and 10.0.0.1.
```

---

## General Monitoring

> **Resource**: `traefik://traffic/routes/list`

```
List all HTTP Traefik routes and TraefikServices across the cluster.
```

> **Resource**: `traefik://traffic/tcp/list`

```
List all TCP Traefik routes (IngressRouteTCP) across the cluster.
```

> **Resource**: `traefik://traffic/ingressroutes/list`

```
List all simple IngressRoutes across the cluster.
```

> **Resource**: `traefik://traffic/{namespace}/{route_name}/distribution`

```
Show traffic distribution, weights, middlewares, and match rules for "api-service-route" in "production".
```

> **Resource**: `traefik://metrics/{namespace}/{service}/summary`

```
Show performance metrics (5xx/4xx bounds, P99 latency) for "api-service" in "production".
```

> **Resource**: `traefik://metrics/prometheus/status`

```
Is Prometheus connected and working for metrics collection?
```

> **Resource**: `traefik://anomalies/detected`

```
Show me all currently detected traffic anomalies.
```

> **Resource**: `traefik://anomalies/history/{namespace}`

```
Show anomaly history for the "production" namespace.
```

---


---

*Document Version: 3.0 | Path-based routing, TLS, mirroring (disable/update), TCP routing | Companion to [WORKFLOW_JOURNEYS.md](WORKFLOW_JOURNEYS.md)*
