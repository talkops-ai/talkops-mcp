# Helm & Kubernetes Workload Security Checklist

## Table of Contents

1. [Pod & Container Security Context](#1-pod--container-security-context)
2. [Image Supply Chain & Registry Security](#2-image-supply-chain--registry-security)
3. [Secrets & Credential Management](#3-secrets--credential-management)
4. [RBAC & ServiceAccount Least Privilege](#4-rbac--serviceaccount-least-privilege)
5. [Network Policies & Service Exposure](#5-network-policies--service-exposure)
6. [Resource Quotas & Denial-of-Service Protection](#6-resource-quotas--denial-of-service-protection)

---

## 1. Pod & Container Security Context

Align all workloads with the Kubernetes **Restricted** Pod Security Standard where possible:
- [ ] `securityContext.runAsNonRoot: true` and explicit non-zero `runAsUser` (e.g., `1001`).
- [ ] `containerSecurityContext.privileged: false` and `allowPrivilegeEscalation: false`. Never use a `privileged: true` `initContainer` to fix volume ownership (`chown`); replace permission-fixing `initContainers` with `podSecurityContext.fsGroup` and `runAsUser`.
- [ ] `containerSecurityContext.readOnlyRootFilesystem: true` (mount `emptyDir` for `/tmp` if required).
- [ ] Drop all Linux capabilities (`capabilities.drop: ["ALL"]`) and add back only explicitly required capabilities.
- [ ] Never enable `hostNetwork: true`, `hostPID: true`, `hostIPC: true`, or `hostPath` volumes unless deploying a vetted node-level DaemonSet.

---

## 2. Image Supply Chain & Registry Security

- [ ] Pin immutable image tags or SHA256 digests (`image.tag: "1.27.2"` or `image.digest: "sha256:..."`); never use `:latest`.
- [ ] Use trusted registries and configure `imagePullSecrets` for private repositories.

---

## 3. Secrets & Credential Management

- [ ] Never pass plaintext passwords, tokens, or TLS private keys in inline Helm `values`.
- [ ] Use `ExternalSecret` objects (External Secrets Operator), Sealed Secrets, or CSI Secret Store referenced via `existingSecret` / `secretKeyRef`, and provision TLS certificates via `cert-manager` `Certificate` resources referenced by Kubernetes TLS `secretName`.
- [ ] Note that the Helm MCP Server automatically redacts `Secret.data` / `Secret.stringData` and sensitive keys (`***REDACTED***`, `secrets_redacted: true`) in `helm_render_manifests`, `helm://releases/{namespace}/{release}/values`, and `helm://releases/{namespace}/{release}/manifest`.

---

## 4. RBAC & ServiceAccount Least Privilege

- [ ] Ensure `serviceAccount.create: true` creates a dedicated ServiceAccount per release rather than using the `default` ServiceAccount.
- [ ] Set `automountServiceAccountToken: false` on workloads that do not communicate with the Kubernetes API server.
- [ ] Prefer namespace-scoped `Role` and `RoleBinding` over cluster-wide `ClusterRole` and `ClusterRoleBinding`.
- [ ] Prohibit wildcard permissions (`verbs: ["*"]`, `resources: ["*"]`).

---

## 5. Network Policies & Service Exposure

- [ ] Default `service.type` to `ClusterIP`; avoid `LoadBalancer` or `NodePort` unless external exposure is explicitly intended and authenticated.
- [ ] Enable chart-provided `networkPolicy.enabled: true` to restrict ingress and egress traffic to required peers.
- [ ] Enforce TLS on all `Ingress` resources.

---

## 6. Resource Quotas & Denial-of-Service Protection

- [ ] Specify `resources.requests.cpu`, `resources.requests.memory`, `resources.limits.cpu`, and `resources.limits.memory` on every container and initContainer.
