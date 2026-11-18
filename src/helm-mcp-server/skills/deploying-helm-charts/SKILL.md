---
name: deploying-helm-charts
description: Discovers, validates, plans, and installs Helm charts onto Kubernetes clusters with multi-cluster context verification and rollout health monitoring. Use when deploying a new application via Helm, searching chart repositories, authoring values overrides, previewing rendered manifests, or verifying cluster prerequisites before installation.
---

# Deploying Helm Charts Procedure

## Overview

Follow this four-phase procedure whenever installing a new Helm release. Calibrate execution freedom by phase:
- **Discovery & Values Authoring (High Freedom):** Adapt chart search and values overrides to workload requirements.
- **Pre-Flight Validation & Installation (Low Freedom):** Never call `helm_install_chart` before verifying cluster context, running local validation scripts, and inspecting `helm_plan_release`.

---

## Phase 1: Cluster Context & Prerequisite Verification

1. **Inspect Active Cluster Context:**
   - Read resource `kubernetes://contexts` to verify `current_context` and available clusters.
   - If the target cluster is not active, call `kubernetes_set_context(context_name="<target-context>")`.
   - Read resource `kubernetes://cluster-info` and `kubernetes://namespaces` to confirm connectivity and namespace existence.
2. **Verify Existing Releases:**
   - Call `helm_list_releases(namespace="<target-namespace>")` to confirm the release name is unused and check for potentially conflicting charts/CRDs.

---

## Phase 2: Chart Discovery & Schema Inspection

1. **Configure Repository:**
   - Read resource `helm://repositories` to check configured Helm repositories.
   - If the required repository is missing, consult [known-repositories.md](./references/known-repositories.md) for canonical repository URLs and call `helm_ensure_repository(repo_name="<repo>", repo_url="<url>")`.
2. **Search & Inspect Chart Metadata:**
   - Call `helm_search_charts(query="<keyword>", repository="<repo>")` to identify the exact `repo/chart` reference and version.
   - Read resources:
     - `helm://charts/{repository}/{chart}` — Chart metadata, required `kubeVersion`, and sub-chart dependencies.
     - `helm://charts/{repository}/{chart}/values` — Default `values.yaml` structure.
     - `helm://charts/{repository}/{chart}/readme` — Chart configuration parameters and prerequisites.
3. **Check Cluster Prerequisites & Shared CRDs:**
   - If the chart specifies a minimum Kubernetes version or required API resources/CRDs—or when deploying a secondary release of a CRD-bundling chart (e.g., `kube-prometheus-stack`, `opentelemetry-operator`) into another namespace—always execute `kubernetes_check_prerequisites(min_kubernetes_version="<ver>", required_api_resources=[...])` (and `helm_list_releases()` across namespaces) on the live cluster rather than only describing the call.
   - Because CustomResourceDefinitions (CRDs) are **cluster-scoped** and stamped with `meta.helm.sh/release-name` and `meta.helm.sh/release-namespace` of the owning release, a second release attempting to install `crds/` fails with `invalid ownership metadata`. Never delete shared CRDs; verify CRD presence via `kubernetes_check_prerequisites`, preview via `helm_plan_release`, and pass `skip_crds=True` to `helm_install_chart`.

---

## Phase 3: Local Validation & Release Planning

1. **Author Values Overrides:**
   - Follow [values-authoring.md](./references/values-authoring.md) when constructing the `values` JSON object (pin image tags, set resource requests/limits, never hardcode plaintext secrets).
2. **Run Deterministic Local Validation:**
   - Validate your proposed values JSON/YAML file locally before making cluster calls:
     ```bash
     python3 ./scripts/validate_values.py <values-file.yaml>
     ```
   - If rendering raw manifests via `helm_render_manifests`, validate the rendered YAML structure locally:
     ```bash
     python3 ./scripts/validate_manifests.py <rendered-manifests.yaml>
     ```
     If `validate_manifests.py` reports `valid: false`, block installation, fix the chart templates (`metadata.name`, `spec.selector`, labels), re-render via `helm_render_manifests` (or `helm template` when iterating on a local chart directory before publishing), and re-run `validate_manifests.py` before calling `helm_plan_release`.
3. **Generate Server-Side Release Plan:**
   - Call `helm_plan_release(chart_ref="<repo>/<chart>", release_name="<release>", namespace="<ns>", values={...}, version="<version>")`.
   - Inspect the returned resource breakdown, CRD count, dependency list, and dry-run status.
   - If CRD conflicts are reported and compatible CRDs already exist in the cluster, set `skip_crds=True` during installation.

---

## Phase 4: Controlled Installation & Rollout Verification

1. **Execute Installation:**
   - If `MCP_ALLOW_WRITE=false` is enforced on the Helm MCP server, stop after `helm_plan_release` / `helm_render_manifests`: explain clearly that `helm_install_chart` requires `MCP_ALLOW_WRITE=true` on the Helm MCP server, never bypass the write gate via shell `helm install` or `kubectl apply`, and hand off the validated values and plan.
   - Obtain operator confirmation if required by your environment policy.
   - Call `helm_install_chart`:
     - Always pass explicit `chart_ref` in `<repo>/<chart>` format.
     - Pin `version` for production deployments.
     - Set `create_namespace=True` if the target namespace does not yet exist.
2. **Monitor Workload Readiness:**
   - Immediately call `helm_monitor_deployment(release_name="<release>", namespace="<ns>", max_wait_seconds=120, check_interval=5)`.
   - Verify `status == "ready"` and `issues == []`.
   - If `status` is `"failed"` or `"timeout"`, transition to the `troubleshooting-helm-releases` skill.
