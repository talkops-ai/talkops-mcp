# Helm Values Authoring & Best Practices Reference

## Table of Contents

1. [Values Structure & Naming Conventions](#1-values-structure--naming-conventions)
2. [Image Pinning & Pull Policies](#2-image-pinning--pull-policies)
3. [Resource Requests, Limits & Autoscaling](#3-resource-requests-limits--autoscaling)
4. [Secret & Credential Handling](#4-secret--credential-handling)
5. [Persistence & StorageClass Configuration](#5-persistence--storageclass-configuration)
6. [Labels, Annotations & Pod Disruption Budgets](#6-labels-annotations--pod-disruption-budgets)
7. [Custom Resource Definitions (CRDs)](#7-custom-resource-definitions-crds)

---

## 1. Values Structure & Naming Conventions

- Always inspect `helm://charts/{repository}/{chart}/values` before constructing overrides so key nesting matches the chart schema.
- Prefer nested dictionaries over flat dot-notation strings when passing `values` to MCP tools:
  ```json
  {
    "replicaCount": 3,
    "service": {
      "type": "ClusterIP",
      "port": 8080
    }
  }
  ```
- Explicitly type booleans (`true`/`false`) and integers (`8080`) rather than quoting everything unless the chart expects string values.

---

## 2. Image Pinning & Pull Policies

- **Never use `:latest` or floating tags (`main`, `master`, `dev`)** in production values. Always pin an immutable semantic version or SHA256 digest:
  ```json
  {
    "image": {
      "repository": "nginx",
      "tag": "1.27.2-alpine",
      "pullPolicy": "IfNotPresent"
    }
  }
  ```
- Configure `imagePullSecrets` when pulling from private container registries.

---

## 3. Resource Requests, Limits & Autoscaling

- Every production workload must define CPU and memory `requests` and `limits` to prevent noisy-neighbor eviction and `OOMKilled` crashes:
  ```json
  {
    "resources": {
      "requests": {
        "cpu": "250m",
        "memory": "256Mi"
      },
      "limits": {
        "cpu": "1000m",
        "memory": "512Mi"
      }
    }
  }
  ```
- Keep `replicaCount` within reasonable bounds ($1 \le \text{replicas} \le 100$) or enable HorizontalPodAutoscaler (`autoscaling.enabled: true`) with explicit `minReplicas` and `maxReplicas`.

---

## 4. Secret & Credential Handling

- **Never hardcode plaintext passwords, API keys, or TLS private keys** inside values overrides, and never fetch raw secret values from external secret managers (`aws secretsmanager`, `vault`) into shell/LLM conversation transcripts. Plaintext values are persisted inside Helm release `Secret` objects (`sh.helm.release.v1.*`) in Kubernetes `etcd` and exposed in rendered manifests and audit logs.
- Provision secrets out-of-band (e.g., via External Secrets Operator `ExternalSecret` or SealedSecrets) and reference pre-existing Kubernetes Secrets wherever supported by the chart (e.g., `auth.existingSecret`, `existingSecret`, `secretName`, `secretKeyRef`):
  ```json
  {
    "auth": {
      "existingSecret": "postgres-prod-credentials",
      "secretKeys": {
        "adminPasswordKey": "postgres-password"
      }
    }
  }
  ```

---

## 5. Persistence & StorageClass Configuration

- For stateful workloads (databases, queues), verify whether `persistence.enabled` is true and whether a specific `storageClass` is required by the cluster:
  ```json
  {
    "primary": {
      "persistence": {
        "enabled": true,
        "storageClass": "gp3",
        "size": "20Gi"
      }
    }
  }
  ```

---

## 6. Labels, Annotations & Pod Disruption Budgets

- Apply standard Kubernetes labels (`app.kubernetes.io/part-of`, `app.kubernetes.io/environment`) via `commonLabels` or `podLabels`.
- Enable `podDisruptionBudget` (`minAvailable: 1` or `maxUnavailable: 1`) for multi-replica production services.

---

## 7. Custom Resource Definitions (CRDs)

- Helm installs files in `crds/` only on initial `helm install` (unless `skip_crds=True` is set) and does **not** upgrade or delete CRDs automatically.
- When multiple releases in the same cluster share CRDs (such as `argo-cd` or `cert-manager`), pass `skip_crds=True` on secondary installations to avoid `invalid ownership metadata` errors.
