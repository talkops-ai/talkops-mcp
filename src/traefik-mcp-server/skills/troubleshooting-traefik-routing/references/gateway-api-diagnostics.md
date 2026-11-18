# Kubernetes Gateway API Read & Diagnose Playbook

## Table of Contents

1. [Scope: Read & Diagnose Only](#1-scope-read--diagnose-only)
2. [Inspecting Gateway API Inventory (`traefik://gateway/{namespace}`)](#2-inspecting-gateway-api-inventory-traefikgatewaynamespace)
3. [Diagnosing `HTTPRoute`, `GRPCRoute`, `TLSRoute`, `TCPRoute`, and `Gateway`](#3-diagnosing-httproute-grpcroute-tlsroute-tcproute-and-gateway)

## 1. Scope: Read & Diagnose Only

The Traefik MCP Server supports **read-only inventory and deep diagnostics** for Kubernetes Gateway API (`gateway.networking.k8s.io/v1` and `v1beta1`). Gateway API resources are never mutated or deleted by MCP write tools.

## 2. Inspecting Gateway API Inventory (`traefik://gateway/{namespace}`)

Read `traefik://gateway/{namespace}` (or `traefik://gateway/_all`) to inspect:
- `GatewayClass` (`controllerName: traefik.io/gateway-controller`, `Accepted` condition)
- `Gateway` listeners (`name`, `port`, `protocol`, `hostname`, `allowedRoutes`, `AttachedRoutes`, `Programmed` condition)
- `HTTPRoute`, `GRPCRoute`, `TLSRoute`, `TCPRoute` parent status conditions (`Accepted`, `ResolvedRefs`)
- `ReferenceGrant` cross-namespace permissions (`from`, `to`)

## 3. Diagnosing `HTTPRoute`, `GRPCRoute`, `TLSRoute`, `TCPRoute`, and `Gateway`

Call `traefik_diagnose_route(kind="HTTPRoute", name=..., namespace=...)`:
- **`GATEWAY_NOT_PROGRAMMED`**: Verify `providers.kubernetesGateway.enabled: true` in `traefik://instance/static-config` and confirm the listener `port` maps to a valid Traefik `entryPoint`.
- **`GATEWAY_LISTENER_REJECTS_ROUTE`**: Listener `allowedRoutes.namespaces.from` is `"Same"` while the `HTTPRoute` lives in a different namespace, or `HTTPRoute.spec.hostnames` does not intersect `listener.hostname`.
- **`REFERENCE_GRANT_MISSING`**: `status.parents[].conditions[type=ResolvedRefs].reason == "RefNotPermitted"` indicates a cross-namespace `backendRef` or `certificateRef` without a matching `ReferenceGrant` in the target namespace.
