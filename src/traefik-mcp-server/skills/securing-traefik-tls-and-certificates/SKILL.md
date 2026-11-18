---
name: securing-traefik-tls-and-certificates
description: Configures and audits Traefik v3 TLSOptions, default TLSStores, mutual TLS (mTLS) client and backend certificate verification, RFC 6125 wildcard SAN coverage, cert-manager vs ACME certResolvers, and zero-downtime X.509 certificate rotation on Kubernetes. Use when hardening TLS versions and cipher suites, configuring client-to-Traefik or Traefik-to-backend mTLS, rotating expiring TLS Secrets, inspecting public X.509 PEM certificates, or evaluating sniStrict blast radius. Do not use for L4 TCP HostSNI TLS passthrough routing (use routing-traefik-tcp-and-udp), non-TLS HTTP middlewares like rateLimit/circuitBreaker (use configuring-traefik-middlewares), cluster-wide 20-check security posture scoring (use auditing-traefik-security-posture), or Kargo Git/OCI credential management (use managing-kargo-credentials-and-access).
---

# Securing Traefik v3 TLS & Certificates

This skill governs TLS termination, Mozilla `modern`/`intermediate` `TLSOption` policies, `default` `TLSStore` fallback certificates, client and backend mutual TLS (`mTLS`), HA `cert-manager` vs `acme.json` architecture, and zero-downtime X.509 certificate rotation on Kubernetes (`traefik.io/v1alpha1`).

## Preconditions & Zero-Private-Key Boundary

1. **Strict Zero-Private-Key Rule**: **Never** read, base64-decode, print, or pass `tls.key` private key material via `kubectl get secret`, shell commands, or files. Always inspect sanitized public certificate metadata via `traefik://certificates/{namespace}` (or `traefik://certificates/_all` across namespaces) and [inspect_certificate.py](scripts/inspect_certificate.py) on public `tls.crt` PEM data only.
2. Read `traefik://server/capabilities` and `traefik://cluster/contexts` to verify `cluster_connected`, `allow_write`, active `toolsets`, and kubeconfig context.
3. Read `traefik://instance/static-config` to inspect replica count (`replicas >= 2` makes local `acme.json` unsafe in Traefik OSS—enforce `cert-manager` `Certificate` -> `kubernetes.io/tls` Secrets!) and `certificatesResolvers`.
4. Read `traefik://certificates/{namespace}` (or `traefik://certificates/_all`), `traefik://policies/{namespace}`, and `traefik://manifests/{kind}/{namespace}/{name}` (instead of `kubectl get ... -o yaml`) to inspect SANs, `days_remaining`, `is_traefik_default_cert`, and route blast radius. If the operator invokes `/onboard` (or `--gitops argocd`), read `commands/onboard.md` first, inspect the ArgoCD `Application` source/repo, and explicitly explain how to commit the rendered `TLSOption` + `IngressRoute` manifests into the ArgoCD GitOps repository / Helm chart templates so ArgoCD reconciles them declaratively without GitOps drift.

## Execution Checklist

- [ ] **Step 1 — Inventory certificates, policies & static config**: Read `traefik://server/capabilities`, `traefik://instance/static-config`, `traefik://certificates/{namespace}` (or `_all`), and `traefik://policies/{namespace}` (plus `traefik://manifests/{kind}/{namespace}/{name}` for target routes/policies).
- [ ] **Step 2 — Consult TLS references & run deterministic X.509 / SAN scripts**: Read the relevant reference guide under `references/` and execute [check_host_coverage.py](scripts/check_host_coverage.py) or [inspect_certificate.py](scripts/inspect_certificate.py) when verifying RFC 6125 wildcard SAN matching or PEM metadata.
- [ ] **Step 3 — Verify SAN coverage, namespace locality & expiry**: Confirm target `Secret` lives in the same namespace (unless cross-namespace references are explicitly enabled), covers every route hostname under RFC 6125 single-leftmost-label rules, is not `TRAEFIK DEFAULT CERT`, and has `days_remaining >= 30` when rotating.
- [ ] **Step 4 — Preview TLS policy or route rotation (`dry_run=True`)**: Call `traefik_configure_tls_policy`, `traefik_configure_servers_transport`, or `traefik_update_route` with `dry_run=True`.
- [ ] **Step 5 — `[GATE]` Apply or hold safely**:
  - If a global policy change (`TLSOption/default` with `sniStrict: true` or `TLSStore/default`) would break routes missing valid SAN certificates (`TLS_SECRET_MISSING` / `TLS_SAN_MISMATCH`), or if asked to extract `tls.key`, **halt and refuse/warn** until prerequisites are fixed.
  - When the operator explicitly requested creating, rotating, or binding a safe TLS policy live, **proceed immediately in the same turn** from `dry_run=True` to `dry_run=False` (passing `confirm=True` when mutating `TLSStore/default` or `TLSOption/default`).
- [ ] **Step 6 — Verify runtime TLS binding**: Run `traefik_diagnose_route(..., include=["tls", "runtime", "events"])` and document instant rollback steps when rotating Secrets.

## Core Workflows

### 1. Hardening `TLSOption` Baselines (`modern` & `intermediate`) & `sniStrict` Blast Radius

Consult [tls-option-baselines.md](references/tls-option-baselines.md) for Mozilla `intermediate` (`VersionTLS12` + 6 AEAD ECDHE cipher suites + `sniStrict: True`) and `modern` (`VersionTLS13` + `sniStrict: True` + `alpnProtocols: ["h2", "http/1.1"]`).

