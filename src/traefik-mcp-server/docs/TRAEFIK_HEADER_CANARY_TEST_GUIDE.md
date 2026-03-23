# Header-Based Canary Test Guide — Traefik MCP Server

**Target application**: `frontend` in `staging` namespace  
**Ingress**: Traefik  
**Strategies**: Header-based matching / Cookie-based matching

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Test Scenarios (Tools & Resources)](#3-test-scenarios-tools--resources)
4. [Natural Language Prompts](#4-natural-language-prompts)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Traefik | Installed and deployed as Ingress Controller |
| Traefik MCP Server | Running (e.g. `uv run traefik-mcp-server`) |

---

## 2. Environment Setup

### Verify Application Services
```bash
kubectl get svc -n staging | grep frontend
```
*(You should ideally have `frontend-stable` and `frontend-canary` running)*

---

## 3. Test Scenarios (Tools & Resources)

### Scenario A: Header & Cookie-Based Canary Routing
Tests `traefik_manage_weighted_routing` (create) with optional header/cookie matchers, plus generator YAML for the baseline TraefikService/IngressRoute if desired.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Baseline route | **Tool**: `traefik_manage_weighted_routing` (action=create, route_name=frontend-route, hostname=app.example.com, namespace=staging, stable_service=frontend-stable, canary_service=frontend-canary, stable_weight=100, canary_weight=0) **or** `traefik_generate_routing_manifest` (manifest_type=ingress_for_traefik_service, …) for GitOps-only YAML. |
| 2 | Header Canary | **Tool**: `traefik_manage_weighted_routing` (action=create, route_name=frontend-canary-header, hostname=app.example.com, namespace=staging, stable_service=frontend-stable, canary_service=frontend-canary, stable_weight=0, canary_weight=100, header_name=X-Canary, header_value=true)<br>Creates a second IngressRoute + WRR whose match includes Traefik `Header` matcher for X-Canary. |
| 3 | Monitor Route / Metrics | **Resource**: `traefik://traffic/staging/frontend-canary-header/distribution` or `traefik://metrics/staging/frontend-canary/summary`<br>Use the `route_name` you chose in step 2. |
| 4 | Cookie Canary | **Tool**: `traefik_manage_weighted_routing` (…, cookie_name=canary, cookie_regex=.*yes.*) (omit `header_name` / `header_value`)<br>Beta-flag style routing via `HeaderRegexp` on the `Cookie` header. |

---

## 4. Natural Language Prompts

Use these exact prompts with the MCP Server to test the workflows.

### Execution Prompts

```text
Generate an IngressRoute pointing to the "frontend-weighted" TraefikService at "app.example.com" in "staging".
```

```text
Create a header-based canary route for "frontend-canary" in "staging" at hostname "app.example.com" — route requests with header "X-Canary: true" to the canary.
```

```text
Show me the traffic distribution for "frontend-canary-header" in "staging".
```

```text
Show performance metrics for "frontend-canary" in "staging".
```

```text
Set up cookie-based canary routing for "frontend-canary" in "staging" at "app.example.com" — route users with cookie "canary=yes" to the new version.
```
