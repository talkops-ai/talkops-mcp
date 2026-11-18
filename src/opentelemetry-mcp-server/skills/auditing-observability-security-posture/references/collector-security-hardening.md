# OpenTelemetry Collector Security Hardening Guide

## Table of Contents

1. [Externalizing Secrets via Kubernetes `secretKeyRef` (`SEC_PLAINTEXT_SECRET`)](#1-externalizing-secrets-via-kubernetes-secretkeyref-sec_plaintext_secret)
2. [Enforcing TLS Verification & mTLS (`SEC_INSECURE_TLS`)](#2-enforcing-tls-verification--mtls-sec_insecure_tls)
3. [Securing Receiver Bindings (`SEC_BIND_ALL_INTERFACES_NO_AUTH`)](#3-securing-receiver-bindings-sec_bind_all_interfaces_no_auth)
4. [Least-Privilege Kubernetes RBAC (`SEC_OVERPRIVILEGED_RBAC`)](#4-least-privilege-kubernetes-rbac-sec_overprivileged_rbac)
5. [Pod Security Standards (Restricted / Non-Root Collector Containers)](#5-pod-security-standards-restricted--non-root-collector-containers)

---

## 1. Externalizing Secrets via Kubernetes `secretKeyRef` (`SEC_PLAINTEXT_SECRET`)

Never store literal API keys, bearer tokens, or basic-auth passwords in `OpenTelemetryCollector.spec.config`.
1. Create a Kubernetes `Secret` containing the token (e.g., key `api-key`).
2. Mount the secret into `spec.env` using `valueFrom.secretKeyRef`.
3. Reference `${env:OTEL_EXPORTER_AUTH_TOKEN}` inside `exporters.*.headers.Authorization`:

```yaml
exporters:
  otlphttp:
    endpoint: https://otlp.vendor.example.com
    headers:
      Authorization: "Bearer ${env:OTEL_EXPORTER_AUTH_TOKEN}"
```

`otel_provision_collector` and `otel_patch_collector` automatically enforce this pattern and redact any residual secret patterns on read via `otel://collector/{namespace}/{name}/config`.

---

## 2. Enforcing TLS Verification & mTLS (`SEC_INSECURE_TLS`)

- Only set `tls.insecure: true` when communicating with an in-cluster plaintext service (`*.svc.cluster.local`) over a trusted CNI or service mesh.
- For all external or cross-cluster `https://` endpoints, set `tls.insecure: false` and never set `tls.insecure_skip_verify: true`.
- If the backend uses a private PKI CA, mount the CA certificate Secret and set `tls.ca_file: /etc/otel/certs/ca.crt`.

---

## 3. Securing Receiver Bindings (`SEC_BIND_ALL_INTERFACES_NO_AUTH`)

- Diagnostic extensions (`pprof`, `zpages`) should bind to `127.0.0.1` (`localhost`), never `0.0.0.0`.
- When exposing OTLP receivers outside the cluster via an Ingress or LoadBalancer, attach `bearertokenauth` or `oidc` authenticator extensions:

```yaml
extensions:
  oidc:
    issuer_url: https://dex.example.com
    audience: otel-collector
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
        auth:
          authenticator: oidc
```

---

## 4. Least-Privilege Kubernetes RBAC (`SEC_OVERPRIVILEGED_RBAC`)

OpenTelemetry Collectors are **read-only** consumers of Kubernetes metadata (`get`, `list`, `watch`).
- A Collector `ClusterRole` must **never** include `create`, `update`, `patch`, `delete`, or `*` verbs, nor `secrets` access.
- `otel_audit_security_posture` flags any Collector `ClusterRole` granting write verbs or wildcard resources with `SEC_OVERPRIVILEGED_RBAC`.

---

## 5. Pod Security Standards (Restricted / Non-Root Collector Containers)

For Gateway and StatefulSet Collectors that do not read `/var/log/pods` from the host node:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  seccompProfile:
    type: RuntimeDefault
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
```
