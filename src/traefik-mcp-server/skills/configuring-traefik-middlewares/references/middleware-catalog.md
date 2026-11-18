# Traefik v3 Middleware Catalog (24 HTTP + 2 TCP Types)

## Table of Contents

1. [HTTP Rate Limiting, Concurrency & Resilience](#1-http-rate-limiting-concurrency--resilience)
2. [HTTP Authentication & Access Control](#2-http-authentication--access-control)
3. [HTTP Security Headers, CORS & Redirects](#3-http-security-headers-cors--redirects)
4. [HTTP Path & Prefix Manipulation](#4-http-path--prefix-manipulation)
5. [HTTP Payload, Compression, Tracing & Plugins](#5-http-payload-compression-tracing--plugins)
6. [TCP Middlewares (`MiddlewareTCP`)](#6-tcp-middlewares-middlewaretcp)

## 1. HTTP Rate Limiting, Concurrency & Resilience

| `type` Enum | CRD Spec Key | Required / Key Parameters |
| --- | --- | --- |
| `rate_limit` | `spec.rateLimit` | `average` (int, req/period), `burst` (int), `period` (`"1s"`), `source_criterion` |
| `in_flight_req` | `spec.inFlightReq` | `amount` (max concurrent requests), `source_criterion` |
| `circuit_breaker` | `spec.circuitBreaker` | `expression` (e.g. `"NetworkErrorRatio() > 0.30 || ResponseCodeRatio(500, 600, 0, 600) > 0.25"`), `check_period` (`"10s"`), `fallback_duration` (`"30s"`), `recovery_duration` (`"10s"`) |
| `retry` | `spec.retry` | `attempts` (int, `<= 10`), `initial_interval` (`"100ms"`) |
| `errors` | `spec.errors` | `status` (`["500-599"]`), `service` (`{"name": ..., "port": ...}`), `query` (`"/{status}.html"`) |

## 2. HTTP Authentication & Access Control

| `type` Enum | CRD Spec Key | Required / Key Parameters |
| --- | --- | --- |
| `basic_auth` | `spec.basicAuth` | `secret` (Kubernetes Secret name — inline `users` forbidden), `realm`, `remove_header` |
| `digest_auth` | `spec.digestAuth` | `secret` (Kubernetes Secret name — inline `users` forbidden), `realm`, `remove_header` |
| `forward_auth` | `spec.forwardAuth` | `address` (URL), `trust_forward_header`, `auth_response_headers`, `auth_request_headers`, `tls` |
| `ip_allow_list` | `spec.ipAllowList` | `source_range` (list of CIDRs), `ip_strategy` (`{"depth": 1, "excludedIPs": [...]}`) |
| `ip_deny_list` | `spec.ipDenyList` | `source_range` (list of CIDRs) — **Schema-gated**: not a native Traefik v3 OSS `middlewares.traefik.io` CRD field; always check `traefik://schema/Middleware` first and fall back to negated `!ClientIP(\`...\`)` router rules, `ip_allow_list`, or a registered `denyip` plugin when absent |

## 3. HTTP Security Headers, CORS & Redirects

| `type` Enum | CRD Spec Key | Required / Key Parameters |
| --- | --- | --- |
| `headers` | `spec.headers` | `custom_request_headers`, `custom_response_headers`, `access_control_allow_methods`, `access_control_allow_origins_list`, `sts_seconds`, `sts_include_subdomains`, `sts_preload`, `frame_deny`, `content_type_nosniff`, `browser_xss_filter`, `referrer_policy` |
| `redirect_scheme` | `spec.redirectScheme` | `scheme` (`"https"`), `port` (`"443"`), `permanent` (`true`) |
| `redirect_regex` | `spec.redirectRegex` | `regex`, `replacement`, `permanent` |

## 4. HTTP Path & Prefix Manipulation

| `type` Enum | CRD Spec Key | Required / Key Parameters |
| --- | --- | --- |
| `strip_prefix` | `spec.stripPrefix` | `prefixes` (`["/api/v1"]`) — Note: `forceSlash` was removed in Traefik v3 |
| `strip_prefix_regex` | `spec.stripPrefixRegex` | `regex` (`["^/api/v[0-9]+"]`) |
| `add_prefix` | `spec.addPrefix` | `prefix` (`"/v2"`) |
| `replace_path` | `spec.replacePath` | `path` (`"/new-target"`) |
| `replace_path_regex` | `spec.replacePathRegex` | `regex`, `replacement` |

## 5. HTTP Payload, Compression, Tracing & Plugins

| `type` Enum | CRD Spec Key | Required / Key Parameters |
| --- | --- | --- |
| `buffering` | `spec.buffering` | `max_request_body_bytes`, `mem_request_body_bytes`, `max_response_body_bytes`, `retry_expression` |
| `compress` | `spec.compress` | `excluded_content_types`, `included_content_types`, `min_response_body_bytes`, `default_encoding` |
| `content_type` | `spec.contentType` | `auto_detect` (`bool`) |
| `grpc_web` | `spec.grpcWeb` | `allow_origins` (`["*"]`) |
| `pass_tls_client_cert` | `spec.passTLSClientCert` | `pem` (`bool`), `info` (dict) |
| `chain` | `spec.chain` | `middlewares` (`[{"name": "mw1"}, {"name": "mw2"}]`) — validated for circular references |
| `plugin` | `spec.plugin` | `plugin_name` (must exist in `traefik://instance/static-config` `plugins`), `config` (dict) |

## 6. TCP Middlewares (`MiddlewareTCP`)

Pass `protocol="tcp"` to `traefik_configure_middleware`:
- `ip_allow_list` -> `MiddlewareTCP.spec.ipAllowList.sourceRange`
- `in_flight_conn` -> `MiddlewareTCP.spec.inFlightConn.amount`
