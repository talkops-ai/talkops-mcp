# Header, Cookie, and Query Routing Patterns

## Table of Contents

1. [Dark-Launch Header Routing](#1-dark-launch-header-routing)
2. [Cookie-Based Beta Cohort Routing](#2-cookie-based-beta-cohort-routing)
3. [Priority Ordering Between Header & Catch-All Rules](#3-priority-ordering-between-header--catch-all-rules)
4. [Verifying Precedence with `traefik_trace_request`](#4-verifying-precedence-with-traefik_trace_request)

## 1. Dark-Launch Header Routing

Use structured `RouteMatch` fields in `traefik_configure_http_route` to isolate internal QA traffic before shifting percentage weights:

```json
{
  "match": {
    "host": "api.example.com",
    "path_prefix": "/v2",
    "headers": {"X-Canary": "true"}
  },
  "priority": 200,
  "services": [{"name": "api-canary", "port": 8080}]
}
```
Compiled Traefik v3 rule:
`Host(`api.example.com`) && PathPrefix(`/v2`) && Header(`X-Canary`, `true`)`

## 2. Cookie-Based Beta Cohort Routing

Traefik v3 matches cookies via `HeaderRegexp` on the `Cookie` request header:
- Exact cookie value: `HeaderRegexp(`Cookie`, `(?:^|;\s*)cohort=beta(?:;|$)`)`
- Structured `RouteMatch`: pass `"cookies": {"cohort": "beta"}` to `traefik_configure_http_route`.

## 3. Priority Ordering Between Header & Catch-All Rules

Traefik v3 default priority equals the character length of the `match` expression (`len(rule)`). Because a header-gated rule (`Host(...) && Header(...)`) is longer than `Host(...)`, it naturally wins by default, **unless** the catch-all rule has an explicit `priority` set higher than `len(header_rule)`. Always set explicit `priority` values when combining explicit and default priorities.

## 4. Verifying Precedence with `traefik_trace_request`

After configuring header or cookie rules, verify both paths using `traefik_trace_request`:
1. With `"headers": {"X-Canary": "true"}` -> verify `matched_router` routes to `api-canary`.
2. Without the header -> verify `matched_router` routes to `api-stable` and lists the canary router under `near_misses`.
