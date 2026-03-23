# Shadow Launch (Traffic Mirroring) Test Guide — Traefik MCP Server

**Target application**: `api-service` in `production` namespace  
**Ingress**: Traefik (with Argo Rollouts for Progressive Delivery)  
**Analysis**: Traffic Anomalies, Health Monitoring  
**Strategies**: Traffic Mirroring (Shadow Launch)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Important Concepts (Mirror vs Canary)](#2-important-concepts-mirror-vs-canary)
3. [Environment Setup](#3-environment-setup)
4. [Test Scenarios (Tools & Resources)](#4-test-scenarios-tools--resources)
5. [Natural Language Prompts](#5-natural-language-prompts)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via `kubectl` |
| Traefik | Installed and deployed as Ingress Controller |
| Traefik MCP Server | Running (e.g. `uv run traefik-mcp-server`) |

---

## 2. Important Concepts (Mirror vs Canary)

Mirroring (`*-mirror`) and Weighted Round Robin (`*-wrr` canary) are fundamentally different. **Do not repoint a production `*-wrr` IngressRoute without explicit sign-off**, as it removes real-user canary exposure.

| Before (`*-wrr` weighted canary) | After (`*-mirror` traffic shadowing) |
|------------------------------------|----------------------------------------|
| A **fraction of real user requests** is served by the canary.  | **All** end-user responses come from the **stable/main** service. |
| Clients receive **either** a canary or stable response. | Canary **only** receives mirrored (duplicated) requests. |
| Production traffic is actively split. | Canary responses are **completely discarded** by Traefik. |

---

## 3. Environment Setup

### Verify Application Services
```bash
kubectl get svc -n production | grep api-service
```
*(You should ideally have `api-service-stable` and `api-service-canary` running)*

If you do not use a `production` namespace, run Scenario A against the **lab profile** in §5 (`canary-route` / `default` / `hello-world-*`).

---

## 4. Test Scenarios (Tools & Resources)

### Scenario A: Progressive Shadow Launch
Tests the `traefik_manage_traffic_mirroring` tool combined with anomaly resources.

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Enable Mirroring | **Tool**: `traefik_manage_traffic_mirroring` — **`action=enable`**, **route_name**, **namespace**, **mirror_percent**, optional **main_service** / **mirror_service** (defaults `{route_name}-stable` / `{route_name}-staging`), optional **attach_to_ingress** (default `false`).<br>Example: `action=enable`, `route_name=api-service-route`, `namespace=production`, `main_service=api-service-stable`, `mirror_service=api-service-canary`, `mirror_percent=20`, `attach_to_ingress=false`.<br>*Creates `{route_name}-mirror`.* Response includes **warning**, **next_steps**, **status** (`created_but_inactive` vs `created_and_active`), **current_ingress_backend**. |
| 2 | Activate Mirror in Ingress | **Option A**: Step 1 with **attach_to_ingress=true** (MCP merge-patches Ingress to `{route_name}-mirror`). ⚠️ *Ends live weighted user split — same as manual.*<br>**Option B**: GitOps / kubectl: set Ingress `services[0].name` to `{route_name}-mirror`. |
| 3 | Evaluate Metrics | **Resources**: `traefik://traffic/routes/list` (mirror: **main_service**, **main_port**, **mirrors**); `traefik://traffic/{namespace}/{ingress_route_name}/distribution` (**traffic_split.type** `mirror`, backends with **is_main** once Ingress uses the mirror TS); `traefik://traffic/ingressroutes/list` (live **targets** per IngressRoute). |
| 4 | Anomaly / signals | **Resource**: `traefik://anomalies/detected` (no dedicated anomaly tool; may be empty or report Argo/Prometheus unavailable in lab). |
| 5 | Ramp Mirroring | **Tool**: `traefik_manage_traffic_mirroring` with **`action=update`** (same route_name / namespace, mirror_percent=50). |
| 6 | **Rollback (Disable)** | **Tool**: `traefik_manage_traffic_mirroring` with **`action=disable`**, **restore_ingress_to_wrr=true** — repoints Ingress to **`{route_name}-wrr`**, then deletes `{route_name}-mirror`. Use **`restore_ingress_to_wrr=false`** only if you will repoint the Ingress yourself. |

---

## 5. Natural Language Prompts

These are **how people usually talk to an agent**: goals and context, not raw tool names. The agent should use the **Traefik MCP server** (mirroring tools + `traefik://` traffic resources) under the hood. Swap in your real route name, namespace, and service names using the table below.

*(The older style used separate enable/disable/update tools; use `traefik_manage_traffic_mirroring` with the right `action`.)*

### Reference naming

| Profile | IngressRoute / story name | Namespace | Stable service | Canary / shadow service |
|---------|---------------------------|-----------|----------------|-------------------------|
| Production story | `api-service-route` | `production` | `api-service-stable` | `api-service-canary` |
| Lab / dev cluster | `canary-route` | `default` | `hello-world-stable` | `hello-world-canary` |

### Set up shadow traffic (create mirror only — don’t switch the live ingress yet)

```text
We’re doing a shadow launch on prod. For the api-service ingress route in production, set up traffic mirroring: send a copy of 20% of traffic to the canary service for observation, but keep user-facing traffic going through stable for now. Use api-service-stable as the real backend and api-service-canary as the shadow. Don’t repoint the ingress to the mirror yet — I only want the mirror TraefikService created. After you run it, tell me what warnings came back and whether the mirror is actually active on the cluster or still waiting on an ingress change.
```

### Turn on shadow and wire the ingress (full shadow — you accept losing the live weighted split)

```text
Turn on traffic mirroring for api-service-route in production: 20% shadow to api-service-canary, stable responses from api-service-stable. Go ahead and update the ingress so traffic goes through the mirror setup. Remind me what that changes for real users vs the old 50/50 weighted canary.
```

### Check what the cluster thinks (list + distribution)

```text
I want to sanity-check our shadow launch. Show me all Traefik traffic services that are doing mirroring — main service, ports, and what percentage is copied to shadow. Then pull the detailed traffic view for api-service-route in production and explain in plain language whether we’re on weighted canary or mirror and which service is the “main” sink.
```

```text
Which TraefikService is our api-service-route ingress actually pointing at right now — the weighted one or the mirror?
```

### Anomalies / health signals

```text
Run a traffic anomaly check for api-service-route in production — use a 2 sigma threshold or whatever the tool defaults to. Tell me if anything looks off.
```

```text
Are there any traffic anomalies flagged cluster-wide right now?
```

### Ramp shadow percentage

```text
Shadow has been stable; bump the mirroring from 20% to 50% for api-service-route in production.
```

### Tear down shadow and go back to weighted canary

```text
We’re done with the shadow test. Turn off traffic mirroring for api-service-route in production, put the ingress back on the weighted TraefikService so real split routing works again, and remove the mirror object.
```

### Lab / local cluster (hello-world, default namespace)

```text
On my dev cluster, enable 20% traffic mirroring for canary-route in default — stable is hello-world-stable, shadow is hello-world-canary — and wire the ingress so it uses the mirror. I know that kills the live weighted split; that’s OK here.
```

```text
We’ve got shadow running on canary-route in default. Pull the route list and the traffic distribution resource and confirm mirror vs main is what we expect.
```

```text
Ramp shadow to 50% on canary-route in default, then shut mirroring down completely and restore the ingress to weighted routing.
```
