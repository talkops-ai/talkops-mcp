# Kubernetes Infrastructure Receivers & Least-Privilege RBAC

## Table of Contents
1. [Receiver Placement by Mode](#receiver-placement-by-mode)
2. [Required RBAC Rules by Component](#required-rbac-rules-by-component)
3. [Volume Mounts & Downward API Requirements](#volume-mounts--downward-api-requirements)

## Receiver Placement by Mode

| Receiver | Required Mode | Signal | Purpose |
|---|---|---|---|
| `kubeletstats` | `daemonset` | `metrics` | Node, pod, container, and volume resource metrics from local kubelet `:10250` (`auth_type: serviceAccount`) |
| `hostmetrics` | `daemonset` | `metrics` | Node CPU, memory, disk, filesystem, network, and load metrics via `root_path: /hostfs` |
| `filelog` | `daemonset` | `logs` | Container stdout/stderr logs from `/var/log/pods` with persistent checkpointing in `/var/lib/otelcol/file_storage` |
| `k8s_cluster` | `deployment` (replicas=1) | `metrics` | Cluster-level deployment/node/quota/HPA state metrics (must run as a single replica to prevent duplicate series) |
| `k8sobjects` | `deployment` (replicas=1) | `logs` | Kubernetes `events.k8s.io` watch stream for cluster event correlation |
| `prometheus` (with Target Allocator) | `statefulset` | `metrics` | Sharded `ServiceMonitor` / `PodMonitor` scraping via `targetAllocator.enabled: true` |

## Required RBAC Rules by Component

- **`k8sattributes` processor**:
  - `apiGroups: [""]`, `resources: ["pods", "namespaces", "nodes"]`, `verbs: ["get", "list", "watch"]`
  - `apiGroups: ["apps"]`, `resources: ["replicasets"]`, `verbs: ["get", "list", "watch"]`
  - `apiGroups: ["batch"]`, `resources: ["jobs"]`, `verbs: ["get", "list", "watch"]`
- **`kubeletstats` receiver**:
  - `apiGroups: [""]`, `resources: ["nodes", "nodes/stats", "nodes/metrics", "nodes/proxy"]`, `verbs: ["get", "list", "watch"]`
- **`k8s_cluster` receiver**:
  - `apiGroups: [""]`, `resources: ["events", "namespaces", "nodes", "pods", "replicationcontrollers", "resourcequotas", "services"]`, `verbs: ["get", "list", "watch"]`
  - `apiGroups: ["apps"]`, `resources: ["daemonsets", "deployments", "replicasets", "statefulsets"]`, `verbs: ["get", "list", "watch"]`
  - `apiGroups: ["batch"]`, `resources: ["jobs", "cronjobs"]`, `verbs: ["get", "list", "watch"]`
  - `apiGroups: ["autoscaling"]`, `resources: ["horizontalpodautoscalers"]`, `verbs: ["get", "list", "watch"]`
- **`k8sobjects` receiver**:
  - `apiGroups: ["", "events.k8s.io"]`, `resources: ["events"]`, `verbs: ["get", "list", "watch"]`
- **Target Allocator (`prometheus_ta`)**:
  - `apiGroups: ["monitoring.coreos.com"]`, `resources: ["servicemonitors", "podmonitors", "scrapeconfigs", "probes"]`, `verbs: ["get", "list", "watch"]`

## Volume Mounts & Downward API Requirements

- **`filelog`**: Mount `/var/log/pods` with `readOnly: true` (`SEC_HOSTPATH_WRITABLE` prevention) and `/var/lib/otelcol/file_storage` as `hostPath` (`type: DirectoryOrCreate`) (`CFG_FILELOG_EPHEMERAL_CHECKPOINT` prevention). Always exclude the collector's own logs (`/var/log/pods/{ns}_{name}*/*/*.log`) (`CFG_FILELOG_NO_SELF_EXCLUDE` prevention).
- **`hostmetrics`**: Mount `/` at `/hostfs` with `readOnly: true`.
- **`K8S_NODE_NAME`**: Inject via `valueFrom.fieldRef.fieldPath: spec.nodeName` whenever running in `daemonset` mode or using `kubeletstats`.
