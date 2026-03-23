# Traffic Management Test Guide — Traefik MCP Server

**Target application**: `api-service` in `production` namespace  
**Ingress**: Traefik (with Argo Rollouts for Progressive Delivery)  
**Analysis**: Anomalies, Health Monitoring  
**Strategies**: Weighted Canary

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Test Scenarios (Tools & Resources)](#3-test-scenarios-tools--resources)
4. [Natural Language Prompts](#4-natural-language-prompts)
5. [TLS Testing: Prerequisites and How to Test](#5-tls-testing-prerequisites-and-how-to-test)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Traefik | Installed and deployed as Ingress Controller |
| Traefik MCP Server | Running (e.g. `uv run traefik-mcp-server`) |

---

## 2. Environment Setup

### Verify Application Services
Ensure you have backends to route traffic to:
```bash
kubectl get svc -n production | grep api-service
```
*(You should ideally have `api-service-stable` and `api-service-canary` running)*

---

## 3. Test Scenarios (Tools & Resources)

### Scenario A: Lifecycle of a Weighted Canary Deployment
Tests the `traefik_manage_weighted_routing` tool alongside traffic distribution and health resources.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Create initial route (100% stable) | **Tool**: `traefik_manage_weighted_routing` (action=create, route_name, hostname, **stable_service** (required — exact K8s Service name), stable_weight=100, canary_weight=0). Omit `canary_service` for single-backend. Optional: `path_prefix`, `path_match_type`, `tls_enabled`, `tls_secret_name`, `middlewares`. Creates TraefikService `{route_name}-wrr` & IngressRoute. |
| 2 | Verify Creation | **Resource**: `traefik://traffic/routes/list`<br>Lists TraefikServices to verify it exists. |
| 3 | Shift to 95/5 | **Tool**: `traefik_manage_weighted_routing` (action=update, stable_weight=95, canary_weight=5) |
| 4 | Monitor Distribution | **Resource**: `traefik://traffic/production/api-service-route/distribution`<br>Checks live distribution percentage. |
| 5 | Complete (0/100) | **Tool**: `traefik_manage_weighted_routing` (action=update, stable_weight=0, canary_weight=100) |
| 6 | Cleanup | **Tool**: `traefik_manage_weighted_routing` (action=delete) |

### Scenario B: Adding Middleware Protections
Tests the `traefik_manage_middleware` tool and cluster health resources.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Rate Limiting | **Tool**: `traefik_manage_middleware` (action=create, middleware_type=rate_limit, average=100, burst=200, period="1s") |
| 2 | Circuit Breaker | **Tool**: `traefik_manage_middleware` (action=create, middleware_type=circuit_breaker, trigger_type=error-rate, threshold=0.3, response_code=429)<br>*(Note: circuit breaker open returns 429 so we can tell proxy CB rejection from a backend 503 error. Allowed range: 400-599. Running create with the same middleware_name updates its properties.)* |
| 3 | Monitor Health | **Resource**: `traefik://traffic/production/api-service-route/distribution`<br>Check route distribution and health. Alternatively: `traefik://metrics/production/api-service-stable/summary` for service metrics. |

### Scenario C: Strip Prefix Middleware (Optional)
Tests path rewriting for nginx migration.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Strip Prefix | **Tool**: `traefik_manage_middleware` (action=create, middleware_type=strip_prefix, middleware_name=api-strip, namespace=production, prefixes=["/api"]) |
| 2 | Attach to Route | **Tool**: `traefik_manage_route_middlewares` (action=attach, route_name=api-service-route, middleware_names=["api-strip"], namespace=production) |

### Simple IngressRoute (no TraefikService, multiple rules)
Use **`traefik_manage_simple_route`** with **`action=create`** when you want an IngressRoute that points **directly** to K8s Services (no TraefikService/WRR). Supports **multiple route rules** in one IngressRoute. If the route already exists, it is patched **in-place** to avoid traffic gaps.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Create simple route | **Tool**: `traefik_manage_simple_route` (**action=create**, route_name=hello-world-preview, namespace=default, entry_points=["web"], routes=[{ "match": "Host(`hello-world-preview.example.com`)", "service_name": "hello-world-preview", "service_port": 80 }]) |
| 2 | Multiple rules | **Tool**: `traefik_manage_simple_route` (**action=create**) with routes=[ rule1, rule2, ... ]. Each rule: match, service_name, service_port (optional), middlewares (optional). |
| 3 | In-place update | **Tool**: `traefik_manage_simple_route` (**action=create**) using the exact same `route_name` to seamlessly patch changes avoiding outage gaps. |
| 4 | Delete | **Tool**: `traefik_manage_simple_route` (**action=delete**, route_name=hello-world-preview) — for non-WRR routes without a TraefikService companion. |

Equivalent to the YAML you provided: one IngressRoute, entryPoints web, one route rule matching the host and sending traffic to the K8s Service `hello-world-preview` on port 80.

### Scenario D: Path-Based Routing and TLS
Tests `traefik_manage_weighted_routing` with path_prefix, TLS, and middlewares.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Create path-based route | **Tool**: `traefik_manage_weighted_routing` (action=create, route_name=api-path-route, hostname=api.example.com, **stable_service**=api-service-stable, path_prefix="/api", path_match_type="PathPrefix", stable_weight=100, canary_weight=0, namespace=production) |
| 2 | Verify route | **Resource**: `traefik://traffic/production/api-path-route/distribution` |
| 3 | Create TLS route | **Tool**: `traefik_manage_weighted_routing` (action=create, route_name=checkout-route, hostname=checkout.example.com, **stable_service**=checkout-backend, tls_enabled=True, tls_secret_name=checkout-tls, stable_weight=100, canary_weight=0, namespace=production) |
| 4 | Create route with middlewares | **Tool**: `traefik_manage_weighted_routing` (action=create, route_name=secure-route, hostname=secure.example.com, **stable_service**=secure-backend, middlewares=["rate-limit", "auth"], stable_weight=100, canary_weight=0, namespace=production) |
| 5 | Cleanup | **Tool**: `traefik_manage_weighted_routing` (action=delete) for each route |

### Backend ServersTransport and Service sticky sessions

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Create transport | **Tool**: `traefik_manage_servers_transport` (**action=create**, name=my-app-transport, namespace=default, dial_timeout=5s, response_header_timeout=60s) — then set on the backend Service: `traefik.ingress.kubernetes.io/service.serverstransport: default-my-app-transport@kubernetescrd` |
| 2 | HTTPS backend (lab) | **Tool**: `traefik_manage_servers_transport` (**action=create**, name=https-backend, insecure_skip_verify=true) — add `service.serversscheme: https` on the Service if needed |
| 3 | Delete transport | **Tool**: `traefik_manage_servers_transport` (**action=delete**, name=my-app-transport, namespace=default) |
| 4 | Enable sticky | **Tool**: `traefik_configure_service_affinity` (**action=enable**, service_name=hello-world-preview, namespace=default, cookie_name=SESSIONID, cookie_max_age=3600) |
| 5 | Disable sticky | **Tool**: `traefik_configure_service_affinity` (**action=disable**, service_name=hello-world-preview, namespace=default) |

---

## 5. TLS Testing: Prerequisites and How to Test

### Naming: what the MCP controls vs. what you pass as-is

- **Route / TraefikService (MCP convention)**: The server always names the weighted backend resource `{route_name}-wrr` (e.g. route `hello-world-route` → TraefikService `hello-world-route-wrr`). You can assume this when referring to or cleaning up routes.
- **K8s Service names (no convention)**: Stable and canary backend names are **not** assumed to end with `-stable` or `-canary`. Pass the exact K8s Service names the user provides; they are used as-is. `stable_service` is required for create; `canary_service` is required only when `canary_weight > 0`.

### Entry points and single-backend routes

- **Entry points**: Traefik uses `web` (HTTP) and `websecure` (HTTPS). There is no entry point named `https`. The tool validates entry point names and raises a clear error if an invalid name is used; the value `https` is automatically normalized to `websecure`. Do not pass custom entry point names unless your Traefik instance defines them.
- **Single-backend (no canary)**: To route only to one service, use `stable_weight=100`, `canary_weight=0`, pass **stable_service** (required), and **omit** `canary_service`. The tool will create a TraefikService with a single backend.

### Prerequisites for TLS

| Requirement | Description |
|-------------|-------------|
| **Traefik `websecure` entrypoint** | Traefik must expose HTTPS (e.g. port 443). When `tls_enabled=True`, the route uses the `websecure` entrypoint. Ensure Traefik is configured with a `websecure` entry point and that it is exposed (e.g. NodePort or LoadBalancer) so you can reach it. |
| **Kubernetes TLS Secret** | A Secret of type `kubernetes.io/tls` in the **same namespace** as the IngressRoute, containing `tls.crt` (certificate) and `tls.key` (private key). The secret name is passed as `tls_secret_name`. |
| **Backend services** | Stable/canary services (e.g. `hello-world-stable`, `hello-world-canary`) in that namespace, as for any weighted route. |

### Creating a TLS secret (for testing)

Use a self-signed certificate for local/testing:

```bash
# Create a self-signed cert for hello-world.example.com (valid 365 days)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=hello-world.example.com"

# Create the Kubernetes secret in the same namespace as the route (e.g. default)
kubectl create secret tls hello-world-tls --cert=tls.crt --key=tls.key -n default
```

For production, use cert-manager, Let's Encrypt, or your PKI; ensure the secret exists in the route namespace before creating the TLS route.

### Creating the TLS route via MCP

- **Tool**: `traefik_manage_weighted_routing`  
- **Parameters**: `action=create`, `route_name=...`, `hostname=...`, `stable_weight=100`, `canary_weight=0`, `tls_enabled=True`, `tls_secret_name=<secret-name>`, `namespace=...`  
- Example: create route `checkout-route` at `checkout.example.com` with secret `checkout-tls` in `default`.

### How to test TLS

1. **Confirm Traefik HTTPS port**  
   Check how `websecure` is exposed (e.g. `kubectl get svc -n <traefik-ns>` and note the NodePort or LoadBalancer port for 443).

2. **Optional: DNS / hosts**  
   Point the hostname (e.g. `hello-world.example.com`) to the Traefik ingress IP or use `/etc/hosts`.

3. **Call HTTPS**  
   - Browser: `https://hello-world.example.com:<websecure-port>/`  
   - CLI: `curl -k https://hello-world.example.com:<websecure-port>/`  
   (`-k` only for self-signed certs.)

4. **Verify certificate**  
   - Browser: check the lock icon and certificate details.  
   - CLI: `openssl s_client -connect hello-world.example.com:<port> -servername hello-world.example.com` and inspect the presented certificate.

If the route is created with `tls_enabled=True` and `tls_secret_name` pointing to an existing TLS secret in the same namespace, Traefik will terminate TLS on that entrypoint and forward plain HTTP to the backend.

---

## 4. Natural Language Prompts

Use these exact prompts with the MCP Server to test the workflows.

## Natural Language Prompts (Adapted for hello-world)

Use these with the MCP client to drive the same workflow:

```text
Create a weighted route for "hello-world-route" in "default" at "hello-world.example.com" with 100% stable and 0% canary, using services hello-world-stable and hello-world-canary.
```

```text
List all Traefik services across all namespaces.
```

```text
Update the weights for "hello-world-route" in "default" to 95% stable and 5% canary.
```

```text
What is the current traffic split and distribution for "hello-world-route" in "default"?
```

```text
Update the weights for "hello-world-route" in "default" to 0% stable and 100% canary.
```

```text
Delete the "hello-world-route" in "default".
```

### Middleware Prompts

```text
Create a rate_limit middleware named "api-rate-limit" in "production" with an average of 50, burst of 100, per 1s.
```

```text
Create a circuit_breaker middleware named "api-cb" in "production" with an error-rate trigger and a 0.3 threshold. Set response_code=429 so we can tell proxy CB rejection from a backend 503 error.
```

```text
What is the current traffic split and distribution for "api-service-route" in "production"?
```

```text
Delete the circuit breaker middleware "hello-world-cb" in "default".
```

### Strip Prefix & Attach Prompts (Scenario C)

```text
Add a strip prefix middleware "api-strip" in "production" that strips "/api" from incoming request paths.
```

```text
Attach middleware "api-strip" to IngressRoute "api-service-route" in "production".
```

### Path-Based and TLS Prompts (Scenario D)

```text
Create route "api-path-route" in "production" at "api.example.com" with path prefix "/api" — route only /api/* traffic, 100% stable.
```

```text
Create a TLS-enabled route "checkout-route" at "checkout.example.com" with secret "checkout-tls" and attach "rate-limit" middleware.
```
