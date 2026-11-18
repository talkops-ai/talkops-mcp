# Pattern Parser and Log Extraction Guide

## Table of Contents
1. [LogQL Parser Selection Matrix](#1-logql-parser-selection-matrix)
2. [Common `| pattern` Expressions by Infrastructure Type](#2-common--pattern-expressions-by-infrastructure-type)
3. [Using `loki_get_log_patterns` to Build Custom Patterns](#3-using-loki_get_log_patterns-to-build-custom-patterns)

---

## 1. LogQL Parser Selection Matrix

| Log Format | Recommended Parser | Relative Speed | Example |
|------------|-------------------|----------------|---------|
| Delimited positional text (Nginx, Envoy, syslog, klog) | `\| pattern` | **Fastest (1x baseline)** | `\| pattern "<ip> - <_> [<_>] \"<method> <uri> <_>\" <status> <bytes>"` |
| `key=value` pairs | `\| logfmt` | Fast (~1.5x) | `\| logfmt level, msg, duration_ms` |
| JSON object (`{...}`) | `\| json` | Moderate (~2–3x; faster with explicit field list) | `\| json status="http.status", latency="duration_ms"` |
| Irregular text with variable optional tokens | `\| regexp` | Slowest (~5–10x) | `\| regexp "(?P<level>INFO\|WARN\|ERROR)\\s+(?P<msg>.*)"` |

---

## 2. Common `| pattern` Expressions by Infrastructure Type

### Nginx / Apache Combined Access Log
Sample:
`10.0.1.4 - - [10/May/2025:14:22:01 +0000] "POST /v1/orders HTTP/1.1" 503 142 "-" "Go-http-client/1.1"`
```logql
| pattern `<client_ip> - <user> [<_>] "<method> <path> <protocol>" <status> <bytes> "<referrer>" "<user_agent>"`
```

### Envoy Proxy Default Access Log
Sample:
`[2025-05-10T14:22:01.123Z] "POST /api/v1/pay HTTP/2" 503 UF 0 95 45 - "10.0.1.4" "curl/8.0" "req-123" "pay.svc:8080" "10.0.2.8:8080"`
```logql
| pattern `[<_>] "<method> <path> <protocol>" <status> <response_flags> <bytes_rx> <bytes_tx> <duration_ms> <upstream_time> "<forwarded_for>" "<user_agent>" "<request_id>" "<authority>" "<upstream_host>"`
```

### Kubernetes `klog` (kubelet / controller-manager / scheduler)
Sample:
`E0510 14:22:01.123456       1 pod_workers.go:1300] "Error syncing pod, skipping" err="failed to start container" pod="prod/api-7d9"`
```logql
| pattern `<severity><date> <time> <_> <source_file>] "<msg>" <kv_tail>` | logfmt
```

---

## 3. Using `loki_get_log_patterns` to Build Custom Patterns

1. Call `loki_get_log_patterns(query='{service_name="legacy-app"}', start="now-1h")`.
2. Loki returns detected templates containing `<_>` placeholders for dynamic tokens.
3. Replace the `<_>` placeholders you care about with named capture variables (`<status>`, `<duration_ms>`) and pass the string directly to `| pattern "..."`.
