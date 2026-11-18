# Traefik v3.6+ `kubernetesIngressNGINX` Annotation Support Matrix

## Table of Contents

1. [Tier 1 — Native In-Place Support (No CRD Rewrite Needed)](#1-tier-1--native-in-place-support-no-crd-rewrite-needed)
2. [Tier 2 — Supported with Behavioral Nuances](#2-tier-2--supported-with-behavioral-nuances)
3. [Tier 3 — Unsupported Annotations (Require Native Traefik Middleware / CRD)](#3-tier-3--unsupported-annotations-require-native-traefik-middleware--crd)

## 1. Tier 1 — Native In-Place Support (No CRD Rewrite Needed)

When `providers.kubernetesIngressNGINX` is enabled in Traefik v3.6+, the following `nginx.ingress.kubernetes.io/*` annotations are translated directly by the Traefik controller:

| Category | Supported `nginx.ingress.kubernetes.io/*` Annotations |
| --- | --- |
| Rewrites & Redirects | `rewrite-target`, `use-regex`, `app-root`, `ssl-redirect`, `force-ssl-redirect`, `permanent-redirect`, `permanent-redirect-code`, `temporal-redirect`, `temporal-redirect-code`, `preserve-trailing-slash` |
| Authentication | `auth-type` (`basic` / `digest`), `auth-secret`, `auth-secret-type`, `auth-realm`, `auth-url`, `auth-method`, `auth-signin`, `auth-Signin-redirect-param`, `auth-response-headers`, `auth-tls-secret` |
| CORS | `enable-cors`, `cors-allow-origin`, `cors-allow-methods`, `cors-allow-headers`, `cors-expose-headers`, `cors-allow-credentials`, `cors-max-age` |
| Sticky Sessions | `affinity` (`cookie`), `session-cookie-name`, `session-cookie-path`, `session-cookie-domain`, `session-cookie-samesite`, `session-cookie-secure`, `session-cookie-max-age`, `session-cookie-expires` |
| Canary Routing | `canary`, `canary-by-header`, `canary-by-header-value`, `canary-by-header-pattern`, `canary-by-cookie`, `canary-weight`, `canary-weight-total` |
| Rate Limits & IP ACL | `limit-rps`, `limit-rpm`, `limit-burst-multiplier`, `limit-connections`, `limit-whitelist`, `whitelist-source-range` |
| Upstream Transport & TLS | `backend-protocol` (`HTTP`, `HTTPS`, `GRPC`, `GRPCS`, `H2C`), `proxy-connect-timeout`, `proxy-read-timeout`, `proxy-send-timeout`, `proxy-body-size`, `proxy-buffering`, `proxy-ssl-secret`, `proxy-ssl-verify`, `proxy-ssl-name`, `proxy-ssl-server-name`, `upstream-vhost`, `custom-headers`, `x-forwarded-prefix` |
| Client Cert mTLS | `auth-tls-verify-client`, `auth-tls-verify-depth`, `auth-tls-pass-certificate-to-upstream` |

## 2. Tier 2 — Supported with Behavioral Nuances

- **`rewrite-target` + `use-regex: "true"`**: Traefik uses Go RE2 regular expressions (`$1`, `$2`). PCRE lookaheads/lookbehinds (`(?!...)`) are not supported in Go RE2 and must be simplified.
- **`limit-rps` / `limit-rpm`**: Evaluated per Traefik replica using Traefik's in-memory token bucket (`average = rps`, `burst = rps * limit-burst-multiplier`).
- **`proxy-body-size: "0"`**: Treated as unlimited request body size; positive values (`"10m"`) configure Traefik's `buffering.maxRequestBodyBytes`.

## 3. Tier 3 — Unsupported Annotations (Require Native Traefik Middleware / CRD)

| Unsupported NGINX Annotation | Traefik v3 Native Replacement |
| --- | --- |
| `configuration-snippet` / `server-snippet` (Header injection) | `traefik_configure_middleware(type="headers", ...)` |
| `configuration-snippet` (Path/URI rewrite) | `traefik_configure_middleware(type="replace_path_regex", ...)` |
| `configuration-snippet` (`deny` CIDR block) | `traefik_configure_middleware(type="ip_deny_list", ...)` (Traefik v3.5+) |
| `auth-snippet` | `traefik_configure_middleware(type="forward_auth", ...)` |
| `modsecurity-snippet` / `enable-modsecurity` | Traefik Coraza WAF `plugin` Middleware (`traefik_configure_middleware(type="plugin", ...)`) |
| `stream-snippet` | `traefik_configure_tcp_udp_route(protocol="tcp", ...)` |
