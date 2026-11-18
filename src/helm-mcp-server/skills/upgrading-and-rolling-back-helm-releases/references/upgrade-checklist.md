# Helm Upgrade Pre-Flight & Values Strategy Checklist

## 1. Pre-Upgrade Checklist

- [ ] **Verify Active Context:** Read `kubernetes://contexts` to confirm the target cluster.
- [ ] **Record Baseline Revision:** Read `helm://releases/{namespace}/{release}/history` and note the current working revision number.
- [ ] **Inspect Existing Overrides:** Read `helm://releases/{namespace}/{release}/values` so existing custom settings are not accidentally wiped.
- [ ] **Ensure Chart Repository Exists:** Read `helm://repositories` before calling `helm_plan_release`; because Helm release metadata stores `<chart>-<version>` without its source repository URL, register any missing repository via `helm_ensure_repository` (`open-telemetry` -> `https://open-telemetry.github.io/opentelemetry-helm-charts`, `prometheus-community` -> `https://prometheus-community.github.io/helm-charts`, `grafana` -> `https://grafana.github.io/helm-charts`, `argo` -> `https://argoproj.github.io/argo-helm`, `traefik` -> `https://traefik.github.io/charts`, `talkops` -> `https://talkops-ai.github.io/OTEL-APP`).
- [ ] **Check Chart Breaking Changes:** Read `helm://charts/{repository}/{chart}/readme` and `helm://charts/{repository}/{chart}/values` when upgrading across major or minor chart versions.
- [ ] **Run `helm_plan_release`:** Review `added_resources`, `removed_resources`, `modified_resources`, `image_changes`, and `replica_changes`.

## 2. Selecting `values_strategy` in `helm_upgrade_release`

| `values_strategy` | Helm CLI Flag | When to Use |
|---|---|---|
| `reuse` *(default)* | `--reuse-values` | Incremental config patch (e.g., changing replica count or image tag) while keeping all previously set user overrides on the same chart version. |
| `reset_then_reuse` | `--reset-then-reuse-values` | Upgrading to a **new chart version** where new default keys were added in upstream `values.yaml`, while still preserving existing user overrides. |
| `reset` | `--reset-values` | Replacing all previous overrides with the chart's built-in defaults plus only the newly supplied `values` dict. |

## 3. StatefulSet & CRD Upgrade Caveats

- **Immutable StatefulSet Fields:** Kubernetes prohibits mutating `volumeClaimTemplates`, `serviceName`, or `podManagementPolicy` on an existing StatefulSet. If `helm_plan_release` shows modifications to a StatefulSet's PVC template, the upgrade will fail with `Forbidden: updates to statefulset spec for fields other than 'replicas', 'template', 'updateStrategy' are forbidden`.
- **CRDs Are Not Upgraded by Helm:** Helm skips the `crds/` directory during `helm upgrade`. Whenever evaluating or executing an Operator/CRD chart upgrade, immediately inspect `helm://charts/{repository}/{chart}/readme` for version-specific CRD upgrade steps and call `kubernetes_check_prerequisites(required_api_resources=[...])` to verify whether the required CRDs exist on the cluster; apply updated CRDs out-of-band before running `helm_plan_release` and `helm_upgrade_release`.
