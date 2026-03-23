# TCP Routing Test Guide — Traefik MCP Server

**Target application**: PostgreSQL, Redis, or custom TCP services  
**Ingress**: Traefik (IngressRouteTCP, MiddlewareTCP)  
**Strategies**: SNI-based routing, TLS passthrough, IP allowlisting

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Test Scenarios (Tools & Resources)](#3-test-scenarios-tools--resources)
4. [Natural Language Prompts](#4-natural-language-prompts)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Traefik | Installed with IngressRouteTCP and MiddlewareTCP CRDs |
| TCP backend service | e.g. `postgres` or `redis` Service running |
| Traefik MCP Server | Running (e.g. `uv run traefik-mcp-server`) |

> **Important Notes**: 
> 1. **CRDs:** `IngressRouteTCP` and `MiddlewareTCP` are included in standard Traefik Helm charts. If not present, the TCP tools will fail with a clear error.
> 2. **Entry Points:** The `entry_points` passed to tools (e.g., `postgresql`) **must** be predefined in Traefik's static configuration or Helm values. The MCP cannot dynamically open new ports on the Traefik deployment.
> 3. **SNI vs Plain TCP:** Utilizing `sni_match` (e.g., `HostSNI(\`redis.example.com\`)`) **only applies if the client performs TLS with SNI upstream**. For plain raw TCP clients, you **must** use `sni_match="*"` (the default).

---

## 2. Environment Setup

### Verify TCP Backend Service
```bash
kubectl get svc -n default | grep -E "postgres|redis"
```
*(You should have a TCP service (e.g. `postgres` on port 5432 or `redis` on port 6379) to route to)*

### Verify Traefik TCP Entry Points
Ensure Traefik has TCP entry points configured (e.g. `postgresql` on :5432, `redis` on :6379). Check your Traefik Helm values or static config.

---

## 3. Test Scenarios (Tools & Resources)

### Scenario A: IngressRouteTCP with IP Allowlist
Tests `traefik_configure_tcp_middleware` and `traefik_manage_tcp_routing` for secure TCP routing.

*(Note: Executing `action=create` on an existing route or middleware performs a seamless in-place patch without traffic gaps.)*

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Create IP allowlist middleware | **Tool**: `traefik_configure_tcp_middleware` (middleware_name=db-allowlist, middleware_type=ip_allowlist, source_ranges='["192.168.1.0/24", "10.0.0.1"]', namespace=default) |
| 2 | Create TCP route | **Tool**: `traefik_manage_tcp_routing` (action=create, route_name=postgres-route, service_name=postgres, service_port=5432, entry_points=["postgresql"], middlewares=["db-allowlist"], namespace=default) |
| 3 | Verify route exists | **Resource**: `traefik://traffic/tcp/list`<br>*(Lists IngressRouteTCPs; each rule shows targets and attached MiddlewareTCP **name**, **namespace**, and **`sourceRange`** when resolved.)* |
| 4 | Patch in place (same names) | **Tool**: `traefik_configure_tcp_middleware` (**create** again with same `middleware_name`, new `source_ranges` JSON) → **updated** without delete.<br>**Tool**: `traefik_manage_tcp_routing` (**create** again with same `route_name`, new `service_name` / `service_port` / `sni_match` / `middlewares`) → **updated** without delete. |
| 5 | Delete middleware | **Tool**: `traefik_configure_tcp_middleware` (**action=delete**, middleware_name=…, namespace=default). *Detach or delete routes referencing it first if your cluster rejects deletes.* |
| 6 | Delete TCP route | **Tool**: `traefik_manage_tcp_routing` (action=delete, route_name=postgres-route, namespace=default) |

### Scenario B: Generator (YAML for GitOps)
Tests `traefik_generate_routing_manifest` for IngressRouteTCP and MiddlewareTCP YAML output.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Generate IngressRouteTCP YAML | **Tool**: `traefik_generate_routing_manifest` (manifest_type=ingress_route_tcp, name=postgres-route, service_name=postgres, service_port=5432, namespace=default) |
| 2 | Generate MiddlewareTCP YAML | **Tool**: `traefik_generate_routing_manifest` (manifest_type=middleware_tcp, name=db-allowlist, source_ranges='["192.168.1.0/24"]', namespace=default) |
| 3 | Verify YAML | Apply generated YAML with `kubectl apply -f` and test connectivity |

### Scenario C: TLS Passthrough (e.g. Redis)
Tests TCP route with TLS passthrough for encrypted backends.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Create TCP route with TLS passthrough | **Tool**: `traefik_manage_tcp_routing` (action=create, route_name=redis-route, service_name=redis, service_port=6379, entry_points=["redis"], sni_match="redis.example.com", tls_passthrough=True, namespace=default) |
| 2 | Cleanup | **Tool**: `traefik_manage_tcp_routing` (action=delete, route_name=redis-route, namespace=default) |

---

## 4. Natural Language Prompts

Use these with the MCP client (they map to **`traefik_configure_tcp_middleware`**, **`traefik_manage_tcp_routing`**, and **`traefik://traffic/tcp/list`**).  
**Note:** **`traefik_manage_tcp_routing`** only exposes **`create`** and **`delete`**; a second **`create`** with the **same `route_name`** performs an **in-place patch** (same pattern for MiddlewareTCP **`create`** with an existing name).

### Scenario A — Allowlist + route + verify

```text
Create a TCP IP allowlist middleware "db-allowlist" in "default" allowing 192.168.1.0/24 and 10.0.0.1.
```

```text
Create a TCP route "postgres-route" in "default" for Kubernetes service "postgres" on port 5432, entry point "postgresql", with middleware "db-allowlist".
```

```text
List all TCP IngressRoutes and middleware attachments by reading the resource traefik://traffic/tcp/list.
```

```text
Delete the TCP route "postgres-route" in "default".
```

### In-place upsert (no delete) — route

Second **`create`** with the **same `route_name`** updates **`spec`** (backend, SNI, entryPoints, TLS flags, middlewares) without removing the CRD.

```text
Update the existing TCP route "postgres-route" in "default" to use backend service "hello-world" on port 80, entry point "postgresql", SNI host "tcp-example.com", keeping middleware "postgres-tcp-allowlist".
```

```text
Patch TCP route "mcp-tcp-verify-up" in "default" to backend "hello-world-stable" port 80, entry point "postgresql", SNI "patch-test.example.com" (same route name, use traefik_manage_tcp_routing create).
```

```text
Create TCP route "demo-tcp" in "default" for "hello-world" on port 80 with entry point "postgresql" and SNI "*" for plain/raw TCP clients (no TLS SNI).
```

### In-place upsert — MiddlewareTCP

```text
Update middleware "db-allowlist" in "default" to allow only ["10.0.0.0/8", "172.16.0.1"] (call traefik_configure_tcp_middleware create with the same middleware_name and new source_ranges JSON).
```

```text
Re-run create on MiddlewareTCP "mcp-tcp-mw-upsert" in "default" with source_ranges ["192.168.1.0/24"] to narrow the allowlist.
```

### Attach / change middleware on an existing TCP route

```text
Patch TCP route "postgres-route" in "default" with backend "hello-world" port 80, SNI "tcp-example.com", entry point "postgresql", middlewares ["postgres-tcp-allowlist"].
```

### Middleware delete

```text
Delete the MiddlewareTCP "mcp-tcp-mw-upsert" in "default" (traefik_configure_tcp_middleware action=delete).
```

```text
Remove MiddlewareTCP "db-allowlist" from namespace "default" after no IngressRouteTCP references it.
```

### TLS passthrough (Scenario C style)

```text
Create IngressRouteTCP "mcp-tcp-tls-pass" in "default" for service "hello-world" on port 80, entry point "postgresql", SNI "tls-passthrough-mcp.example.com", with TLS passthrough enabled.
```

```text
Create TCP route "redis-route" in "default" for "redis" on port 6379, entry point "redis", SNI "redis.example.com", tls_passthrough true.
```

```text
Delete the TCP route "mcp-tcp-tls-pass" in "default".
```

### Generator Prompts

```text
Generate an IngressRouteTCP YAML for route name "postgres-route" targeting Kubernetes service "postgres" on port 5432 in namespace "default". Use entry point "postgresql" and catch-all HostSNI (`*`) for plain TCP clients.
```

```text
Generate a MiddlewareTCP ipAllowList YAML "db-allowlist" allowing 192.168.1.0/24 and 10.0.0.1.
```
