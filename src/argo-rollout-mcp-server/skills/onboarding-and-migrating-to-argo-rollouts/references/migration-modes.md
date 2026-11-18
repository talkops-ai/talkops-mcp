# Migration Modes: `direct` vs. `workload_ref`

## Overview

When migrating an existing Kubernetes `Deployment` to an Argo `Rollout`, `argo_convert_deployment_to_rollout` (and `scripts/convert_deployment_to_rollout.py`) supports two migration modes:

| Dimension | `workload_ref` (Recommended for Production) | `direct` (Standalone Rollout) |
|---|---|---|
| **Pod Template Location** | Remains on the existing `Deployment`; Rollout uses `spec.workloadRef` | Copied directly into `Rollout.spec.template` |
| **Duplicate Pod Window** | Controlled automatically by `workloadRef.scaleDown` (`onsuccess` or `progressively`) | Runs 2x pods until you manually scale/delete the legacy Deployment |
| **Rollback Safety** | High — `argo_delete_rollout` blocks deletion if the referenced Deployment has 0 replicas | Manual — use `argo_convert_rollout_to_deployment` before deleting the Rollout |
| **GitOps Compatibility** | Requires ignoring `/spec/replicas` on the `Deployment` in ArgoCD | Requires replacing `Deployment` with `Rollout` in Git or scaling `Deployment` to 0 |

## Scale-Down Policies for `workload_ref`

- `never`: Keeps both the Deployment and Rollout running at full replica count until changed.
- `onsuccess` (Default): Scales the referenced Deployment down to 0 only after the Rollout reaches `Healthy`.
- `progressively`: Scales down the referenced Deployment proportionally as the Rollout scales up ReplicaSets.

## Service Cloning and Named `targetPort` Resolution

Argo Rollouts requires a pair of Kubernetes `Service` objects:
- **Canary**: `{app}-stable` and `{app}-canary`
- **Blue-Green**: `{app}-active` and `{app}-preview`

### Why Numeric `targetPort` Matters
If your existing Service uses a named `targetPort` (e.g., `targetPort: http`) and a subsequent Helm/ArgoCD sync overwrites the pod template without named container ports, Kubernetes endpoint resolution fails with `502 Bad Gateway`.
- `argo_convert_deployment_to_rollout` automatically inspects `spec.template.spec.containers[*].ports[*]` and resolves named `targetPort` references to their numeric `containerPort` (e.g., `8080`).
- Runtime controller labels (`pod-template-hash` and `rollouts-pod-template-hash`) are stripped from cloned Service selectors so the Argo Rollouts controller can dynamically manage ReplicaSet pinning.
