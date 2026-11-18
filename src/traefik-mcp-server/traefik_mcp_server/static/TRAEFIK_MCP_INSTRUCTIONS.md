# Traefik MCP Server — Execution Plane Instructions

You are connected to the **Traefik MCP Server** (`v0.2.0`), the live Kubernetes and Traefik v3 runtime execution plane.

## Architectural Contract
- **Execution Only**: This MCP server exposes live cluster/runtime state (`resources`) and guarded cluster/diagnostic operations (`tools`). Procedural runbooks live in `skills/`.
- **Read-Only by Default**: Write tools are disabled unless started with `--allow-write` or `MCP_ALLOW_WRITE=true`. Check `traefik://server/capabilities` first.
- **Dry-Run Previews**: All mutating tools (`traefik_configure_http_route`, `traefik_configure_weighted_service`, `traefik_set_traffic_weights`, `traefik_configure_traffic_mirroring`, `traefik_update_route`, `traefik_configure_tcp_udp_route`, `traefik_configure_middleware`, `traefik_configure_tls_policy`, `traefik_configure_servers_transport`) default to `dry_run=True` and return rendered YAML + unified diff + guard results.
- **Destructive Confirmations & Ownership Guards**: Destructive operations (`traefik_delete_resource`, disabling mirroring, removing TLS, changing global `default` `TLSOption`/`TLSStore`) require MCP elicitation or `confirm=True`. Objects managed by Argo Rollouts (`weightedTraefikServiceName`) are refused with a pointer to the Argo Rollouts MCP server.

## Toolsets (15 Tools Max, `<= 8` Parameters Each)
- **`traffic`**: `traefik_configure_http_route`, `traefik_configure_weighted_service`, `traefik_set_traffic_weights`, `traefik_configure_traffic_mirroring`, `traefik_update_route`, `traefik_configure_tcp_udp_route`
- **`policies`**: `traefik_configure_middleware`, `traefik_configure_tls_policy`, `traefik_configure_servers_transport`
- **Lifecycle (with any write toolset)**: `traefik_delete_resource`
- **`diagnostics` (read-only)**: `traefik_diagnose_route`, `traefik_trace_request`, `traefik_compare_traffic_metrics`, `traefik_analyze_logs`, `traefik_audit_configuration`

## Resources (12 Read-Only `traefik://` Resources)
- `traefik://server/capabilities` — Write mode, toolsets, Traefik version, installed CRDs, runtime API & Prometheus status, enabled providers, watched namespaces
- `traefik://cluster/contexts` — Active and available kubeconfig contexts
- `traefik://instance/static-config` — Sanitized static config (entryPoints, provider flags, certResolvers, observability, plugins)
- `traefik://runtime/health` — Runtime router/service/middleware counts and active runtime errors/warnings
- `traefik://runtime/{protocol}` — Concise runtime routers, services (with UP/DOWN server status), and middlewares (`http`, `tcp`, `udp`)
- `traefik://routes/{namespace}` — All `IngressRoute`, `IngressRouteTCP`, `IngressRouteUDP`, and `Ingress` routes with backend trees and `argo_managed` flags (`_all` supported)
- `traefik://manifests/{kind}/{namespace}/{name}` — Sanitized YAML manifest for any Traefik CRD, Ingress, Gateway API route/Gateway, or Service
- `traefik://policies/{namespace}` — `Middleware`, `MiddlewareTCP`, `ServersTransport`, `ServersTransportTCP`, `TLSOption`, and `TLSStore` inventory with `referenced_by`
- `traefik://certificates/{namespace}` — TLS certificate metadata (SANs, issuer, `notAfter`, `days_remaining` — never private keys) and cert-manager `Certificate` status
- `traefik://gateway/{namespace}` — Read-only Gateway API inventory (`GatewayClass`, `Gateway`, `HTTPRoute`, `GRPCRoute`, `TLSRoute`, `TCPRoute`, `ReferenceGrant`)
- `traefik://metrics/{namespace}/{service}/summary` — Real Prometheus service metrics (RPS, 4xx/5xx rate, p95, `server_up`) or `unavailable`
- `traefik://schema/{kind}` — Installed CRD `openAPIV3Schema` property tree for the cluster's Traefik version
