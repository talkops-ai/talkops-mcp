# Mutual TLS (mTLS) Client Authentication Guide

## Table of Contents

1. [Client-to-Traefik mTLS (`TLSOption.spec.clientAuth`)](#1-client-to-traefik-mtls-tlsoptionspecclientauth)
2. [Forwarding Client Cert Metadata (`pass_tls_client_cert`)](#2-forwarding-client-cert-metadata-pass_tls_client_cert)
3. [Traefik-to-Backend mTLS (`ServersTransport`)](#3-traefik-to-backend-mtls-serverstransport)

## 1. Client-to-Traefik mTLS (`TLSOption.spec.clientAuth`)

Configure client certificate validation using `traefik_configure_tls_policy(kind="TLSOption", ...)`:
- `client_auth_type`:
  - `"RequireAndVerifyClientCert"` (strictest — recommended for zero-trust B2B/partner APIs)
  - `"VerifyClientCertIfGiven"` (optional client cert verification)
  - `"RequestClientCert"` / `"RequireAnyClientCert"`
- `secret_names`: List of Kubernetes Secrets in the same namespace containing trusted PEM CA certificates (`tls.ca` or `ca.crt`).

## 2. Forwarding Client Cert Metadata (`pass_tls_client_cert`)

When backend services need to inspect the authenticated client's DN or SANs:
1. Create a `pass_tls_client_cert` Middleware via `traefik_configure_middleware(name="forward-client-cert", type="pass_tls_client_cert", spec={"pem": False, "info": {"subject": {"commonName": True, "serialNumber": True}, "sans": True}})`.
2. Attach it to the `IngressRoute` via `traefik_update_route`.

## 3. Traefik-to-Backend mTLS (`ServersTransport`)

To authenticate Traefik itself when connecting to an HTTPS or gRPC upstream pod:
1. Call `traefik_configure_servers_transport(protocol="http", name="backend-mtls", spec={"server_name": "internal.svc.cluster.local", "root_cas": ["internal-root-ca"], "certificates": ["traefik-client-cert"]})`.
2. Reference `servers_transport: "backend-mtls"` on the route backend via `traefik_update_route`.
