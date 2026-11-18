# Rate Limit and Circuit Breaker Tuning

## Table of Contents

1. [Token-Bucket Rate Limit Sizing](#1-token-bucket-rate-limit-sizing)
2. [Source Criterion behind Cloud Load Balancers](#2-source-criterion-behind-cloud-load-balancers)
3. [Circuit Breaker Expression Patterns](#3-circuit-breaker-expression-patterns)
4. [Bounded Retry Policies](#4-bounded-retry-policies)

## 1. Token-Bucket Rate Limit Sizing

Traefik's `rateLimit` uses a token-bucket algorithm:
- `average`: Steady-state tokens replenished per `period` (default `1s`).
- `burst`: Maximum instantaneous spike allowed before HTTP `429 Too Many Requests` is returned (`burst` should typically be `1.5x–3x` of `average`).

## 2. Source Criterion behind Cloud Load Balancers

When Traefik sits behind an AWS ALB/NLB, GCP Load Balancer, or Cloudflare:
- Verify `entryPoints.*.forwardedHeaders.trustedIPs` in `traefik://instance/static-config`.
- Configure `source_criterion.ip_strategy.depth: 1` (or `request_header_name: "CF-Connecting-IP"`) so rate limits apply per end-user IP rather than throttling the load balancer's internal IP.

## 3. Circuit Breaker Expression Patterns

Traefik v3 supports three circuit breaker functions combinable with `&&` and `||`:
- `NetworkErrorRatio() > 0.30`: Trips when `> 30%` of backend connections fail at TCP/dial level.
- `ResponseCodeRatio(500, 600, 0, 600) > 0.25`: Trips when `5xx` responses exceed `25%` of total responses.
- `LatencyAtQuantileMS(50.0) > 500`: Trips when median backend latency exceeds `500ms`.

Recommended timing parameters:
- `check_period: "10s"`
- `fallback_duration: "30s"` (returns `503 Service Unavailable` immediately while open)
- `recovery_duration: "10s"` (linear ramp-up window after fallback expires)

## 4. Bounded Retry Policies

Keep `retry.attempts <= 4` (`initial_interval: "100ms"`). Setting `attempts > 5` risks retry amplification storms during backend brownouts.
