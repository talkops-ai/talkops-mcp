# cert-manager vs Traefik ACME Resolver Patterns

## Table of Contents

1. [Multi-Replica Kubernetes Best Practice (`cert-manager`)](#1-multi-replica-kubernetes-best-practice-cert-manager)
2. [Traefik Built-In ACME `certResolver` Caveats](#2-traefik-built-in-acme-certresolver-caveats)
3. [Wildcard Certificates & RFC 6125 Matching Rules](#3-wildcard-certificates--rfc-6125-matching-rules)

## 1. Multi-Replica Kubernetes Best Practice (`cert-manager`)

In multi-replica Kubernetes deployments (`replicas >= 2`), Traefik's open-source local ACME `storage` (`acme.json`) is not distributed across pods and can trigger Let's Encrypt rate limits or race conditions.
- **Recommended Pattern**: Issue certificates via `cert-manager` (`Certificate` CRD -> `kubernetes.io/tls` `Secret`) and reference `tls.secret_name` on each `IngressRoute` (or `default_certificate_secret` on the namespace `TLSStore`).
- Read `traefik://certificates/{namespace}` to verify both the `Secret` X.509 metadata and the backing `cert_manager.ready` condition.

## 2. Traefik Built-In ACME `certResolver` Caveats

Use `tls.cert_resolver` on `IngressRoute` only when:
- Traefik runs as a single replica with a persistent volume for `acme.json`, or
- The resolver name is verified in `traefik://instance/static-config` under `certificatesResolvers`.

## 3. Wildcard Certificates & RFC 6125 Matching Rules

Per RFC 6125:
- `*.example.com` covers `api.example.com` and `web.example.com` (single left-most label).
- `*.example.com` does **not** cover the apex `example.com` (include `example.com` as an explicit SAN) and does **not** cover nested subdomains like `a.b.example.com`.
