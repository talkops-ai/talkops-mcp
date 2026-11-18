# Helm & Kubernetes Workload Error Catalog

## Table of Contents

1. [Container Runtime Failures (`CrashLoopBackOff`, `OOMKilled`, `CreateContainerConfigError`)](#1-container-runtime-failures-crashloopbackoff-oomkilled-createcontainerconfigerror)
2. [Image Pull Failures (`ImagePullBackOff`, `ErrImagePull`, `InvalidImageName`)](#2-image-pull-failures-imagepullbackoff-errimagepull-invalidimagename)
3. [Pod Scheduling & Pending Failures (`FailedScheduling`, `Unbound PVC`)](#3-pod-scheduling--pending-failures-failedscheduling-unbound-pvc)
4. [Helm Install & Upgrade Conflicts (`CRD Ownership`, `Release Exists`, `Pending Lock`)](#4-helm-install--upgrade-conflicts-crd-ownership-release-exists-pending-lock)
5. [Kubernetes API, Prerequisite & Repository Resolution](#5-kubernetes-api-prerequisite--repository-resolution)

---

## 1. Container Runtime Failures (`CrashLoopBackOff`, `OOMKilled`, `CreateContainerConfigError`)

### `CrashLoopBackOff`
- **Symptoms:** `helm_monitor_deployment` reports `reason: "CrashLoopBackOff"` on `pod/<name>/container/<container>`.
- **Common Causes:**
  1. Missing required environment variables or database connection URLs in Helm values.
  2. Liveness probe configured on the wrong port/path or with too short an `initialDelaySeconds`.
  3. Read-only root filesystem (`readOnlyRootFilesystem: true`) blocking writes to `/tmp` or `/var/run` without an `emptyDir` mount. **Never weaken security by setting `readOnlyRootFilesystem: false`**; always keep `readOnlyRootFilesystem: true` and mount `emptyDir: {}` volumes at writable runtime paths (`/tmp`, `/var/run`, cache directories).
- **Remediation:**
  - Read `helm://releases/{namespace}/{release}/values` and `helm://releases/{namespace}/{release}/manifest`.
  - Compare against `helm://charts/{repository}/{chart}/values` and `helm://charts/{repository}/{chart}/readme`.
  - Patch values via `helm_upgrade_release` or rollback via `helm_rollback_release`.

### `OOMKilledRecurring`
- **Symptoms:** `helm_monitor_deployment` reports `reason: "OOMKilledRecurring"` (container terminated with exit code 137 and $\ge 3$ restarts).
- **Remediation:**
  - Increase `resources.limits.memory` (and `resources.requests.memory`) in the chart values and apply with `helm_upgrade_release`.

### `CreateContainerConfigError`
- **Symptoms:** Pod remains in `Pending`/`ContainerCreating` with `reason: "CreateContainerConfigError"`.
- **Common Causes:** Referenced Kubernetes `Secret` or `ConfigMap` (such as `existingSecret`) does not exist in the target namespace, or a required key is missing from the Secret.
- **Remediation:** Verify the secret name and keys in `helm://releases/{namespace}/{release}/values`.

---

## 2. Image Pull Failures (`ImagePullBackOff`, `ErrImagePull`, `InvalidImageName`)

- **Symptoms:** `helm_monitor_deployment` reports `reason: "ImagePullBackOff"`, `"ErrImagePull"`, or `"InvalidImageName"`.
- **Common Causes:**
  1. Typo in `image.repository` or `image.tag` in user values.
  2. Chart default tag does not exist for the target architecture (`arm64` vs `amd64`).
  3. Private registry requires `imagePullSecrets` which were omitted.
- **Remediation:**
  - Inspect `helm://releases/{namespace}/{release}/manifest` to see the exact rendered `image:` string.
  - Update `image.repository` / `image.tag` / `imagePullSecrets` via `helm_upgrade_release`.

---

## 3. Pod Scheduling & Pending Failures (`FailedScheduling`, `Unbound PVC`)

- **Symptoms:** `helm_monitor_deployment` reports `reason: "Unschedulable"` or `"SchedulingFailed"` on `pod/<name>`, or `status: "timeout"` with `pod_summary.pending > 0`.
- **Common Causes:**
  1. `Insufficient cpu` or `Insufficient memory` across cluster nodes.
  2. `pod has unbound immediate PersistentVolumeClaims` — missing default `StorageClass` or invalid `storageClass` name in values.
  3. Node selector (`nodeSelector`), `affinity`, or `tolerations` do not match any node in `kubernetes://cluster-info`.
- **Remediation:**
  - Right-size `resources.requests`, set a valid `storageClass` (or disable persistence for ephemeral dev environments), and upgrade the release.

---

## 4. Helm Install & Upgrade Conflicts (`CRD Ownership`, `Release Exists`, `Pending Lock`)

### CRD Ownership Conflict (`invalid ownership metadata`)
- **Symptoms:** `helm_install_chart` fails with `rendered manifests contain a resource that already exists` or `invalid ownership metadata; annotation validation error: key "meta.helm.sh/release-name" must equal "..."`.
- **Cause:** Another release in the cluster already installed the chart's cluster-scoped CRDs.
- **Remediation:**
  1. Call `helm_list_releases()` across all namespaces to identify the release managing the CRDs.
  2. **Never delete shared cluster CRDs** (`kubectl delete crd ...` or uninstalling CRD definitions) to bypass an ownership error—deleting a CRD immediately cascade-deletes every Custom Resource instance of that kind across all namespaces in the cluster.
  3. Reuse/upgrade the existing owning release, or re-run `helm_install_chart` with `skip_crds=True` if a secondary release is required and existing CRDs are version-compatible.

### Release Already Exists (`cannot re-use a name that is still in use`)
- **Symptoms:** `helm_install_chart` fails because the release name already exists in the namespace.
- **Remediation:**
  1. Call `helm_get_release_status(release_name="<release>", namespace="<ns>")` and read `helm://releases/{namespace}/{release}/history`.
  2. If `status == "deployed"`, use `helm_plan_release` + `helm_upgrade_release` instead of `helm_install_chart`.
  3. If `status == "failed"` at revision `1` with zero prior `deployed` revisions, call `helm_uninstall_release(release_name="<release>", namespace="<ns>", keep_history=False)` to free the release name, **always preview the clean chart first via `helm_plan_release`**, then call `helm_install_chart` and verify readiness via `helm_monitor_deployment`.

---

## 5. Kubernetes API, Prerequisite & Repository Resolution

- **API / `kubeVersion` Mismatches:** When `helm_install_chart` or `helm_upgrade_release` fails with `chart requires kubeVersion: >=1.xx.0` or `no matches for kind "..." in version "..."`, call `kubernetes_check_prerequisites(min_kubernetes_version="<ver>", required_api_resources=["<Kind>"])` and inspect `helm://charts/{repository}/{chart}/readme`; block retrying installation until missing CRDs or version requirements are satisfied.
- **Resolving `<repo>/<chart>` for `helm_plan_release` / `helm_upgrade_release`:** Because Helm release Secrets store `<chart>-<version>` without the source repository URL, check `helm://repositories` before planning an upgrade and call `helm_ensure_repository` if the canonical repository is missing (e.g., `open-telemetry` -> `https://open-telemetry.github.io/opentelemetry-helm-charts`, `prometheus-community` -> `https://prometheus-community.github.io/helm-charts`, `grafana` -> `https://grafana.github.io/helm-charts`, `argo` -> `https://argoproj.github.io/argo-helm`, `traefik` -> `https://traefik.github.io/charts`, `jetstack` -> `https://charts.jetstack.io`, `talkops` -> `https://talkops-ai.github.io/OTEL-APP`).
