---
name: routing-traefik-tcp-and-udp
description: Configures, diagnoses, and decommissions Traefik v3 L4 TCP IngressRouteTCP and UDP IngressRouteUDP routes, HostSNI matching, TLS passthrough vs TLS termination, PROXY protocol v1/v2 forwarding, MiddlewareTCP, and ServersTransportTCP on Kubernetes. Use when exposing PostgreSQL, Valkey/Redis, Kafka, OTLP gRPC TCP listeners, TLS passthrough services, or UDP Jaeger/OTel/DNS endpoints through Traefik. Do not use for L7 HTTP/gRPC IngressRoutes, header/cookie routing, or TraefikService canary weights (use managing-traefik-traffic-routing), HTTP middleware chain ordering (use configuring-traefik-middlewares), HTTP TLSOption client mTLS policies (use securing-traefik-tls-and-certificates), or NGINX HTTP Ingress annotation classification (use adopting-traefik-nginx-ingress-provider).
---

# Routing Traefik v3 TCP & UDP Workloads

This skill governs L4 TCP (`IngressRouteTCP`, `MiddlewareTCP`, `ServersTransportTCP`) and UDP (`IngressRouteUDP`) routing on Kubernetes (`traefik.io/v1alpha1`). Always use MCP resources and tools rather than raw `kubectl`.

## Preconditions

1. Read `traefik://server/capabilities` and `traefik://cluster/contexts` to verify `cluster_connected`, `allow_write`, active `toolsets`, and installed L4 CRDs (`ingressroutetcps`, `ingressrouteudps`, `middlewaretcps`, `serverstransporttcps`).
2. Read `traefik://instance/static-config` to verify that target L4 `entryPoints` (e.g., `websecure`, `valkey`, `postgres`, `otlp-tls`, `jaeger-udp`, `udp-otel`) are statically declared.
   - **Hard Prerequisite Blocker**: Traefik CRDs **cannot** dynamically open new host/Service TCP or UDP ports! If the requested port/entryPoint (e.g., `:9092` / `kafka`) is absent from `traefik://instance/static-config`, **halt before creating `IngressRouteTCP`** (`ENTRYPOINT_UNKNOWN`) and provide both options: (a) adding the static `entryPoints.<name>` + Kubernetes `Service` port in Traefik's Helm values, or (b) multiplexing TLS-wrapped `HostSNI` traffic over existing `websecure` (`:443`) if clients initiate TLS SNI.
3. Read `traefik://routes/{namespace}` (and `traefik://manifests/{kind}/{namespace}/{name}` when inspecting an existing `IngressRouteTCP`/`IngressRouteUDP`), plus `traefik://runtime/tcp` or `traefik://runtime/udp` to inspect active L4 routers and port/SNI allocations.

## Execution Checklist

- [ ] **Step 1 — Verify static L4 entryPoints & runtime routers**: Read `traefik://server/capabilities`, `traefik://instance/static-config`, `traefik://routes/{namespace}`, and `traefik://runtime/tcp` (or `traefik://runtime/udp`).
- [ ] **Step 2 — Consult L4 reference guides & validate `HostSNI`/TLS/UDP rules**: Read [tcp-sni-and-tls-patterns.md](references/tcp-sni-and-tls-patterns.md) or [udp-routing-notes.md](references/udp-routing-notes.md):
  - Specific `HostSNI(\`host.example.com\`)` rules **must** use backticks `` ` `` (never single quotes `'...'`) with **zero leading/trailing spaces** inside backticks, and **must** include `tls` (`passthrough=True` or `secret_name` termination), otherwise `TCP_SNI_WITHOUT_TLS` breaks routing. Whenever diagnosing or correcting `HostSNI(...)` quote/whitespace syntax pitfalls, **always** also invoke `traefik_trace_request(request={"protocol": "tcp", "sni": "<hostname>"})` to verify SNI router resolution!
  - Raw non-TLS TCP (e.g., Valkey `:6379`, raw PostgreSQL `:5432`) has no TLS ClientHello SNI and **must** use ``HostSNI(`*`)`` (`tls=None`) on a **dedicated** L4 `entryPoint`—never put ``HostSNI(`*`)`` without TLS on shared `websecure` (`:443`)!
  - `IngressRouteUDP` supports **only** `entryPoints` and `routes[].services` (`name`, `port`, `weight`, `nativeLB`)—strictly reject `match`, `priority`, `middlewares`, and `tls` on UDP routes, and always recommend **Kubernetes `NetworkPolicy` in the target namespace** (or cloud load-balancer ACLs) at the network layer if UDP source-IP filtering/ACLs are needed!
- [ ] **Step 3 — Preview L4 policies & routes (`dry_run=True`)**: Call `traefik_configure_middleware(..., protocol="tcp")`, `traefik_configure_servers_transport(..., protocol="tcp")`, or `traefik_configure_tcp_udp_route` with `dry_run=True`.
- [ ] **Step 4 — `[GATE]` Apply or hold safely**:
  - If a prerequisite entryPoint is missing, if invalid UDP fields (`match`/`middlewares`/`tls`) or `HostSNI` without TLS were requested, or if preview-only/`allow_write: false`, **stop** and explain the fix.
  - When the operator explicitly requested creating or deleting a valid L4 route/policy live, **proceed immediately in the same turn** from `dry_run=True` to `dry_run=False` (and `confirm=True` for `traefik_delete_resource`).
- [ ] **Step 5 — Verify L4 runtime & trace**: Run `traefik_diagnose_route(kind="IngressRouteTCP"|"IngressRouteUDP", ...)`, `traefik_trace_request(request={"protocol": "tcp", "sni": ...})` (for TCP), and inspect `traefik://runtime/tcp` or `traefik://runtime/udp`.

