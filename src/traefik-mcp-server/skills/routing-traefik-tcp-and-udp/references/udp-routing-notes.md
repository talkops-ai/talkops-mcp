# UDP Routing Notes and Constraints

## Table of Contents

1. [`IngressRouteUDP` Schema Constraints](#1-ingressrouteudp-schema-constraints)
2. [UDP EntryPoints & Session Timeouts](#2-udp-entrypoints--session-timeouts)

## 1. `IngressRouteUDP` Schema Constraints

Unlike HTTP and TCP routes, UDP is connectionless and has no application-layer header or TLS SNI inspection in `IngressRouteUDP`:
- `routes[]` contains **only** `services` (`name`, `port`, `weight`, `native_lb`).
- `match`, `priority`, `middlewares`, and `tls` are **not** supported on `IngressRouteUDP` and are rejected by `traefik_configure_tcp_udp_route`.

## 2. UDP EntryPoints & Session Timeouts

- Every `IngressRouteUDP` must bind to a UDP `entryPoint` declared in `traefik://instance/static-config` (e.g., `address: ":53/udp"`).
- Traefik maintains virtual UDP streams per `(client IP, client port)` tuple governed by `entryPoints.<name>.udp.timeout` (default `3s`).
