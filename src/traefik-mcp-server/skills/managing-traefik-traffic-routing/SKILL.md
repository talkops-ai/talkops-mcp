---
name: managing-traefik-traffic-routing
description: Configures and operates Traefik v3 HTTP IngressRoutes, weighted round-robin canary and blue-green TraefikServices, preview-first traffic weight shifts, header/cookie/query cohort routing, and shadow traffic mirroring on Kubernetes. Use when exposing HTTP or gRPC workloads, splitting canary or blue-green traffic, shifting backend weights, validating or rewriting v2-to-v3 router match rules, rendering IngressRoute/TraefikService GitOps manifests, or setting up shadow traffic mirroring. Do not use for L4 TCP/UDP IngressRouteTCP or IngressRouteUDP routing (use routing-traefik-tcp-and-udp), HTTP/TCP middleware chains or ServersTransport tuning (use configuring-traefik-middlewares), Argo Rollout CRD image/step progression (use progressing-argo-rollouts), or debugging 4xx/5xx access logs (use troubleshooting-traefik-routing).
---

# Managing Traefik v3 Traffic Routing

This skill governs the end-to-end lifecycle of Traefik v3 HTTP/gRPC `IngressRoute` and `TraefikService` resources on Kubernetes (`traefik.io/v1alpha1`). Never shell out to `kubectl` when an MCP resource or tool is available.

## Preconditions

1. Read `traefik://server/capabilities` to verify:
   - `cluster_connected`, `allow_write` mode (if `allow_write: false`, perform read-only discovery + deterministic script validation and output copy-pasteable manifests without calling write tools), active `toolsets`, `crds_installed.traefik.io`, and `prometheus.reachable`.
2. Read `traefik://cluster/contexts` to confirm the active kubeconfig context matches the target environment.
3. Read `traefik://instance/static-config` to verify valid `entryPoints` (e.g., `web`, `websecure`), `certificatesResolvers`, and `providers.kubernetesCRD.ingressClass`.
4. Read `traefik://routes/{namespace}` (and `traefik://manifests/{kind}/{namespace}/{name}` when inspecting an existing `IngressRoute` or `TraefikService` YAML rather than running `kubectl get ... -o yaml`) to inspect hostnames, priorities, and ownership metadata.
   - **Argo Rollouts Coexistence Guard**: Inspect existing `TraefikService` ownership via `traefik_diagnose_route(kind="TraefikService", ...)` and `traefik://manifests/TraefikService/{namespace}/{name}`. If `owner_type == "argo_rollouts"` (`ARGO_ROLLOUT_MANAGED`, owned by an Argo `Rollout`), **never** call `traefik_set_traffic_weights`; explain that the Rollouts controller will immediately overwrite manual weight edits, **activate/read `.agents/skills/progressing-argo-rollouts/SKILL.md`**, inspect `argorollout://rollouts/{namespace}/{rollout}/detail`, and delegate canary progression cleanly via `argo_manage_rollout_lifecycle` on the `argo-rollout` MCP server.
   - If invoked via plugin command workflow (`commands/canary.md` or `commands/onboard.md`), read that command file first and coordinate progressive delivery or GitOps onboarding end-to-end.

## Execution Checklist

- [ ] **Step 1 — Discover capabilities, context & existing routes**: Read `traefik://server/capabilities`, `traefik://cluster/contexts`, `traefik://instance/static-config`, and `traefik://routes/{namespace}` (plus `traefik://manifests/{kind}/{namespace}/{name}` for target CRDs).
- [ ] **Step 2 — Consult reference playbooks & run deterministic scripts**: Read the relevant guide under `references/` and execute the deterministic helper scripts in `scripts/` for rule syntax validation, canary schedule generation, or GitOps YAML rendering.
- [ ] **Step 3 — Verify backend & TLS readiness**: Check `traefik://certificates/{namespace}` and run `traefik_diagnose_route` before routing live traffic.
- [ ] **Step 4 — Preview manifest & unified diff (`dry_run=True`)**: Call `traefik_configure_http_route`, `traefik_configure_weighted_service`, `traefik_set_traffic_weights`, `traefik_configure_traffic_mirroring`, or `traefik_update_route` with `dry_run=True`.
- [ ] **Step 5 — `[GATE]` Apply or hold safely**:
  - If the operator asked for a preview/plan only, if `allow_write: false`, or if a safety guard fails (`WEIGHT_TO_EMPTY_BACKEND`, `ALL_WEIGHTS_ZERO`, `ARGO_ROLLOUT_MANAGED`, or mutating `POST` mirroring against live stateful backends), **stop** and present the preview/remediation.
  - When the operator explicitly requested creating, shifting, updating, or disabling the route/service live and all guards pass, **proceed immediately in the same turn** to `dry_run=False` (passing `expected_resource_version` for weight shifts and `confirm=True` where required).
