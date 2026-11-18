# Traefik v3 Security & Configuration Hardening Checklist (All 20 Check IDs)

## Table of Contents

1. [Security Checks (`SEC-001` – `SEC-005`)](#1-security-checks-sec-001--sec-005)
2. [TLS & Cryptography Checks (`TLS-001` – `TLS-006`)](#2-tls--cryptography-checks-tls-001--tls-006)
3. [Reliability Checks (`REL-001` – `REL-002`)](#3-reliability-checks-rel-001--rel-002)
4. [Configuration Hygiene Checks (`HYG-001` – `HYG-004`)](#4-configuration-hygiene-checks-hyg-001--hyg-004)
5. [Traefik v3 Migration Checks (`V3M-001` – `V3M-002`)](#5-traefik-v3-migration-checks-v3m-001--v3m-002)
6. [Gateway API Checks (`GW-001`)](#6-gateway-api-checks-gw-001)

## 1. Security Checks (`SEC-001` – `SEC-005`)

| Check ID | Severity | Condition | Remediation |
| --- | --- | --- | --- |
| `SEC-001` | `critical` | `api.insecure: true` in static config exposes `/api/*` and dashboard without auth. | Set `api.insecure: false` and expose `api@internal` behind an `IngressRoute` with `basicAuth`/`forwardAuth`. |
| `SEC-002` | `high` | `entryPoints.*.forwardedHeaders.insecure: true` trusts `X-Forwarded-For` from any client IP. | Set `forwardedHeaders.insecure: false` and configure explicit `trustedIPs` CIDRs. |
| `SEC-003` | `medium` | `providers.kubernetesCRD.allowCrossNamespace: true` permits cross-tenant references. | Set `allowCrossNamespace: false` in multi-tenant clusters. |
| `SEC-004` | `medium` | `providers.kubernetesCRD.allowExternalNameServices: true` enables arbitrary DNS egress. | Set `allowExternalNameServices: false` unless explicitly required. |
| `SEC-005` | `high` | `headers` Middleware pairs `accessControlAllowOriginList: ["*"]` with `accessControlAllowCredentials: true`. | Replace `"*"` with explicit origin domains via `traefik_configure_middleware`. |

## 2. TLS & Cryptography Checks (`TLS-001` – `TLS-006`)

| Check ID | Severity | Condition | Remediation |
| --- | --- | --- | --- |
| `TLS-001` | `high` | `TLSOption` allows deprecated `VersionTLS10` or `VersionTLS11`. | Set `min_version: "VersionTLS12"` or `"VersionTLS13"` via `traefik_configure_tls_policy`. |
| `TLS-002` | `medium` | `TLSOption` includes weak CBC, 3DES, RC4, or static RSA cipher suites. | Use `profile: "intermediate"` or `"modern"` via `traefik_configure_tls_policy`. |
| `TLS-003` | `high` | `ServersTransport` or `ServersTransportTCP` sets `insecureSkipVerify: true`. | Configure `root_cas` Secret and set `insecure_skip_verify: false` via `traefik_configure_servers_transport`. |
| `TLS-004` | `medium` | Public HTTP route lacks a `tls` block and has no HTTPS redirect middleware. | Attach TLS or a `redirect_scheme` middleware via `traefik_update_route`. |
| `TLS-005` | `critical` / `high` | TLS certificate in `traefik://certificates/{namespace}` is expired or expiring within 14 days. | Rotate the TLS Secret and verify with `traefik_diagnose_route`. |
| `TLS-006` | `medium` | TLS Secret contains `TRAEFIK DEFAULT CERT` self-signed fallback certificate. | Replace with a valid `cert-manager` or ACME certificate Secret. |

## 3. Reliability Checks (`REL-001` – `REL-002`)

| Check ID | Severity | Condition | Remediation |
| --- | --- | --- | --- |
| `REL-001` | `medium` | `retry` Middleware configures `attempts > 4` (retry amplification risk). | Reduce `attempts` to `2–3` via `traefik_configure_middleware`. |
| `REL-002` | `low` | Weighted `TraefikService` has multiple backends without active `healthCheck`. | Add `health_check` via `traefik_configure_weighted_service`. |

## 4. Configuration Hygiene Checks (`HYG-001` – `HYG-004`)

| Check ID | Severity | Condition | Remediation |
| --- | --- | --- | --- |
| `HYG-001` | `low` | Orphaned `Middleware` or `MiddlewareTCP` (`referenced_by_count == 0`). | Delete unused middleware via `traefik_delete_resource` or attach to a route. |
| `HYG-002` | `low` | Orphaned non-`default` `TLSOption` (`referenced_by_count == 0`). | Delete unused `TLSOption` via `traefik_delete_resource`. |
| `HYG-003` | `low` | Orphaned `TraefikService` or missing target Kubernetes `Service`. | Delete unused `TraefikService` via `traefik_delete_resource`. |
| `HYG-004` | `medium` | Multiple routes declare identical `match` rules without explicit `priority`. | Set explicit `priority` via `traefik_update_route`. |

## 5. Traefik v3 Migration Checks (`V3M-001` – `V3M-002`)

| Check ID | Severity | Condition | Remediation |
| --- | --- | --- | --- |
| `V3M-001` | `high` | Legacy `traefik.containo.us/v1alpha1` CRDs or resources detected. | Migrate resources to `traefik.io/v1alpha1` via `traefik_configure_http_route`. |
| `V3M-002` | `high` | Route rule uses Traefik v2 syntax (`Headers(...)`, multi-arg `Host(...)`, `{var:regex}`) or `ipWhiteList`. | Update rule to Traefik v3 syntax via `traefik_configure_http_route`. |

## 6. Gateway API Checks (`GW-001`)

| Check ID | Severity | Condition | Remediation |
| --- | --- | --- | --- |
| `GW-001` | `high` | `Gateway` or `HTTPRoute`/`GRPCRoute`/`TLSRoute`/`TCPRoute` has `Accepted=False`, `Programmed=False`, or `ResolvedRefs=False`. | Diagnose with `traefik_diagnose_route` and inspect `traefik://gateway/{namespace}`. |
