# ServersTransport and Backend HealthChecks

## Table of Contents

1. [HTTP `ServersTransport` Tuning (`traefik_configure_servers_transport`)](#1-http-serverstransport-tuning-traefik_configure_servers_transport)
2. [TCP `ServersTransportTCP` Tuning](#2-tcp-serverstransporttcp-tuning)
3. [Backend Active HealthChecks & `nativeLB`](#3-backend-active-healthchecks--nativelb)

## 1. HTTP `ServersTransport` Tuning (`traefik_configure_servers_transport`)

Use `traefik_configure_servers_transport(protocol="http", ...)` to customize how Traefik connects to upstream pods:
- `server_name`: SNI hostname sent to HTTPS/gRPC backends.
- `root_cas`: List of Kubernetes Secret names containing internal CA bundles for upstream TLS verification.
- `certificates`: List of Kubernetes Secret names containing client certificates for backend mTLS.
- `max_idle_conns_per_host`: Keep-alive pool size per backend pod (recommended `32–128` for high-RPS microservices).
- `forwarding_timeouts`:
  - `dial`: `"5s"` (fail fast on unreachable pod IPs)
  - `response_header`: `"30s"` (prevent hung upstream requests from exhausting worker goroutines)
  - `idle_conn`: `"90s"`

## 2. TCP `ServersTransportTCP` Tuning

Pass `protocol="tcp"` to `traefik_configure_servers_transport`:
- `dial_timeout: "5s"`, `dial_keep_alive: "15s"`, `termination_delay: "100ms"`
- `tls`: `{"server_name": ..., "root_cas": [...], "certificates": [...], "insecure_skip_verify": false}`

## 3. Backend Active HealthChecks & `nativeLB`

Attach active health checks to any `IngressRoute` or `TraefikService` backend:
- `health_check`: `{"path": "/healthz", "interval": "10s", "timeout": "3s"}`
- `native_lb`: When `false` (default), Traefik load-balances directly across Kubernetes EndpointSlice pod IPs (`serverStatus` visible in `traefik://runtime/http`). When `true`, Traefik forwards to the Kubernetes Service ClusterIP (`kube-proxy`).