- [ ] **Step 6 — Verify runtime & live telemetry**: Run `traefik_diagnose_route`, `traefik_trace_request`, `traefik_compare_traffic_metrics(..., include_backend_split=True)`, and read `traefik://metrics/{namespace}/{service}/summary` to confirm healthy cutover.

## Core Workflows

### 1. Exposing HTTP/gRPC Services & Cohort Routing (`IngressRoute`)

Consult [v3-rule-syntax-and-priority.md](references/v3-rule-syntax-and-priority.md) and [header-cookie-routing.md](references/header-cookie-routing.md) whenever authoring or migrating router match rules, header/cookie/query cohorts, or explicit priorities.

1. Validate every non-trivial or migrated v2 match expression deterministically with [validate_match_rule.py](scripts/validate_match_rule.py):
   ```bash
   python3 .agents/skills/managing-traefik-traffic-routing/scripts/validate_match_rule.py --rule 'Host(`shop.example.com`) && PathPrefix(`/`)'
   ```
   *(If running outside `.agents/skills`, invoke `./scripts/validate_match_rule.py` relative to this skill directory.)*
2. Read `traefik://instance/static-config` and `traefik://certificates/{namespace}` to confirm `entry_points` (`["websecure"]`) and TLS `secret_name`.
3. Preview with `traefik_configure_http_route(..., dry_run=True)`:
   - Always pass `rules[].match` as an explicit Traefik v3 backtick string (for example, ``"Host(`shop.example.com`) && PathPrefix(`/`)"``) rather than a structured dict.
   - Always set explicit `priority` on both cohort (`Header` / `HeaderRegexp` cookie boundary regex `(?:^|;\s*)key=val(?:;|$)`) and catch-all fallback routes so `len(match)` never shadows a cohort route.
   - For gRPC backends, set `scheme: "h2c"` (cleartext HTTP/2) or `"https"`.
4. **`[GATE]`** Apply with `traefik_configure_http_route(..., dry_run=False)` when live creation was requested, then verify both cohort and default requests via `traefik_diagnose_route` and `traefik_trace_request`.

### 2. Canary & Blue-Green Traffic Splitting (`TraefikService` + Weight Shifts)

Consult [canary-and-blue-green-playbooks.md](references/canary-and-blue-green-playbooks.md) for progression schedules, sticky-cookie security flags (`http_only: True`, `secure: True`, `same_site: "lax"` or `"strict"`), blue-green `>= 30 minute` warm-standby retention, and rollback gates.

1. When planning canary progressions (`standard`, `critical`, or `fast` risk profiles), execute [plan_weight_schedule.py](scripts/plan_weight_schedule.py):
   ```bash
   python3 .agents/skills/managing-traefik-traffic-routing/scripts/plan_weight_schedule.py --traefik-service frontend-proxy-wrr --namespace otel-demo --stable-service frontend-proxy-stable --canary-service frontend-proxy-canary --profile standard
   ```
