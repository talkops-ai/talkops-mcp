# Traefik Error & Diagnosis Code Catalog (All 41 Codes)

## Table of Contents

1. [Route & Provider Diagnosis Codes](#1-route--provider-diagnosis-codes)
2. [Middleware Diagnosis Codes](#2-middleware-diagnosis-codes)
3. [Backend & Traffic Weight Diagnosis Codes](#3-backend--traffic-weight-diagnosis-codes)
4. [TLS & Certificate Diagnosis Codes](#4-tls--certificate-diagnosis-codes)
5. [Kubernetes Gateway API Diagnosis Codes](#5-kubernetes-gateway-api-diagnosis-codes)
6. [Traffic Health & Ownership Codes](#6-traffic-health--ownership-codes)

## 1. Route & Provider Diagnosis Codes

| Diagnosis Code | Severity | Root Cause | Remediation Tool / Resource |
| --- | --- | --- | --- |
| `HEALTHY` | `info` | Route, runtime router, middlewares, TLS, and backend endpoints are healthy. | None required (`traefik://manifests/{kind}/{namespace}/{name}`). |
| `ROUTE_NOT_FOUND` | `critical` | Target route resource does not exist in the specified namespace. | Read `traefik://routes/{namespace}` or `traefik://gateway/{namespace}`. |
| `ROUTE_IGNORED_BY_PROVIDER` | `error` | `kubernetes.io/ingress.class` annotation does not match `providers.kubernetesCRD.ingressClass`. | Update `ingress_class` via `traefik_configure_http_route`. |
| `INGRESS_NOT_CLAIMED` | `error` | `Ingress` uses `ingressClassName: nginx` while `providers.kubernetesIngressNGINX` is disabled. | Enable `kubernetesIngressNGINX` or update `ingressClassName`. |
| `INGRESS_PROVIDER_CONFLICT` | `error` | `Ingress` mixes both `nginx.ingress.kubernetes.io/*` and `traefik.ingress.kubernetes.io/*` annotations. | Remove conflicting annotation family (see `adopting-traefik-nginx-ingress-provider`). |
| `LEGACY_API_GROUP` | `error` | Resource uses deprecated `traefik.containo.us/v1alpha1` API group. | Re-apply as `traefik.io/v1alpha1` via `traefik_configure_http_route`. |
| `RULE_SYNTAX_V2` | `error` | Match rule uses removed Traefik v2 syntax (`Headers`, multi-arg `Host`, `{name:regex}`). | Rewrite rule in v3 syntax via `traefik_configure_http_route`. |
| `RULE_INVALID` | `error` | Match rule has unbalanced parentheses, backticks, or unknown matcher tokens. | Fix rule expression via `traefik_configure_http_route`. |
| `ROUTER_NOT_IN_RUNTIME` | `warning` | Route exists in Kubernetes but is absent from Traefik `/api/{protocol}/routers`. | Inspect controller logs via `traefik_analyze_logs(source="controller")`. |
| `ROUTER_DISABLED` | `critical` | Traefik runtime disabled the router due to a rule, middleware, or TLS error. | Inspect `runtime_router.error` and fix via `traefik_update_route`. |
| `ENTRYPOINT_UNKNOWN` | `error` | Route references an `entryPoint` not declared in Traefik static config. | Read `traefik://instance/static-config` and update `entry_points`. |
| `PRIORITY_SHADOWED` | `warning` | Another active router has an identical or overlapping rule with higher priority. | Trace with `traefik_trace_request` and set explicit `priority` via `traefik_update_route`. |

## 2. Middleware Diagnosis Codes

| Diagnosis Code | Severity | Root Cause | Remediation Tool / Resource |
| --- | --- | --- | --- |
| `MIDDLEWARE_MISSING` | `critical` | Referenced `Middleware` or `MiddlewareTCP` does not exist in Kubernetes. | Create with `traefik_configure_middleware` or detach with `traefik_update_route`. |
| `MIDDLEWARE_CROSS_NAMESPACE_BLOCKED` | `error` | Route references a middleware in another namespace while `allowCrossNamespace=false`. | Deploy middleware in the same namespace or enable `allowCrossNamespace`. |
| `MIDDLEWARE_RUNTIME_ERROR` | `error` | Traefik runtime reports an instantiation error on the middleware. | Read `traefik://policies/{namespace}` and fix via `traefik_configure_middleware`. |
| `MIDDLEWARE_CHAIN_CYCLE` | `error` | A `chain` Middleware contains a direct or transitive circular reference. | Break the cycle via `traefik_configure_middleware`. |

## 3. Backend & Traffic Weight Diagnosis Codes

| Diagnosis Code | Severity | Root Cause | Remediation Tool / Resource |
| --- | --- | --- | --- |
| `BACKEND_SERVICE_MISSING` | `critical` | Referenced Kubernetes `Service` does not exist. | Verify Service name in `traefik://routes/{namespace}` or deploy the Service. |
| `BACKEND_PORT_MISMATCH` | `error` | Route backend port does not match any port exposed by the Kubernetes `Service`. | Fix backend port via `traefik_configure_http_route`. |
| `NO_READY_ENDPOINTS` | `critical` | Target Kubernetes `Service` has `0` ready endpoints in `Endpoints`/`EndpointSlice`. | Fix pod readiness or shift weight away via `traefik_set_traffic_weights`. |
| `PARTIAL_ENDPOINTS` | `warning` | Some backing pods are `notReady` (`ready < total`). | Check pod health and monitor `traefik_compare_traffic_metrics`. |
| `EXTERNALNAME_NOT_ALLOWED` | `error` | Backend `Service` is `type: ExternalName` while `allowExternalNameServices=false`. | Enable `allowExternalNameServices` or use an in-cluster Service. |
| `EMPTY_SERVICE_NOT_ALLOWED` | `error` | Backend `Service` has 0 ready endpoints while `allowEmptyServices=false`. | Scale up ready pods backing the Service. |
| `TRAEFIK_SERVICE_MISSING` | `critical` | Referenced `TraefikService` (WRR or mirroring) does not exist. | Create via `traefik_configure_weighted_service`. |
| `WEIGHT_TO_EMPTY_BACKEND` | `critical` | Positive traffic weight (`> 0`) is assigned to a backend with `0` ready endpoints. | Shift weight to `0` via `traefik_set_traffic_weights`. |
| `ALL_WEIGHTS_ZERO` | `critical` | Sum of weights across all backends in a weighted `TraefikService` is `0`. | Assign positive weight via `traefik_set_traffic_weights`. |
| `MIRROR_TARGET_MISSING` | `warning` | Shadow mirror target `Service` on a `TraefikService` does not exist. | Update or disable mirroring via `traefik_configure_traffic_mirroring`. |
| `SERVERS_TRANSPORT_MISSING` | `error` | Referenced `ServersTransport` or `ServersTransportTCP` does not exist. | Create via `traefik_configure_servers_transport`. |
| `BACKEND_HEALTHCHECK_DOWN` | `error` | Traefik active healthCheck reports backend server `DOWN` in `/api/http/services`. | Check healthCheck path and pod logs. |

## 4. TLS & Certificate Diagnosis Codes

| Diagnosis Code | Severity | Root Cause | Remediation Tool / Resource |
| --- | --- | --- | --- |
| `TLS_SECRET_MISSING` | `error` | Referenced TLS `Secret` does not exist in the route's namespace. | Read `traefik://certificates/{namespace}` and update via `traefik_update_route`. |
| `TLS_CERT_EXPIRED` | `critical` | X.509 certificate in `tls.secretName` is past its `not_after` timestamp. | Rotate TLS Secret and update route via `traefik_update_route`. |
| `TLS_CERT_EXPIRING` | `warning` | X.509 certificate expires within `cert_expiry_warning_days` (default 14 days). | Renew certificate via `cert-manager` or rotate Secret. |
| `TLS_SAN_MISMATCH` | `error` | Certificate SANs do not cover one or more hostnames in the route's `match` rules. | Issue a certificate covering all route hosts (RFC 6125). |
| `TLS_OPTION_MISSING` | `error` | Referenced `TLSOption` does not exist. | Create via `traefik_configure_tls_policy` or detach via `traefik_update_route`. |
| `CERT_RESOLVER_UNKNOWN` | `error` | `tls.certResolver` is not defined in `certificatesResolvers` in static config. | Read `traefik://instance/static-config` and fix `cert_resolver`. |
| `TCP_SNI_WITHOUT_TLS` | `error` | `IngressRouteTCP` matches a specific `HostSNI` without a `spec.tls` block. | Add `tls` (`passthrough=True` or termination) via `traefik_configure_tcp_udp_route`. |

## 5. Kubernetes Gateway API Diagnosis Codes

| Diagnosis Code | Severity | Root Cause | Remediation Tool / Resource |
| --- | --- | --- | --- |
| `GATEWAY_NOT_PROGRAMMED` | `error` | `Gateway` status condition `Programmed=False`. | Inspect `traefik://gateway/{namespace}` and `traefik://instance/static-config`. |
| `GATEWAY_LISTENER_REJECTS_ROUTE` | `error` | Parent `Gateway` listener rejects route due to `allowedRoutes` namespace/kind/hostname mismatch. | Inspect listener `allowedRoutes` in `traefik://gateway/{namespace}`. |
| `GATEWAY_ROUTE_NOT_ACCEPTED` | `error` | Route parent condition `Accepted=False`. | Inspect parent status condition message in `traefik://gateway/{namespace}`. |
| `GATEWAY_REFS_UNRESOLVED` | `error` | Route parent condition `ResolvedRefs=False` (missing backend Service or invalid port). | Verify target `Service` and port in `traefik://routes/{namespace}`. |
| `REFERENCE_GRANT_MISSING` | `error` | Cross-namespace `backendRef` or `certificateRef` rejected with `RefNotPermitted` (`ResolvedRefs=False`). | Create a `ReferenceGrant` in the target namespace (`traefik://gateway/{namespace}`). |

## 6. Traffic Health & Ownership Codes

| Diagnosis Code | Severity | Root Cause | Remediation Tool / Resource |
| --- | --- | --- | --- |
| `HIGH_ERROR_RATE` | `error` | 5-minute Prometheus `5xx` error rate is `>= 5.0%`. | Inspect logs via `traefik_analyze_logs` and roll back weights via `traefik_set_traffic_weights`. |
| `ARGO_ROLLOUT_MANAGED` | `info` | Resource is actively managed by an Argo Rollout trafficRouting block. | Use the Argo Rollouts MCP server (`argo_manage_rollout_lifecycle`) for weight changes. |
| `GITOPS_MANAGED` | `info` | Resource carries Argo CD or FluxCD ownership metadata. | Commit permanent changes to GitOps after emergency triage. |
