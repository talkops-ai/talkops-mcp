# Mozilla Modern and Intermediate TLSOption Baselines

## Table of Contents

1. [Mozilla Modern Profile (`profile="modern"`)](#1-mozilla-modern-profile-profilemodern)
2. [Mozilla Intermediate Profile (`profile="intermediate"`)](#2-mozilla-intermediate-profile-profileintermediate)
3. [SNI Strictness (`sniStrict: true`)](#3-sni-strictness-snistrict-true)
4. [Default Namespace `TLSOption` Blast Radius](#4-default-namespace-tlsoption-blast-radius)

## 1. Mozilla Modern Profile (`profile="modern"`)

Recommended for internal APIs, mobile clients, and modern browsers supporting TLS 1.3 exclusively:
- `minVersion: VersionTLS13`
- `sniStrict: true`
- `alpnProtocols: ["h2", "http/1.1"]`

## 2. Mozilla Intermediate Profile (`profile="intermediate"`)

Recommended for general public-facing web traffic requiring TLS 1.2 + TLS 1.3 compatibility:
- `minVersion: VersionTLS12`
- `cipherSuites`:
  - `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256`
  - `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`
  - `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384`
  - `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384`
  - `TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256`
  - `TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256`
- `curvePreferences`: `["CurveP521", "CurveP384"]`
- `sniStrict: true`

## 3. SNI Strictness (`sniStrict: true`)

When `sniStrict: false`, Traefik falls back to its auto-generated self-signed certificate (`TRAEFIK DEFAULT CERT`) whenever a client sends an unknown SNI hostname. Enabling `sniStrict: true` rejects handshakes when no matching certificate exists, preventing accidental fallback to untrusted default certificates.

## 4. Default Namespace `TLSOption` Blast Radius

A `TLSOption` named `default` applies globally to all routers that do not specify an explicit `tls.options` reference. Modifying `default` is gated behind `confirm=True` in `traefik_configure_tls_policy`.
