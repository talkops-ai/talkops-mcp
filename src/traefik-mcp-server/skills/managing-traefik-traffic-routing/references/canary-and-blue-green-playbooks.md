# Canary and Blue-Green Traffic Progression Playbooks

## Table of Contents

1. [Standard Canary Weight Schedules](#1-standard-canary-weight-schedules)
2. [Preview-First Weight Shift Protocol](#2-preview-first-weight-shift-protocol)
3. [Prometheus Bake & Abort Thresholds](#3-prometheus-bake--abort-thresholds)
4. [Blue-Green Cutover & Instant Rollback](#4-blue-green-cutover--instant-rollback)
5. [Sticky Sessions & Canary Draining](#5-sticky-sessions--canary-draining)

## 1. Standard Canary Weight Schedules

| Risk Profile | Progression Steps (Canary %) | Bake Window Per Step | Min Sample Volume |
| --- | --- | --- | --- |
| Standard Tier-2 Service | `5% -> 25% -> 50% -> 100%` | `10m` | `>= 100 requests` |
| Critical Tier-1 / Payments | `1% -> 5% -> 15% -> 35% -> 65% -> 100%` | `15m` | `>= 500 requests` |
| Internal / Low-Traffic API | `10% -> 50% -> 100%` | `5m` | `>= 25 requests` |

## 2. Preview-First Weight Shift Protocol

Every weight shift must execute in two phases:

1. **Preview (`dry_run=True`, default)**:
   ```json
   {
     "name": "payments-wrr",
     "namespace": "production",
     "weights": {"payments-stable": 75, "payments-canary": 25},
     "dry_run": true
   }
   ```
   Inspect `details.resource_version`, `diff`, and `guards` (ensuring `WEIGHT_TO_EMPTY_BACKEND` and `ALL_WEIGHTS_ZERO` pass).
2. **Apply (`dry_run=False`) with Optimistic Concurrency**:
   Pass `expected_resource_version` from the preview output so concurrent controller edits cannot be silently overwritten.

## 3. Prometheus Bake & Abort Thresholds

After each step, invoke `traefik_compare_traffic_metrics`:
- **Abort Immediately (`weights={"stable": 100, "canary": 0}`)** if:
  - 5xx error rate exceeds `1.0%` absolute or `+0.5%` delta over baseline.
  - P95 latency increases by `> 25%` compared to baseline.
  - `traefik_diagnose_route` reports `PARTIAL_ENDPOINTS` or `BACKEND_HEALTHCHECK_DOWN`.

## 4. Blue-Green Cutover & Instant Rollback

1. Provision `TraefikService` with `{"app-blue": 100, "app-green": 0}` (and if adding `sticky` session cookies to an existing `TraefikService`, apply `sticky` via `traefik_configure_weighted_service` while keeping `100/0` weights first—never combine config mutation and live cutover in one unguarded step).
2. Verify `app-green` readiness via `traefik_diagnose_route` and synthetic header routing.
3. Always execute the atomic `100/0 -> 0/100` cutover via `traefik_set_traffic_weights(..., weights={"app-blue": 0, "app-green": 100}, dry_run=True)` followed by `traefik_set_traffic_weights(..., expected_resource_version=<rv>, dry_run=False)` so optimistic concurrency and `WEIGHT_TO_EMPTY_BACKEND` guards protect the cutover.
4. Keep `app-blue` scaled up for at least `30m` so instant `100/0` rollback remains available.

## 5. Sticky Sessions & Canary Draining

When `sticky.cookie` is enabled on a weighted `TraefikService`, existing clients pinned to the canary backend will continue routing there until cookie expiration or weight `0`. Always set `http_only: true`, `secure: true`, and `same_site: "Lax"` or `"Strict"`.
