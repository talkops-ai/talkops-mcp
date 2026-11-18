<p align="center">
  <img src="https://raw.githubusercontent.com/traefik/traefik/master/docs/content/assets/img/traefik.logo.png" alt="Traefik logo" height="100"/>
</p>

<h1 align="center">Traefik MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An Agent Plugin (v1.0.0) and FastMCP Execution Server for Traefik v3 Kubernetes Traffic Management, Security Policies, and Deep Diagnostics — separating reasoning workflows (<code>SKILL.md</code>) from live cluster execution (MCP Tools & Resources).
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-traefik-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-traefik-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://traefik.io/"><img src="https://img.shields.io/badge/Traefik-v3.6%2B-24A1C1.svg?style=flat-square&logo=traefikproxy&logoColor=white" alt="Traefik v3.6+"/></a>
</p>

---

## Architecture: Skill & Execution Separation (`v0.2.0`)

Following the TalkOps Skill & Execution Separation standard (`docs/skill-and-execution-separation.md`), this repository packages two distinct layers in a single Agent Plugin (`plugin.json` + `mcp.json`):

1. **Reasoning Layer (`skills/*/SKILL.md` + `references/` + `scripts/`)**:
   - **7 Agent Skills** loaded progressively on-demand (~100 tokens at startup for metadata, `<500` lines when activated).
   - **10 Offline Deterministic Scripts** (`skills/*/scripts/*.py`) for local/GitOps Traefik v3 YAML generation, rule linting, TLS SAN validation, access log parsing, and NGINX annotation classification — zero live Kubernetes API dependencies.
   - **23 Domain Reference Guides** (`skills/*/references/*.md`) covering all 41 diagnostic codes, 20 security audit checks, 26 middleware types, and Traefik v3.6+ `kubernetesIngressNGINX` provider compatibility.

2. **Execution Layer (`traefik_mcp_server/`)**:
   - **15 Live Cluster Tools** across selectable toolsets (`traffic`, `policies`, `diagnostics`), each strictly `<= 8` parameters with Pydantic `Field(description=...)` schemas and `ToolAnnotations`.
   - **12 Sanitized Live Resources** (`traefik://...` — 4 static + 8 templates) for read-only cluster discovery, Traefik `/api/rawdata` runtime inspection, sanitized X.509 certificate metadata, Gateway API read-only inventory, and Prometheus golden metrics.
   - **0 MCP Prompts** — all multi-step runbooks and decision trees live in `skills/`.
   - **Local `stdio` Transport Only** (`ServerConfig.transport == "stdio"`).
   - **Safety-First Execution**: Read-only by default (`allow_write=False`), preview-first `dry_run=True` defaults on all mutating tools (including `traefik_set_traffic_weights`), optimistic concurrency via `expected_resource_version`, Argo Rollouts / GitOps / NGINX ownership guards, CRD OpenAPI schema gating, and MCP Elicitation (`ctx.elicit()`) + `confirm=True` fallback on destructive operations.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        AI Host (Cursor, Claude, Agent)                     │
└───────────────────┬────────────────────────────────────┬───────────────────┘
                    │ Progressive Disclosure             │ MCP Protocol (stdio)
                    ▼                                    ▼
