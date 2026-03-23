# NGINX to Traefik Migration Test Guide — Traefik MCP Server

**Tool**: `traefik_nginx_migration` (`action=apply` / `generate` / `revert` — mutating when applying or reverting)  
**Resources**: `nginx-ingress-scan` + `nginx-ingress-analyze` + `nginx-runbook` (cluster-wide and `{namespace}` variants)  
**Ingress**: Legacy NGINX Controller → Traefik Controller  

**See also:** [ING_SWITCH_REFERENCE.md](ING_SWITCH_REFERENCE.md) — vendored reference; [ING_SWITCH_MCP_IMPLEMENTATION.md](ING_SWITCH_MCP_IMPLEMENTATION.md) — spec; [ING_SWITCH_MIGRATION_TASK_TRACKER.md](ING_SWITCH_MIGRATION_TASK_TRACKER.md) — task tracker; examples under `docs/ing-switch/examples/`.

**Middleware primitives:** After running `traefik_nginx_migration` (YAML bundle), you can adjust or add `Middleware` CRDs with **`traefik_manage_middleware`** — same underlying spec builders as the migrator. See [MIDDLEWARE_TOOLS.md](MIDDLEWARE_TOOLS.md) for `middleware_type` × parameters. Regression: `uv sync --group dev && uv run pytest tests/test_traefik_middleware_builders.py -q`.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [Tool Reference](#3-tool-reference)
4. [Test Scenarios](#4-test-scenarios)
5. [Natural Language Prompts](#5-natural-language-prompts)
6. [Regression Fixtures](#6-regression-fixtures)
7. [Post-migration Cleanup](#7-post-migration-cleanup)

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Kubernetes cluster | Accessible via kubeconfig |
| NGINX Ingress Controller | Running with Ingress resources deployed |
| Traefik MCP Server | Running (e.g. `uv run traefik-mcp-server`) |

---

## 2. Environment Setup

### Verify NGINX is running
```bash
kubectl get svc -n ingress-nginx | grep ingress-nginx-controller
kubectl get ingressclass nginx
kubectl get ingress --all-namespaces
```

### Optional: Deploy test Ingresses
Apply example manifests from `docs/ing-switch/examples/` to create Ingress resources with various NGINX annotations:
```bash
kubectl apply -f docs/ing-switch/examples/01-basic-routing.yaml
kubectl apply -f docs/ing-switch/examples/06-cors.yaml
kubectl apply -f docs/ing-switch/examples/08-rate-limit-ip.yaml
```

### Apply **all** ing-switch examples (Scenario A — full fixture set)

The YAML files use **multiple namespaces** that do not exist on a fresh cluster. Create them once, then apply the directory:

```bash
cd /path/to/traefik-mcp-server   # repo root for this package

for ns in production fintech ecommerce platform services security messaging enterprise; do
  kubectl create namespace "$ns" 2>/dev/null || true
done

kubectl apply -f docs/ing-switch/examples/
```

**Admission webhook note:** If Ingress NGINX has **snippet annotations disabled** (common on Docker Desktop / hardened installs), `02-ssl-tls.yaml` and `11-full-featured.yaml` may be **rejected** (`configuration-snippet` not allowed). The other nine files should still apply; you will see **zero** `complexity: unsupported` from those two until snippets are allowed or you apply trimmed manifests.

Then fetch **`traefik://migration/nginx-ingress-scan`** (or `.../nginx-ingress-scan/production`) for routing + **`nginxAnnotations`**. For full compatibility, **`read_resource`** **`traefik://migration/nginx-ingress-analyze/production`** (or cluster-wide **`.../nginx-ingress-analyze`**) — not the migration tool.

---

## 3. Tool Reference

### MCP resources (scan + analyze)

| URI | Purpose |
|-----|---------|
| `traefik://migration/nginx-ingress-scan` | Inventory (`schema`: `traefik.mcp/nginx-ingress-scan/2`): `summary`, `controller`, `ingresses[]` with **`paths`**, **`nginxAnnotations`**, `ref`, `complexity`, `hosts`, `backends`. |
| `traefik://migration/nginx-ingress-scan/{namespace}` | Same shape, scoped to one namespace. |
| `traefik://migration/nginx-ingress-analyze` | Full compatibility analysis cluster-wide (`schema`: `traefik.mcp/nginx-ingress-analyze/1`): `target`, `ingressReports` (**`breakingAnnotations`** when breaking), `summary`. |
| `traefik://migration/nginx-ingress-analyze/{namespace}` | Same analysis shape, scoped to one namespace. |
| `traefik://migration/nginx-runbook` | Full migration runbook (markdown) with inline YAML for Middlewares and updated Ingresses. |
| `traefik://migration/nginx-runbook/{namespace}` | Same runbook, scoped to one namespace. |

Use **resources** for inventory, compatibility, and default runbooks (read-only context). Use the **tool** for **`action=apply`** (mutate cluster), **`action=generate`** (preview / `migration_plan` overrides without apply), or **`action=revert`** (single Ingress rollback).

### `traefik_nginx_migration`

Generates with overrides and applies the migration. The tool response is **small**: `status`, `migration` (summary), optional `apply_result`, and **`compatibilityReport`** URIs. (For default read-only generation, use the `nginx-runbook` resource instead).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | `apply` \| `generate` \| `revert` | `apply` | **`apply`**: Middleware CRDs + strategic-merge patch Ingress (needs **`MCP_ALLOW_WRITE=true`**). **`generate`**: same pipeline without cluster apply (preview / overrides). **`revert`**: undo one Ingress; requires **`ingress_name`**. |
| `namespace` | string | — | Scope to one namespace (required for all actions) |
| `target` | `traefik` \| `gateway-api` | traefik | **apply / generate** only |
| `switch` | bool | false | **apply** only: patch `ingressClassName` nginx → traefik |
| `migration_plan` | object | — | **apply / generate** only: optional per-Ingress overrides. Keys: Ingress **`name`** or **`namespace/name`**. Values: `ignore_annotations` (string[]), `inject_middlewares` (string[]). See below. |
| `ingress_name` | string | — | **revert** only: Ingress to roll back |

#### `migration_plan` (agent / operator overrides)

Use this after **`read_resource`** on **`nginx-ingress-analyze/{namespace}`** when the operator accepts dropping or working around specific annotations.

| Field | Type | Effect |
|-------|------|--------|
| `ignore_annotations` | string[] | Short nginx keys (e.g. `session-cookie-conditional-samesite-none`) or full `nginx.ingress.kubernetes.io/...` paths. Removed from **compatibility analysis** for that Ingress and excluded from **automatic Middleware generation**. Annotations that normally would be stripped after translation are **kept** on the generated Ingress when listed here (so NGINX-only behavior may remain visible until you edit the manifest). |
| `inject_middlewares` | string[] | Middleware **names** in the same namespace (`my-mw` → `namespace-my-mw@kubernetescrd`) or full refs (`otherns-mw@kubernetescrd`). Appended to **`traefik.ingress.kubernetes.io/router.middlewares`** after generated middlewares. Create those Middleware CRDs first (e.g. `traefik_manage_middleware` or apply your YAML). |

Example (tool arguments alongside `namespace`):

```json
{
  "namespace": "ecommerce",
  "migration_plan": {
    "ecommerce-shop": {
      "ignore_annotations": [
        "session-cookie-conditional-samesite-none"
      ],
      "inject_middlewares": [
        "custom-strict-samesite-mw"
      ]
    }
  }
}
```

Regression: `uv run pytest tests/test_migration_agent_intelligence.py -q`

**Pipeline:**

```text
read_resource nginx-ingress-scan[/{ns}]     → inventory + paths + nginx annotation values
read_resource nginx-ingress-analyze[/{ns}]   → full compatibility (use for agents / large context)
read_resource nginx-runbook[/{ns}]           → default runbook with inline YAML (read-only)

traefik_nginx_migration (action=apply)      → apply cluster mutations; action=generate → preview with agent overrides; action=revert → single Ingress rollback
```

**Migration bundle output (in Runbook):**

| Path | Description |
|------|-------------|
| `00-migration-report.md` | Analysis summary with per-Ingress annotation tables |
| `01-install-traefik/` | Helm install script + `values.yaml` |
| `02-middlewares/` | Traefik `Middleware` CRDs per Ingress |
| `03-ingresses/` | Updated Ingress manifests with Traefik annotations |
| `04-verify.sh` | Verification script (curl tests via Traefik LB) |
| `05-dns-migration.md` | DNS cutover guide |
| `06-cleanup/` | IngressClass preservation + NGINX removal scripts |

**Day-2 (no re-migration):** The apply path uses shared `TraefikService` logic for ServersTransport CRDs and Service sticky patches. To adjust backends **without** raw `kubectl`, agents can use **`traefik_manage_servers_transport`** (timeouts/TLS) and **`traefik_configure_service_affinity`** (sticky on the Service). See [TRAEFIK_TRAFFIC_MANAGEMENT_TEST_GUIDE.md](TRAEFIK_TRAFFIC_MANAGEMENT_TEST_GUIDE.md) for suggested steps.

---

## 4. Test Scenarios

### Scenario A: Discovery scan

| Step | Action | Expected |
|------|--------|----------|
| 1 | Read resource `traefik://migration/nginx-ingress-scan` | Digest JSON: controller, `summary`, `ingresses[]` with `complexity` per ref |
| 2 | Read `traefik://migration/nginx-ingress-scan/{namespace}` | Same shape scoped to one namespace |
| 3 | Optional: `read_resource` `traefik://migration/nginx-ingress-analyze/...` | Same as analyze resource: `ingressReports` / `summary`; breaking → `breakingAnnotations` |
| 4 | Verify complexity | From resource: `complexity` on each Ingress; snippet-based → `unsupported` when present |

### Scenario B: Annotation analysis

| Step | Action | Expected |
|------|--------|----------|
| 1 | Analyze for Traefik target | Each annotation mapped with status + target resource + note |
| 2 | Check summary counts | Total, fully compatible, needs workaround, has unsupported — all correct |
| 3 | Verify breaking detection | `overallStatus: breaking` → non-empty `breakingAnnotations` (unsupported mappings); e.g. `configuration-snippet` |

### Scenario C: Full migration (read-only runbook)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Read resource `traefik://migration/nginx-runbook/{namespace}` | Returns a markdown runbook mapping out all phases |
| 2 | Verify Middleware YAML | In phase 2 step 1: CORS → `Headers`; rate-limit → `RateLimit`; IP allowlist → `IPAllowList` |
| 3 | Verify updated Ingress | In phase 2 step 2: NGINX annotations stripped; `traefik.ingress.kubernetes.io/router.middlewares` added |

### Scenario D: End-to-end migration (apply tool)

**Prerequisite:** server started with **`MCP_ALLOW_WRITE=true`**; otherwise `apply_result.status` is **`blocked`**.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Migrate with `action=apply` (default) | Middleware CRDs created/updated; Ingress **strategic-merge patched** (annotations + **spec**: rules, `ingressClassName`, TLS) |
| 2 | Verify Middlewares exist | `kubectl get middleware -A` shows generated middlewares |
| 3 | Verify Ingress patched | `kubectl get ingress <name> -o yaml` shows Traefik middleware annotation and updated **spec** where generated YAML differs |
| 4 | Check apply results | Response includes `apply_result.summary` with applied/error counts (or `blocked` if writes disabled) |

---

## 5. Natural Language Prompts

### Scan

```text
Scan my cluster for all NGINX Ingress resources and tell me what you find —
controller type, how many Ingresses, and their complexity level.
```

```text
Scan the "production" namespace for NGINX Ingresses and show me the annotation summary.
```

### Analyze

```text
Analyze all my NGINX Ingresses for Traefik compatibility. Which annotations
are fully supported, which need workarounds, and which are unsupported?
```

```text
Check if my Ingresses in the "ecommerce" namespace can be migrated to Traefik without any breaking changes.
```

### Migrate Runbook (read-only)

```text
Read the Traefik migration runbook for all my NGINX Ingresses.
Don't apply anything yet — I want to review the generated YAML first.
```

```text
Read the migration runbook for the "ecommerce" namespace to review the
Middleware CRDs, updated Ingresses, install scripts, and verification steps.
```

### Migrate (end-to-end apply)

```text
Migrate all my NGINX Ingresses to Traefik and apply the changes directly
to the cluster — create the Middleware CRDs and patch the Ingress annotations.
```

```text
Run the full NGINX to Traefik migration for the "production" namespace
and apply everything end-to-end.
```

### Agentic Override Workflow (Supervised Autonomy)

This is the end-to-end workflow for an Agent to discover a breaking change, consult the operator, create a custom fix, and execute the migration using a strategic override.

1. **Step 1: Discovery & Analysis**
   * **Action:** Agent reads the compatibility resource to find breaking changes without mutating the cluster.
   * **Prompt:** *"Analyze the `ecommerce` namespace for NGINX to Traefik migration and tell me if there are any breaking annotations. Don't migrate yet."*
   * **Tool/Resource:** Agent calls `read_resource` on `traefik://migration/nginx-ingress-analyze/ecommerce`.

2. **Step 2: Human Consultation & Custom Primitive Creation**
   * **Action:** Agent creates a custom workaround via primitive tools to replace the broken NGINX logic.
   * **Prompt:** *"I see `auth-signin` is unsupported. Please create a custom Traefik ForwardAuth middleware named `agent-custom-auth` in the `ecommerce` namespace pointing to `http://auth.internal` to replace it."*
   * **Tool/Resource:** Agent calls `traefik_manage_middleware(action="create", middleware_type="forward_auth", middleware_name="agent-custom-auth", forward_auth_address="http://auth.internal")`.

3. **Step 3: Intelligent Migration Execution**
   * **Action:** Agent runs the bulk migration tool but uses `migration_plan` to inject its intelligence payload. It bypasses the breaking NGINX logic and dynamically wires up the custom Traefik CRD.
   * **Prompt:** *"Now run the full migration for the `ecommerce` namespace with apply enabled. Make sure to ignore the `auth-signin` annotation, and explicitly inject the `agent-custom-auth` middleware we just created into the `ecommerce-admin` ingress routing."*
   * **Tool/Resource:** Agent calls `traefik_nginx_migration` with `action=apply`, `namespace=ecommerce`, and `migration_plan`:
     ```json
     {
       "action": "apply",
       "namespace": "ecommerce",
       "migration_plan": {
         "ecommerce-admin": {
           "ignore_annotations": ["auth-signin"],
           "inject_middlewares": ["agent-custom-auth"]
         }
       }
     }
     ```

### Follow-up prompts

```text
Show me the NGINX to Traefik migration guide for DNS cutover steps.
```

```text
We've fully migrated. What manual cleanup steps remain —
specifically, when can I safely delete the old Ingress objects?
```

---

## 6. Regression Fixtures

Apply each file from `docs/ing-switch/examples/` to a test namespace:

| Example | Key annotations | Expected middleware |
|---------|----------------|-------------------|
| `01-basic-routing.yaml` | (none) | No middleware |
| `02-ssl-tls.yaml` | `ssl-redirect`, `force-ssl-redirect` | `RedirectScheme` |
| `03-auth-external.yaml` | `auth-url`, `auth-response-headers` | `ForwardAuth` |
| `06-cors.yaml` | `enable-cors`, `cors-allow-*` | `Headers` (CORS) |
| `07-path-rewrite-regex.yaml` | `rewrite-target`, `use-regex` | `ReplacePathRegex` |
| `08-rate-limit-ip.yaml` | `limit-rps`, `whitelist-source-range` | `RateLimit` + `IPAllowList` |
| `11-full-featured.yaml` | All of the above + `configuration-snippet` | Multiple + **breaking** flag |

---

## 7. Post-migration Cleanup

The MCP tool **does not** delete your `Ingress` objects. That step is **manual** — installs differ (Helm, raw manifests, GitOps), and you must only remove legacy routes when Traefik already serves the same hostnames.

**When safe to remove:**
- Traefik is running and serving all traffic
- DNS has been cut over to Traefik's LoadBalancer
- You've verified all routes via the generated `04-verify.sh`

**Steps:**
1. List legacy Ingresses: `kubectl get ingress -A`
2. Confirm Traefik routes are authoritative (dashboard, curl, smoke tests)
3. Remove from Git or run `kubectl delete ingress <name> -n <ns>`
4. Optionally uninstall NGINX: use the generated `06-cleanup/02-remove-nginx.sh`
