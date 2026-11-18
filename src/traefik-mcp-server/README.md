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

Let your AI assistant manage Traefik v3 on Kubernetes: routes, weighted canary traffic, mirroring, middlewares, TLS, and TCP/UDP routing. It also explains why a request returns 404 or 502, and audits your setup for security issues.

## What you get

- **15 MCP tools** (5 read-only) that work against your live Traefik setup
- **12 resources** your assistant can read for context, under `traefik://`
- **7 Agent Skills**: step-by-step playbooks that teach your assistant how to use the tools well
- **Safe by default**: only read-only tools are loaded until you turn on writes, and changes are previewed or confirmed before they happen

## Quick start

**You'll need:**

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), **or** [Docker](https://docs.docker.com/get-docker/)
- Access to a Kubernetes cluster running Traefik v3 (through a kubeconfig file)
- Optional: a Prometheus URL for traffic metrics

**1. Add the server to your MCP client.** For Claude Desktop, Cursor, Windsurf, and most other clients, add this to your MCP config file:

```json
{
  "mcpServers": {
    "traefik": {
      "command": "uvx",
      "args": [
        "--from",
        "talkops-traefik-mcp-server",
        "traefik-mcp-server"
      ],
      "env": {
        "KUBECONFIG": "/path/to/your/kubeconfig",
        "TRAEFIK_NAMESPACE": "traefik"
      }
    }
  }
}
```

Using Claude Code? Run this instead:

```bash
claude mcp add traefik -e KUBECONFIG=/path/to/your/kubeconfig -e TRAEFIK_NAMESPACE=traefik -- uvx --from talkops-traefik-mcp-server traefik-mcp-server
```

`uvx` downloads [`talkops-traefik-mcp-server`](https://pypi.org/project/talkops-traefik-mcp-server/) from PyPI and runs it, so there's nothing else to install. Prefer a normal install? Run `pip install talkops-traefik-mcp-server` and use `traefik-mcp-server` as the command.

**Prefer Docker?** Pull [`talkopsai/traefik-mcp-server`](https://hub.docker.com/r/talkopsai/traefik-mcp-server) from Docker Hub—no Python setup needed:

```json
{
  "mcpServers": {
    "traefik": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v",
        "/path/to/your/kubeconfig:/app/.kube/config:ro",
        "-e",
        "TRAEFIK_NAMESPACE",
        "talkopsai/traefik-mcp-server:latest"
      ],
      "env": {
        "TRAEFIK_NAMESPACE": "traefik"
      }
    }
  }
}
```

> [!NOTE]
> Traefik runs over `stdio` only.

**2. Restart your client and try asking:**

- *"Why does `https://shop.example.com/api` return a 404?"*
- *"Shift 10% of traffic for `checkout` to the canary service, but show me the preview first."*
- *"Run a security audit of my Traefik setup."*

## Allowing changes

Out of the box the server is read-only. To let your assistant make changes (creating and changing routes, weighted services, middlewares, TLS settings, and deleting Traefik resources), add `"--allow-write"` to `args` (or pass `-e MCP_ALLOW_WRITE=true` to `docker run`). Even then, changes are previewed first and destructive actions ask for confirmation.

## Configuration

Set these as environment variables (the `env` block in your client config, or `-e` with `docker run`) or pass the matching flag.

| Variable | Flag | Default | What it does |
| :--- | :--- | :--- | :--- |
| `K8S_KUBECONFIG` / `KUBECONFIG` | `--kubeconfig` | `~/.kube/config` | Kubeconfig file to use |
| `K8S_CONTEXT` | `--context` | current context | Kubernetes context to use |
| `TRAEFIK_NAMESPACE` | `--traefik-namespace` | `traefik` | Namespace where Traefik runs |
| `TRAEFIK_API_URL` | `--traefik-api-url` | via Kubernetes | Direct URL to the Traefik API (optional) |
| `PROMETHEUS_URL` | `--prometheus-url` | `http://prometheus:9090` | Prometheus for traffic metrics |
| `MCP_ALLOW_WRITE` | `--allow-write` | `false` | Enable tools that change your cluster |
| `MCP_ALLOWED_NAMESPACES` | `--allowed-namespaces` | all | Only allow changes in these namespaces |
| `MCP_PROTECTED_NAMESPACES` | `--protected-namespaces` | `kube-system,traefik` | Ask for confirmation before changes here |
| `MCP_TOOLSETS` | `--toolsets` | `all` | Limit tools: `traffic`, `policies`, `diagnostics`, `readonly` |

Run `uvx --from talkops-traefik-mcp-server traefik-mcp-server --help` to see every option.

## Agent Skills

Skills live in [`skills/`](skills/). Each one is a `SKILL.md` playbook (plus optional `references/` and offline `scripts/`) that teaches your AI assistant *how* to do a job safely, while the MCP server does the actual work. Tools are the hands, skills are the know-how.

To use them, copy the folders into your assistant's skills directory, for example:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cp -r talkops-mcp/src/traefik-mcp-server/skills/* ~/.claude/skills/
```

This folder is also a portable [Agent Plugin](https://agent-plugins.org) (`plugin.json` + `mcp.json` + `skills/`), so plugin-aware clients can load the server and skills together.

| Skill | Use it to |
| :--- | :--- |
| [`managing-traefik-traffic-routing`](skills/managing-traefik-traffic-routing/SKILL.md) | Create routes and run canary, blue-green, and mirrored traffic. |
| [`configuring-traefik-middlewares`](skills/configuring-traefik-middlewares/SKILL.md) | Add rate limits, circuit breakers, auth, headers, and other middlewares in the right order. |
| [`securing-traefik-tls-and-certificates`](skills/securing-traefik-tls-and-certificates/SKILL.md) | Set up TLS options, mTLS, and check certificates. |
| [`routing-traefik-tcp-and-udp`](skills/routing-traefik-tcp-and-udp/SKILL.md) | Route TCP and UDP traffic, including TLS passthrough. |
| [`troubleshooting-traefik-routing`](skills/troubleshooting-traefik-routing/SKILL.md) | Work out why requests fail (404, 502, 503, TLS errors, and more). |
| [`auditing-traefik-security-posture`](skills/auditing-traefik-security-posture/SKILL.md) | Run a security and best-practice audit and fix the findings. |
| [`adopting-traefik-nginx-ingress-provider`](skills/adopting-traefik-nginx-ingress-provider/SKILL.md) | Serve existing NGINX Ingress resources with Traefik's built-in NGINX provider. |

## Reference

<details>
<summary><strong>All 15 tools</strong></summary>

| Tool | Access | What it does |
| :--- | :--- | :--- |
| `traefik_analyze_logs` | Read | Parse and aggregate Traefik pod access logs (JSON or CLF) or controller logs with automatic secret/token redaction, status/router/latency filtering, and grouped counts. |
| `traefik_audit_configuration` | Read | Run 20 deterministic security, TLS, reliability, hygiene, v3_migration, and gateway_api checks across Traefik static configuration, routes, policies, certificates, and Gateway API objects. |
| `traefik_compare_traffic_metrics` | Read | Query Prometheus for Traefik service, router, or entrypoint request rate, 4xx/5xx error rate, P50/P95/P99 latency, and open connections across baseline and comparison windows, or compare canary vs stable backend sub-services. |
| `traefik_configure_http_route` | Write | Create or update a Traefik v3 HTTP IngressRoute (<= 8 parameters). |
| `traefik_configure_middleware` | Write | Create or update a Traefik v3 HTTP Middleware or TCP MiddlewareTCP (<= 8 parameters). |
| `traefik_configure_servers_transport` | Write | Create or update a Traefik ServersTransport or ServersTransportTCP CRD (<= 8 parameters). |
| `traefik_configure_tcp_udp_route` | Write | Create or update a Traefik IngressRouteTCP or IngressRouteUDP (<= 8 parameters). |
| `traefik_configure_tls_policy` | Write (destructive) | Create or update a Traefik TLSOption policy or default TLSStore (<= 8 parameters). |
| `traefik_configure_traffic_mirroring` | Write (destructive) | Enable, update, or disable shadow traffic mirroring via a TraefikService (<= 8 parameters). |
| `traefik_configure_weighted_service` | Write | Create or update a weighted TraefikService for canary or blue-green traffic splitting, and optionally expose it via an IngressRoute in one call (<= 8 parameters). |
| `traefik_delete_resource` | Write (destructive) | Delete a Traefik custom resource (IngressRoute, IngressRouteTCP, IngressRouteUDP, TraefikService, Middleware, MiddlewareTCP, TLSOption, TLSStore, ServersTransport, ServersTransportTCP) with referential-integrity and human confirmation checks. Does NOT delete Kubernetes Services, Secrets, or Gateway API resources. |
| `traefik_diagnose_route` | Read | Perform deep end-to-end health diagnosis of an IngressRoute, IngressRouteTCP, IngressRouteUDP, TraefikService, Ingress, HTTPRoute, GRPCRoute, TLSRoute, TCPRoute, or Gateway across Kubernetes manifests, Traefik runtime API, endpoints, and TLS. |
| `traefik_set_traffic_weights` | Write | Shift traffic weights on an existing weighted TraefikService (<= 8 parameters). |
| `traefik_trace_request` | Read | Evaluate which Traefik router matches a synthetic HTTP/TCP request by priority, trace the ordered middleware chain and backend service tree, identify shadowed routers and near-misses, and optionally run an SSRF-guarded live HTTP/TLS probe. |
| `traefik_update_route` | Write (destructive) | Patch an existing IngressRoute, IngressRouteTCP, or Kubernetes Ingress without restating the full resource (<= 8 parameters). |

</details>

<details>
<summary><strong>All 12 resources</strong></summary>

| Resource | What it returns |
| :--- | :--- |
| `traefik://cluster/contexts` | Available kubeconfig contexts, active context, and cluster connection mode. |
| `traefik://instance/static-config` | Redacted Traefik static configuration including entryPoints, providers (kubernetesCRD, kubernetesIngress, kubernetesIngressNGINX, kubernetesGateway), certificatesResolvers, metrics, accessLog, and plugins. |
| `traefik://runtime/health` | Live Traefik runtime overview (/api/overview + /api/entrypoints): router, service, and middleware error/warning counts per protocol plus entryPoint listener status. |
| `traefik://server/capabilities` | Server readiness, allow_write flag, active toolsets, Traefik version, installed CRDs (traefik.io and gateway.networking.k8s.io), enabled providers, Prometheus reachability, and namespace policies. |
| `traefik://certificates/{namespace}` | Sanitized X.509 certificate metadata (Subject, Issuer, SANs, NotBefore, NotAfter, days_remaining, cert-manager Certificate status) in a namespace (or '_all'). Never exposes private key material. |
| `traefik://gateway/{namespace}` | Read-only Kubernetes Gateway API inventory (GatewayClass, Gateway, HTTPRoute, GRPCRoute, TLSRoute, TCPRoute, ReferenceGrant) with listener & parent status conditions (Accepted, Programmed, ResolvedRefs). |
| `traefik://manifests/{kind}/{namespace}/{name}` | Sanitized Kubernetes manifest (managedFields and applied-configuration bloat stripped, Secret data redacted) with resourceVersion for optimistic concurrency. |
| `traefik://metrics/{namespace}/{service}/summary` | 5-minute Prometheus GOLDEN metrics snapshot (RPS, 2xx/4xx/5xx error rates, P50/P95/P99 latency, open connections) for a Traefik service. |
| `traefik://policies/{namespace}` | Unified policy inventory (Middleware, MiddlewareTCP, TLSOption, TLSStore, ServersTransport, ServersTransportTCP) in a namespace (or '_all') with referenced-by route counts. |
| `traefik://routes/{namespace}` | Unified route inventory (IngressRoute, IngressRouteTCP, IngressRouteUDP, TraefikService, and Ingress) in a namespace (or '_all'), enriched with hosts, entryPoints, weights, mirror percentages, and ownership metadata. |
| `traefik://runtime/{protocol}` | Active Traefik runtime routers, services (with backend serverStatus UP/DOWN), and middlewares for protocol ('http', 'tcp', or 'udp'). |
| `traefik://schema/{kind}` | Cluster-installed CRD OpenAPI v3 spec schema and supported field names for a Traefik or Gateway API resource kind. |

</details>

## Development

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/traefik-mcp-server
uv sync --dev
uv run pytest
uv run traefik-mcp-server --help
```

## Get help

- [Documentation](https://talkops.ai/docs/integrations/traefik-mcp-server/overview)
- [Report a bug or request a feature](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=traefik-mcp-server)
- [Join the TalkOps community on Slack](https://talkops.ai/slack/)

## License

Apache 2.0. See [LICENSE](../../LICENSE).
