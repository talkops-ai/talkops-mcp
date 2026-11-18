# Zero-Downtime Certificate Rotation Runbook

## Table of Contents

1. [Pre-Rotation Verification](#1-pre-rotation-verification)
2. [Swapping `secretName` on `IngressRoute`](#2-swapping-secretname-on-ingressroute)
3. [Post-Rotation Verification](#3-post-rotation-verification)

## 1. Pre-Rotation Verification

1. Read `traefik://certificates/{namespace}` to confirm the replacement TLS Secret exists and has:
   - `expired: false` and `days_remaining >= 30`
   - `is_traefik_default_cert: false`
   - Complete SAN coverage for every hostname on the target route (`traefik://routes/{namespace}`).

## 2. Swapping `secretName` on `IngressRoute`

1. Preview the TLS Secret swap via `traefik_update_route(name=..., namespace=..., changes={"tls": {"secret_name": "new-tls-secret"}}, dry_run=True)`.
2. **`[GATE]`** Present the diff and SAN coverage verification to the operator.
3. Apply with `traefik_update_route(..., dry_run=False)`. Traefik hot-reloads the certificate from the Kubernetes Secret watch without dropping active connections.

## 3. Post-Rotation Verification

1. Run `traefik_diagnose_route(name=..., namespace=..., include=["tls", "runtime"])` and confirm `healthy: true` with zero `TLS_CERT_EXPIRED`, `TLS_CERT_EXPIRING`, or `TLS_SAN_MISMATCH` codes.