┌───────────────────────────────────────┐  ┌─────────────────────────────────┐
│     Agent Skills Layer (skills/)      │  │   FastMCP Execution Server      │
│                                       │  │    (traefik_mcp_server/)        │
│ • managing-traefik-traffic-routing    │  │                                 │
│ • configuring-traefik-middlewares     │  │ • 15 Tools (<=8 params each)    │
│ • securing-traefik-tls-and-certs      │  │ • 12 Resources (traefik://)     │
│ • routing-traefik-tcp-and-udp         │  │ • 0 Prompts                     │
│ • troubleshooting-traefik-routing     │  │ • Ownership & Schema Guards     │
│ • auditing-traefik-security-posture   │  │ • Secret & Log Redaction        │
│ • adopting-traefik-nginx-ingress-...  │  │ • Write & Elicitation Gates     │
└───────────────────────────────────────┘  └────────────────┬────────────────┘
                                                            │
                                                            ▼
                                           ┌─────────────────────────────────┐
                                           │ Kubernetes + Traefik Runtime API│
                                           │         + Prometheus            │
                                           └─────────────────────────────────┘
```

---

## Bundled Agent Skills (`skills/`)

| Skill Name | Purpose | Offline Scripts (`scripts/`) | Reference Docs (`references/`) |
|------------|---------|------------------------------|--------------------------------|
| `managing-traefik-traffic-routing` | Configure HTTP/gRPC `IngressRoute`s, weighted `TraefikService` canary splits (`wrr`/`p2c`/`hrw`), preview-first weight shifts, and shadow traffic mirroring | `render_route_manifest.py`, `validate_match_rule.py`, `plan_weight_schedule.py` | `v3-rule-syntax-and-priority.md`, `canary-and-blue-green-playbooks.md`, `header-cookie-routing.md`, `shadow-mirroring-guide.md` |
| `configuring-traefik-middlewares` | Author, capability-gate, order, and attach all 24 HTTP `Middleware` and 2 TCP `MiddlewareTCP` types | `render_middleware_manifest.py`, `lint_middleware_spec.py` | `middleware-catalog.md`, `middleware-ordering-and-chains.md`, `rate-limit-and-circuit-breaker-tuning.md`, `servers-transport-and-healthchecks.md` |
| `securing-traefik-tls-and-certificates` | Configure `TLSOption` (Mozilla profiles, mTLS), `TLSStore` default certificates, backend `ServersTransport`, and inspect X.509 SANs/expiry | `inspect_certificate.py`, `check_host_coverage.py` | `tls-option-baselines.md`, `mtls-client-auth.md`, `cert-manager-and-acme-patterns.md`, `cert-rotation-runbook.md` |
| `routing-traefik-tcp-and-udp` | Configure `IngressRouteTCP` (`HostSNI`, TLS passthrough vs termination), `IngressRouteUDP`, and `ServersTransportTCP` | *(uses `traefik_configure_tcp_udp_route`)* | `tcp-sni-and-tls-patterns.md`, `udp-routing-notes.md` |
| `troubleshooting-traefik-routing` | Diagnose 404/421/500/502/503/504 errors across Traefik CRDs, `Ingress`, and Gateway API routes using `traefik_diagnose_route` (41 codes), `traefik_trace_request`, and `traefik_analyze_logs` | `parse_access_log.py` | `traefik-error-catalog.md`, `symptom-decision-trees.md`, `gateway-api-diagnostics.md`, `incident-summary-template.md` |
| `auditing-traefik-security-posture` | Run the 20-check best-practice and security audit (`traefik_audit_configuration`) and remediate findings | `render_audit_report.py` | `hardening-checklist.md`, `audit-report-template.md` |
| `adopting-traefik-nginx-ingress-provider` | Adopt Traefik v3.6+'s built-in `providers.kubernetesIngressNGINX` provider to serve existing `nginx.ingress.kubernetes.io/*` `Ingress` objects in-place | `classify_nginx_annotations.py` | `annotation-support-matrix.md`, `provider-configuration-and-coexistence.md`, `cutover-and-rollback-runbook.md` |

> **Note on Legacy NGINX Migration Tools**: Legacy `nginx_to_traefik` CRD rewrite MCP tools have been removed in `v0.2.0`. Use the `adopting-traefik-nginx-ingress-provider` skill and Traefik v3.6+'s native `providers.kubernetesIngressNGINX` provider instead.

---

## Available MCP Tools (15 Tools across Toolsets)

Every tool enforces `<= 8` parameters and returns structured Pydantic models (`ExecutionResult`, `RouteDiagnosisReport`, `RequestTraceReport`, `TrafficMetricsComparison`, `LogAnalysisReport`, `ConfigurationAuditReport`).

### Toolset: `traffic` (Write-Gated)
| Tool | Params | `dry_run` Default | Destructive Gate | Description |
|------|--------|-------------------|------------------|-------------|
| `traefik_configure_http_route` | 7 | `True` | No | Create or update an HTTP/gRPC `IngressRoute` with structured or raw v3 `RouteMatch` rules |
| `traefik_configure_weighted_service` | 6 | `True` | No | Create or update a weighted `TraefikService` (`wrr`, `p2c`, `hrw`) and optionally wire an `IngressRoute` |
| `traefik_set_traffic_weights` | 5 | `True` | No | Preview or shift traffic weights on a `TraefikService` with `expected_resource_version` concurrency control and `0`-ready-endpoint protection |
| `traefik_configure_traffic_mirroring` | 7 | `True` | Yes (`confirm` / elicit) | Enable, update, or disable shadow traffic mirroring via a `TraefikService` |
| `traefik_update_route` | 6 | `True` | No | Patch middlewares, TLS, entryPoints, priority, or backend on an `IngressRoute`, `IngressRouteTCP`, `IngressRouteUDP`, or `Ingress` |
| `traefik_configure_tcp_udp_route` | 7 | `True` | No | Create or update a Layer-4 `IngressRouteTCP` or `IngressRouteUDP` |

### Toolset: `policies` (Write-Gated)
| Tool | Params | `dry_run` Default | Destructive Gate | Description |
|------|--------|-------------------|------------------|-------------|
| `traefik_configure_middleware` | 6 | `True` | No | Create or update any of the 24 HTTP `Middleware` or 2 TCP `MiddlewareTCP` types with CRD schema gating |
| `traefik_configure_tls_policy` | 6 | `True` | On `default` / `TLSStore` | Create or update a `TLSOption` (Mozilla profiles / mTLS) or `TLSStore` |
| `traefik_configure_servers_transport` | 5 | `True` | No | Create or update a backend `ServersTransport` or `ServersTransportTCP` |

### Shared Lifecycle Tool (Registered when `traffic` or `policies` write toolset is enabled)
| Tool | Params | `dry_run` Default | Destructive Gate | Description |
|------|--------|-------------------|------------------|-------------|
| `traefik_delete_resource` | 6 | `True` | Yes (`confirm` / elicit) | Delete any Traefik CRD (`IngressRoute*`, `TraefikService`, `Middleware*`, `TLSOption`, `TLSStore`, `ServersTransport*`) with referential integrity checks |

### Toolset: `diagnostics` (Read-Only — Always Available in Default Mode)
| Tool | Params | Read-Only? | Description |
|------|--------|------------|-------------|
| `traefik_diagnose_route` | 4 | **Yes** | Single-call deep diagnosis across Traefik CRDs, `Ingress`, and Gateway API (`Gateway`, `HTTPRoute`, `GRPCRoute`, `TLSRoute`, `TCPRoute`) returning 41 deterministic `diagnosis_codes` |
| `traefik_trace_request` | 7 | **Yes** | Static Traefik v3 rule evaluation, priority ordering, middleware simulation, and SSRF-guarded live HTTP probe |
| `traefik_compare_traffic_metrics` | 6 | **Yes** | Compare Prometheus RPS, 2xx/4xx/5xx rates, and P50/P95/P99 latency across baseline vs comparison windows |
| `traefik_analyze_logs` | 5 | **Yes** | Parse and aggregate Traefik JSON/CLF access logs or controller logs with automatic token/header redaction |
| `traefik_audit_configuration` | 4 | **Yes** | Run the 20-check security, TLS, reliability, and hygiene audit across namespaces |

---

## Available MCP Resources (12 Read-Only `traefik://` Resources)

| Resource URI | Type | Description |
|--------------|------|-------------|
| `traefik://server/capabilities` | Static | Server readiness, `allow_write`, active `toolsets`, Traefik version, installed CRDs (`traefik.io` & `gateway.networking.k8s.io`), enabled providers, and namespace policies |
| `traefik://cluster/contexts` | Static | Available kubeconfig contexts, active context, and cluster connection mode |
| `traefik://instance/static-config` | Static | Redacted Traefik static configuration (`entryPoints`, `providers`, `certificatesResolvers`, `metrics`, `accessLog`, `plugins`) |
| `traefik://runtime/health` | Static | Live Traefik runtime overview (`/api/overview` + `/api/entrypoints`): router/service/middleware error counts and listener status |
| `traefik://runtime/{protocol}` | Template | Active Traefik runtime routers, services (with backend `serverStatus` UP/DOWN), and middlewares for `http`, `tcp`, or `udp` |
| `traefik://routes/{namespace}` | Template | Unified route inventory (`IngressRoute*`, `TraefikService`, and `Ingress`) in `namespace` or `_all` |
| `traefik://manifests/{kind}/{namespace}/{name}` | Template | Sanitized Kubernetes manifest (`managedFields`, `uid`, and `last-applied-configuration` stripped; `Secret` data redacted) + `resource_version` |
| `traefik://policies/{namespace}` | Template | Unified policy inventory (`Middleware*`, `TLSOption`, `TLSStore`, `ServersTransport*`) with `referenced_by` route counts |
| `traefik://certificates/{namespace}` | Template | Sanitized X.509 certificate metadata (`Subject`, `Issuer`, `SANs`, `NotAfter`, `days_remaining`). Never exposes private keys |
| `traefik://gateway/{namespace}` | Template | Read-only Kubernetes Gateway API inventory (`GatewayClass`, `Gateway`, `HTTPRoute`, `GRPCRoute`, `TLSRoute`, `TCPRoute`, `ReferenceGrant`) |
| `traefik://metrics/{namespace}/{service}/summary` | Template | 5-minute Prometheus GOLDEN metrics snapshot (RPS, 2xx/4xx/5xx rates, P50/P95/P99 latency, open connections) |
| `traefik://schema/{kind}` | Template | Cluster-installed CRD OpenAPI v3 `spec` properties and supported load-balancing strategies for `kind` |

---

## Quick Start & CLI Configuration

```bash
# Run in safe Read-Only mode (default: 5 diagnostic tools + 12 resources)
uv run traefik-mcp-server

# Enable write tools across all toolsets (15 tools + 12 resources)
uv run traefik-mcp-server --allow-write --toolsets all

# Enable only traffic and diagnostics toolsets with namespace allowlisting
uv run traefik-mcp-server --allow-write --toolsets traffic,diagnostics --allowed-namespaces default,payments
```

### CLI Flags & Environment Variables

| CLI Flag | Environment Variable | Default | Description |
|----------|----------------------|---------|-------------|
| `--transport` | `MCP_TRANSPORT` | `stdio` | Transport mode (`stdio` only) |
| `--allow-write` | `MCP_ALLOW_WRITE` | `false` | Enable mutating and destructive cluster tools |
| `--read-only` | `MCP_READ_ONLY` | `false` | Force read-only mode (overrides `--allow-write`) |
| `--toolsets` | `MCP_TOOLSETS` | `all` | Comma-separated toolsets: `all`, `readonly`, `traffic`, `policies`, `diagnostics` |
| `--traefik-namespace` | `TRAEFIK_NAMESPACE` | `traefik` | Namespace where the Traefik controller runs |
| `--traefik-api-url` | `TRAEFIK_API_URL` | `None` | Optional direct URL to Traefik Runtime API (defaults to K8s `pods/proxy`) |
| `--prometheus-url` | `PROMETHEUS_URL` | `http://prometheus:9090` | Prometheus base URL for golden metrics |
| `--allowed-namespaces` | `MCP_ALLOWED_NAMESPACES` | `None` (all non-protected) | Comma-separated allowlist of namespaces permitted for writes |
| `--protected-namespaces` | `MCP_PROTECTED_NAMESPACES` | `kube-system,traefik` | Protected namespaces requiring operator confirmation |
| `--kubeconfig` | `K8S_KUBECONFIG` | `None` | Path to kubeconfig file |
| `--context` | `K8S_CONTEXT` | `None` | Kubernetes context name |

---

## Running Tests

```bash
cd src/traefik-mcp-server
.venv/bin/pytest -v
```