## Core Workflows

### 1. TCP TLS Passthrough, TLS Termination & Raw TCP (`IngressRouteTCP`)

Consult [tcp-sni-and-tls-patterns.md](references/tcp-sni-and-tls-patterns.md) (including PostgreSQL's `SSLRequest` preamble caveat vs direct TLS ClientHello SNI).

1. **TLS Passthrough** (backend terminates TLS/mTLS itself, e.g., `kafka:9093` on `websecure`):
   - `traefik_configure_tcp_udp_route(name=..., protocol="tcp", namespace=..., entry_points=["websecure"], routes=[{"match": "HostSNI(`kafka.example.com`)", "services": [{"name": "kafka", "port": 9093}]}], tls={"passthrough": True}, dry_run=True -> False)`.
2. **TLS Termination at Traefik** (Traefik decrypts using `Secret`, forwards plaintext TCP upstream):
   - Verify `Secret` in `traefik://certificates/{namespace}`, then call `traefik_configure_tcp_udp_route(..., tls={"secret_name": "<tls-secret>", "passthrough": False}, dry_run=True -> False)`.
3. **Raw Non-TLS TCP + `MiddlewareTCP` + PROXY Protocol v2**:
   - Configure `MiddlewareTCP` via `traefik_configure_middleware(..., protocol="tcp", type="ip_allow_list"|"in_flight_conn", dry_run=True -> False)` and `ServersTransportTCP` via `traefik_configure_servers_transport(..., protocol="tcp", spec={"dial_timeout": "10s"}, dry_run=True -> False)`.
   - **PROXY Protocol Warning**: Always warn that setting `proxy_protocol_version: 2` corrupts initial TCP bytes unless the upstream listener (e.g., Envoy `envoy.filters.listener.proxy_protocol`) explicitly parses PROXY v2 headers!

### 2. Stateless UDP Routing (`IngressRouteUDP`) & L4 Cleanup

Consult [udp-routing-notes.md](references/udp-routing-notes.md) for virtual `(client IP, client port)` UDP stream session affinity and `entryPoints.<name>.udp.timeout` (default `3s`).

1. Preview & apply `traefik_configure_tcp_udp_route(name=..., protocol="udp", namespace=..., entry_points=[...], routes=[{"services": [{"name": ..., "port": ..., "weight": ...}]}], dry_run=True -> False)`, then verify `traefik://runtime/udp` and `traefik_diagnose_route(kind="IngressRouteUDP", ...)`.
2. Decommission retired TCP/UDP routes cleanly via `traefik_delete_resource(kind="IngressRouteTCP"|"IngressRouteUDP", name=..., namespace=..., confirm=True)` after checking references in `traefik://routes/{namespace}`.

## Reference Documentation

- [TCP HostSNI, TLS Passthrough, and PROXY Protocol Patterns](references/tcp-sni-and-tls-patterns.md)
- [UDP Routing Notes and Constraints](references/udp-routing-notes.md)