2. Create or update the weighted `TraefikService` baseline (`spec.weighted.sticky`, `health_check`) via `traefik_configure_weighted_service(..., health_check={"path": "/", "interval": "10s", "timeout": "3s"}, dry_run=True)` -> `dry_run=False`. When adding sticky cookies during a Blue-Green cutover on an existing `TraefikService`, **decouple spec changes from the traffic flip**: configure `sticky` (`http_only: True`, `secure: True`, `same_site: "Lax"`) at the current `100/0` baseline weights first, then perform the `0/100` traffic shift with `traefik_set_traffic_weights`.
3. For all weight shifts and Blue-Green cutovers (`100/0 -> 0/100`), **always** use `traefik_set_traffic_weights` (never flip live traffic weights inside `traefik_configure_weighted_service`):
   - Call `traefik_set_traffic_weights(name=..., namespace=..., weights=..., dry_run=True)` first to verify `WEIGHT_TO_EMPTY_BACKEND` / `ALL_WEIGHTS_ZERO` guards and capture `details.resource_version`.
   - If a concurrent update causes a `409` `expected_resource_version` conflict on `dry_run=False`, **always explain explicitly** that Kubernetes `resourceVersion` optimistic concurrency control is an intentional safety guard that prevents **lost concurrent updates and race conditions** when another operator or controller edits weights at the same time—**never retry blindly**: re-read `traefik://manifests/TraefikService/{namespace}/{name}` and run a fresh `dry_run=True` preview to inspect the concurrent change before reconciling and capturing the updated `resource_version`.
   - **`[GATE]`** Apply with `traefik_set_traffic_weights(..., expected_resource_version=<rv>, dry_run=False)` when live shifting was requested.
   - Monitor bake health via `traefik_compare_traffic_metrics(..., scope="service", include_backend_split=True)` and read `traefik://metrics/{namespace}/{service}/summary`. Document immediate `100/0` rollback steps if 5xx or P95 latency regresses.

### 3. Shadow Traffic Mirroring

Consult [shadow-mirroring-guide.md](references/shadow-mirroring-guide.md) before enabling any traffic mirror.

1. **Non-Idempotent Mutation Refusal**: Strictly **refuse** mirroring mutating requests (`POST`, `PUT`, `PATCH`, `DELETE` such as `POST /api/checkout` order/payment charges) to shadow backends connected to shared/live databases, caches, payment gateways, or Kafka brokers (which causes duplicate customer charges and state corruption). Also refuse unbounded `mirror_body: true` without `max_body_size` (e.g., cap `max_body_size: 1048576` or set `mirror_body: False`).
2. For safe idempotent read routes (`GET`/`HEAD`):
   - Preview with `traefik_configure_traffic_mirroring(name=..., action="enable", namespace=..., route_name=..., spec={"main": {"name": ..., "port": ...}, "mirrors": [{"name": ..., "port": ..., "percent": 10}], "mirror_body": False, "max_body_size": 1048576}, dry_run=True)`.
   - **`[GATE]`** Apply with `dry_run=False, confirm=True`, inspect `traefik://metrics/{namespace}/{service}/summary` and `traefik_compare_traffic_metrics`, and disable cleanly via `traefik_configure_traffic_mirroring(..., action="disable", route_name=..., dry_run=True)` -> `dry_run=False, confirm=True` when requested.

### 4. Incremental Route Patching, GitOps Rendering & Cleanup

1. **In-Place Route Patching**: Read `traefik://manifests/IngressRoute/{namespace}/{name}` first, preview via `traefik_update_route(name=..., route_kind="IngressRoute", namespace=..., changes={"priority": ..., "middlewares": {"action": "attach", "refs": [{"name": ...}]}}, dry_run=True)`, apply with `dry_run=False`, and verify via `traefik_diagnose_route`.
2. **GitOps Multi-Doc Manifest Rendering**: Whenever asked to generate GitOps-ready `IngressRoute` + `TraefikService` YAML manifests (or when `allow_write: false`), execute [render_route_manifest.py](scripts/render_route_manifest.py):
   ```bash
   python3 .agents/skills/managing-traefik-traffic-routing/scripts/render_route_manifest.py --name otel-storefront --traefik-service frontend-proxy-wrr --namespace otel-demo --host shop.otel-demo.talkops.io --path-prefix / --service frontend-proxy-stable --port 8090 --canary-service frontend-proxy-canary --canary-weight 10 --entry-points websecure --middleware storefront-ratelimit --tls-secret shop-otel-tls
   ```
3. **Cleanup**: Retire unused CRDs after checking route references via `traefik_delete_resource(kind=..., name=..., namespace=..., confirm=True)`.

## Reference Documentation

- [Canary and Blue-Green Playbooks](references/canary-and-blue-green-playbooks.md)
- [Header, Cookie, and Query Routing Patterns](references/header-cookie-routing.md)
- [Shadow Traffic Mirroring Guide](references/shadow-mirroring-guide.md)
- [Traefik v3 Rule Syntax and Priority Calculation](references/v3-rule-syntax-and-priority.md)
