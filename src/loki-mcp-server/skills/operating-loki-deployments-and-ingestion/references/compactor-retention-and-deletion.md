# Loki Compactor Retention and Log Deletion Reference

## Table of Contents
1. [Compactor Retention Configuration](#1-compactor-retention-configuration)
2. [Per-Tenant and Per-Stream Retention Policies](#2-per-tenant-and-per-stream-retention-policies)
3. [Safe PII / Secret Log Deletion Runbook (`/loki/api/v1/delete`)](#3-safe-pii--secret-log-deletion-runbook-lokiapiv1delete)

---

## 1. Compactor Retention Configuration

In Loki 3.x, the **Compactor** is solely responsible for enforcing retention and executing log deletion requests:

```yaml
compactor:
  working_directory: /var/loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150
  delete_request_store: s3
```
> **Important**: `delete_request_store` must be set to your object store (`s3`, `gcs`, `azure`) for `/loki/api/v1/delete` endpoints and `loki_manage_delete_requests` to function.

---

## 2. Per-Tenant and Per-Stream Retention Policies

Define default retention and stream-specific overrides under `limits_config`:

```yaml
limits_config:
  retention_period: 30d
  retention_stream:
    - selector: '{namespace="audit"}'
      priority: 10
      period: 365d
    - selector: '{env="dev"}'
      priority: 5
      period: 7d
    - selector: '{service_name="envoy-access"} |= "healthz"'
      priority: 1
      period: 24h
```

---

## 3. Safe PII / Secret Log Deletion Runbook (`/loki/api/v1/delete`)

When a secret token, password, or GDPR-protected PII is accidentally logged:
1. **Verify Exact Blast Radius First**:
   - Run a read-only `loki_query_range` with the exact stream selector and line filter (`{service_name="auth"} |= "leaked_secret_xyz"`) to verify how many lines match and confirm no critical unrelated logs match.
2. **Preview the Delete Request (`dry_run=True`)**:
   - Call `loki_manage_delete_requests(action="create", query='{service_name="auth"} |= "leaked_secret_xyz"', start="now-24h", end="now", dry_run=True)`.
3. **Execute with Confirmation (`dry_run=False, confirm=True`)**:
   - Call `loki_manage_delete_requests(action="create", ..., dry_run=False, confirm=True)`.
4. **Verify Status**:
   - Read `loki://compactor/delete-requests` to confirm the request is registered (`status: "received"` -> `"processed"`).