1. Before enabling `sniStrict: true`—especially on `TLSOption/default` (which applies cluster-wide to every HTTPS router without an explicit `TLSOption`)—inspect `traefik://routes/_all` and `traefik://certificates/_all` (and run `traefik_diagnose_route`) to verify **every** HTTPS route has a loaded, SAN-matching certificate. With `sniStrict: true`, Traefik aborts TLS handshakes (`unrecognized_name` / `421`) rather than serving a fallback certificate!
2. Verify RFC 6125 wildcard SAN coverage deterministically via [check_host_coverage.py](scripts/check_host_coverage.py) (`*.example.com` matches `shop.example.com` ONLY—never apex `example.com` and never multi-level `us.shop.example.com`). **Always warn explicitly in your response** that any uncovered host triggers `TLS_SAN_MISMATCH`, and enabling `sniStrict: true` with uncovered hosts causes **immediate TLS handshake rejections** (`tls: unrecognized name` / `TLS_SAN_MISMATCH`) rather than falling back to a default certificate:
   ```bash
   python3 .agents/skills/securing-traefik-tls-and-certificates/scripts/check_host_coverage.py --hosts "shop.otel-demo.talkops.io,otel-demo.talkops.io,us.shop.otel-demo.talkops.io" --sans "*.otel-demo.talkops.io,otel-demo.talkops.io"
   ```
3. Preview `traefik_configure_tls_policy(kind="TLSOption", name=..., namespace=..., spec={"profile": "modern"|"intermediate", "sni_strict": True, ...}, dry_run=True)`, apply with `dry_run=False, confirm=True`, attach via `traefik_update_route(name=..., namespace=..., changes={"tls": {"options": {"name": ..., "namespace": ...}}}, dry_run=True -> False)`, and verify via `traefik_diagnose_route(..., include=["tls", "runtime"])`.

### 2. Client mTLS (`TLSOption.clientAuth`) & Backend mTLS (`ServersTransport`)

Consult [mtls-client-auth.md](references/mtls-client-auth.md).

1. **Client-to-Traefik mTLS**: `TLSOption.spec.clientAuth.secretNames` must reference CA `Secret` names in the **same namespace** as the `TLSOption` (cross-namespace `"ns/secret"` strings fail unless replicated into the target namespace; always note explicitly that `clientAuth` CA Secrets store **only public root/intermediate CA certificates (`ca.crt` / `tls.ca`)—no private keys**—so replicating the CA Secret into the target namespace is safe). Configure `client_auth={"client_auth_type": "RequireAndVerifyClientCert", "secret_names": ["<ca-secret>"]}` via `traefik_configure_tls_policy(..., dry_run=True -> False)`. When forwarding client cert identity upstream, create a `pass_tls_client_cert` Middleware with `pem: False` and structured `info` fields (`subject`, `serialNumber`) so raw PEM blobs aren't leaked in headers, and attach both to the route via `traefik_update_route`.
2. **Traefik-to-Backend mTLS Re-Encryption**: Configure `traefik_configure_servers_transport(name=..., protocol="http", namespace=..., spec={"server_name": "<sni>", "root_cas": ["<ca-secret>"], "certificates": ["<client-cert-secret>"], "insecure_skip_verify": False}, dry_run=True -> False)`.

### 3. Default `TLSStore`, HA `cert-manager` & Zero-Downtime Certificate Rotation

Consult [cert-rotation-runbook.md](references/cert-rotation-runbook.md) and [cert-manager-and-acme-patterns.md](references/cert-manager-and-acme-patterns.md).

1. **`TLSStore/default` Rule & `[GATE]` Cluster-Wide Blast Radius**: Traefik **only** honors a `TLSStore` named `default` (any other name such as `otel-wildcard-store` is silently ignored). Mutating `TLSStore/default` in the Traefik controller namespace has **cluster-wide blast radius** across every HTTPS router that omits an explicit `tls.secretName`—always verify the certificate's SANs, `days_remaining`, and non-default issuer in `traefik://certificates/{namespace}` first, preview with `dry_run=True`, include an explicit **`[GATE]` cluster-wide blast-radius warning** in your response, and pass `confirm=True` on `dry_run=False`.
2. **HA `cert-manager` vs `acme.json`**: Never use local `acme.json` file storage across `replicas >= 2` in Traefik OSS (causes concurrent Let's Encrypt challenge races and rate-limit lockouts). Always read `traefik://routes/_all` first to map the affected hostnames to their exact Kubernetes route namespaces (e.g., `otel-demo` and `observability`), and recommend `cert-manager` `Issuer`/`ClusterIssuer` + `Certificate` resources writing `kubernetes.io/tls` Secrets referenced via `tls.secretName` in each route's namespace (such as `otel-demo` and `observability`).
3. **Zero-Downtime Secret Rotation & Offline PEM Inspection**: Verify the new Secret in `traefik://certificates/{namespace}` (`expired: false`, `days_remaining >= 30`, `is_traefik_default_cert: false`, full SAN coverage), switch `changes={"tls": {"secret_name": "<new-secret>"}}` via `traefik_update_route(..., dry_run=True -> False)`, verify via `traefik_diagnose_route(..., include=["tls", "runtime"])`, and document instant rollback to `<old-secret>`. For offline public `tls.crt` PEM files, run [inspect_certificate.py](scripts/inspect_certificate.py):
   ```bash
   python3 .agents/skills/securing-traefik-tls-and-certificates/scripts/inspect_certificate.py --cert-file <public-tls.crt>
   ```

## Reference Documentation

- [Mozilla Modern and Intermediate TLSOption Baselines](references/tls-option-baselines.md)
- [cert-manager vs Traefik ACME Resolver Patterns](references/cert-manager-and-acme-patterns.md)
- [Mutual TLS (mTLS) Client Authentication Guide](references/mtls-client-auth.md)
- [Zero-Downtime Certificate Rotation Runbook](references/cert-rotation-runbook.md)
