# Traefik v3 Rule Syntax and Priority Calculation

## Table of Contents

1. [Traefik v3 HTTP Matchers](#1-traefik-v3-http-matchers)
2. [Traefik v2 -> v3 Breaking Syntax Changes](#2-traefik-v2---v3-breaking-syntax-changes)
3. [Rule Priority Calculation](#3-rule-priority-calculation)
4. [Offline Validation with `validate_match_rule.py`](#4-offline-validation-with-validate_match_rulepy)

## 1. Traefik v3 HTTP Matchers

| Matcher | Traefik v3 Syntax | Notes |
| --- | --- | --- |
| Exact Host | ``Host(`api.example.com`)`` | Single argument per `Host(...)` call; join multiple hosts with `\|\|` |
| Regex Host | ``HostRegexp(`^[a-z0-9-]+\.example\.com$`)`` | Standard Go RE2 regular expression |
| Path Prefix | ``PathPrefix(`/api/v1`)`` | Matches `/api/v1` and `/api/v1/*` |
| Exact Path | ``Path(`/healthz`)`` | Exact URI path match |
| Regex Path | ``PathRegexp(`^/users/[0-9]+$`)`` | Go RE2 regex path match |
| Method | ``Method(`GET`)`` | Single HTTP verb per call |
| Exact Header | ``Header(`X-Env`, `staging`)`` | Case-insensitive header key |
| Regex Header | ``HeaderRegexp(`Authorization`, `^Bearer .+`)`` | Go RE2 regex on header value |
| Query Param | ``Query(`version`, `2`)`` | Two backtick arguments (`key`, `value`) |
| Client IP | ``ClientIP(`10.0.0.0/8`)`` | CIDR or IP match |

## 2. Traefik v2 -> v3 Breaking Syntax Changes

- **Multiple arguments in `Host(...)` or `PathPrefix(...)`**: ``Host(`a.com`, `b.com`)`` is **invalid** in v3; use ``Host(`a.com`) || Host(`b.com`)``.
- **Renamed `Headers` / `HeadersRegexp`**: Replaced by singular ``Header(`k`, `v`)`` and ``HeaderRegexp(`k`, `regex`)``.
- **Curly-brace regex macros**: ``HostRegexp(`{subdomain:[a-z]+}.example.com`)`` is removed in v3; use ``HostRegexp(`^[a-z]+\.example\.com$`)``.
- **`Query` key=value format**: ``Query(`foo=bar`)`` is replaced by ``Query(`foo`, `bar`)``.

## 3. Rule Priority Calculation

When `priority` is omitted on a route rule, Traefik v3 assigns a default priority equal to `len(match_string)`. Longer, more specific rules evaluate before shorter catch-all rules.

## 4. Offline Validation with `validate_match_rule.py`

Run `python3 skills/managing-traefik-traffic-routing/scripts/validate_match_rule.py --rule 'Host(`api.example.com`) && PathPrefix(`/v1`)'` to verify v3 syntax and compute priority offline.
