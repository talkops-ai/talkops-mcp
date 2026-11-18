# TCP HostSNI, TLS Passthrough, and PROXY Protocol Patterns

## Table of Contents

1. [`HostSNI` Matching Rules & TLS Requirement](#1-hostsni-matching-rules--tls-requirement)
2. [Multiplexing TCP & HTTPS on Port 443 (`websecure`)](#2-multiplexing-tcp--https-on-port-443-websecure)
3. [Preserving Client IP with PROXY Protocol v1/v2](#3-preserving-client-ip-with-proxy-protocol-v1v2)

## 1. `HostSNI` Matching Rules & TLS Requirement

- **Specific `HostSNI('db.example.com')`**: Reads the TLS ClientHello SNI extension. Therefore, a `tls` block (`passthrough: true` or `secret_name` / `cert_resolver`) is **mandatory**; omitting `tls` triggers diagnosis code `TCP_SNI_WITHOUT_TLS`.
- **Wildcard `HostSNI('*')`**: Matches any TCP stream (including non-TLS protocols like raw Redis or MySQL). Must be bound to a dedicated `entryPoint` so it does not capture all traffic on a shared port.

## 2. Multiplexing TCP & HTTPS on Port 443 (`websecure`)

Traefik allows `IngressRouteTCP` and HTTP `IngressRoute` to share `websecure` (`:443`) as long as the `IngressRouteTCP` specifies a non-wildcard `HostSNI('tcp.example.com')` and `tls` (`passthrough: true` or termination).

## 3. Preserving Client IP with PROXY Protocol v1/v2

Because L4 TCP forwarding does not inject `X-Forwarded-For` HTTP headers, set `proxy_protocol_version: 2` (binary v2) or `1` (text v1) on the `BackendRef` only when the upstream server explicitly parses PROXY protocol headers.
