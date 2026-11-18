# Traefik MCP Server

Let your AI assistant manage Traefik v3 on Kubernetes: configure IngressRoutes, weighted canary splits, traffic mirroring, middlewares, TLS options, and TCP/UDP routes, diagnose 404/502/TLS errors, and audit your edge security posture.

## Quick Reference

- **Maintained by:** [TalkOps](https://talkops.ai) ([GitHub repository](https://github.com/talkops-ai/talkops-mcp/tree/main/src/traefik-mcp-server))
- **Supported tags:** `latest`, `0.2.1`
- **Architectures:** `linux/amd64`, `linux/arm64`
- **Documentation:** [https://talkops.ai/docs/integrations/traefik-mcp-server/overview](https://talkops.ai/docs/integrations/traefik-mcp-server/overview)
- **PyPI alternative:** [`talkops-traefik-mcp-server`](https://pypi.org/project/talkops-traefik-mcp-server/)
- **License:** [Apache License 2.0](https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE)

## What You Get

- **15 MCP tools** (5 read-only) built for AI agents and MCP clients
- **12 MCP resources** under `traefik://` for structured context discovery
- **7 Agent Skills** bundled in `/app/skills` ([browse on GitHub](https://github.com/talkops-ai/talkops-mcp/tree/main/src/traefik-mcp-server/skills))
- **Container ready:** Includes `kubectl` inside a minimal non-root image (`linux/amd64`, `linux/arm64`). Runs over `stdio` transport.
- **Safe by default:** starts in read-only mode until you explicitly set `MCP_ALLOW_WRITE=true`.

---

## Quick Start (MCP Client over `stdio`)

Use this configuration in **Claude Desktop**, **Cursor**, **Windsurf**, or **VS Code** (`mcp.json` / `claude_desktop_config.json`):

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

Using **Claude Code**? Register it in one command:

```bash
claude mcp add traefik -e TRAEFIK_NAMESPACE=traefik -- docker run -i --rm -v ~/.kube/config:/app/.kube/config:ro -e TRAEFIK_NAMESPACE talkopsai/traefik-mcp-server:latest
```

> **Tip:** If your kubeconfig references external client certificate files (for example with `minikube` or `kind`), mount the full `~/.kube` directory (`-v /path/to/.kube:/app/.kube:ro`) so those files are reachable inside the container.

Restart your MCP client and try asking:

- *"Why does `https://shop.example.com/api` return a 404?"*
- *"Shift 10% of traffic for `checkout` to the canary service, but show me the preview first."*
- *"Run a security audit of my Traefik setup."*

> **Note:** Traefik MCP Server runs over `stdio` transport only (`docker run -i --rm`).

---

## Allowing Changes (Write Mode)

Out of the box, the container runs in **read-only mode** (`MCP_ALLOW_WRITE=false`). To allow mutations (creating, updating, or deleting routes, weighted services, middlewares, and TLS resources), pass `-e MCP_ALLOW_WRITE=true` to `docker run`. Even with writes enabled, changes support dry-run previews and destructive operations require explicit confirmation.

---

## Environment Variables

| Variable | Container Default | Description |
| :--- | :--- | :--- |
| `K8S_KUBECONFIG` | `/app/.kube/config` | Path to mounted kubeconfig inside the container |
| `K8S_CONTEXT` | current context | Kubernetes context name to target |
| `TRAEFIK_NAMESPACE` | `traefik` | Namespace where Traefik runs |
| `TRAEFIK_API_URL` | via Kubernetes | Optional direct URL to the Traefik dashboard/API |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Optional Prometheus URL for route traffic metrics |
| `MCP_ALLOW_WRITE` | `false` | Set to `true` to enable cluster mutations |
| `MCP_ALLOWED_NAMESPACES` | all | Comma-separated allowlist of namespaces where writes are permitted |
| `MCP_PROTECTED_NAMESPACES` | `kube-system,traefik` | Namespaces requiring explicit confirmation before changes |
| `MCP_TOOLSETS` | `all` | Filter tools: `traffic`, `policies`, `diagnostics`, `readonly` |

---

## Available Tools (15)

| Tool | Access | Description |
| :--- | :--- | :--- |
| `traefik_analyze_logs` | Read | Parse and aggregate Traefik pod access logs (JSON or CLF) or controller logs with automatic secret/token redaction, status/router/latency filtering, and grouped counts. |
| `traefik_audit_configuration` | Read | Run 20 deterministic security, TLS, reliability, hygiene, v3_migration, and gateway_api checks across Traefik static configuration, routes, policies, certificates, and Gateway API... |
| `traefik_compare_traffic_metrics` | Read | Query Prometheus for Traefik service, router, or entrypoint request rate, 4xx/5xx error rate, P50/P95/P99 latency, and open connections across baseline and comparison windows, or c... |
| `traefik_configure_http_route` | Write | Create or update a Traefik v3 HTTP IngressRoute (<= 8 parameters). |
| `traefik_configure_middleware` | Write | Create or update a Traefik v3 HTTP Middleware or TCP MiddlewareTCP (<= 8 parameters). |
| `traefik_configure_servers_transport` | Write | Create or update a Traefik ServersTransport or ServersTransportTCP CRD (<= 8 parameters). |
| `traefik_configure_tcp_udp_route` | Write | Create or update a Traefik IngressRouteTCP or IngressRouteUDP (<= 8 parameters). |
| `traefik_configure_tls_policy` | Write (destructive) | Create or update a Traefik TLSOption policy or default TLSStore (<= 8 parameters). |
| `traefik_configure_traffic_mirroring` | Write (destructive) | Enable, update, or disable shadow traffic mirroring via a TraefikService (<= 8 parameters). |
| `traefik_configure_weighted_service` | Write | Create or update a weighted TraefikService for canary or blue-green traffic splitting, and optionally expose it via an IngressRoute in one call (<= 8 parameters). |
| `traefik_delete_resource` | Write (destructive) | Delete a Traefik custom resource (IngressRoute, IngressRouteTCP, IngressRouteUDP, TraefikService, Middleware, MiddlewareTCP, TLSOption, TLSStore, ServersTransport, ServersTransport... |
| `traefik_diagnose_route` | Read | Perform deep end-to-end health diagnosis of an IngressRoute, IngressRouteTCP, IngressRouteUDP, TraefikService, Ingress, HTTPRoute, GRPCRoute, TLSRoute, TCPRoute, or Gateway across... |
| `traefik_set_traffic_weights` | Write | Shift traffic weights on an existing weighted TraefikService (<= 8 parameters). |
| `traefik_trace_request` | Read | Evaluate which Traefik router matches a synthetic HTTP/TCP request by priority, trace the ordered middleware chain and backend service tree, identify shadowed routers and near-miss... |
| `traefik_update_route` | Write (destructive) | Patch an existing IngressRoute, IngressRouteTCP, or Kubernetes Ingress without restating the full resource (<= 8 parameters). |

---

## Bundled Agent Skills (7)

This image also ships step-by-step operational playbooks (`SKILL.md`) under `/app/skills`:

- [`adopting-traefik-nginx-ingress-provider`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/traefik-mcp-server/skills/adopting-traefik-nginx-ingress-provider/SKILL.md)
- [`auditing-traefik-security-posture`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/traefik-mcp-server/skills/auditing-traefik-security-posture/SKILL.md)
- [`configuring-traefik-middlewares`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/traefik-mcp-server/skills/configuring-traefik-middlewares/SKILL.md)
- [`managing-traefik-traffic-routing`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/traefik-mcp-server/skills/managing-traefik-traffic-routing/SKILL.md)
- [`routing-traefik-tcp-and-udp`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/traefik-mcp-server/skills/routing-traefik-tcp-and-udp/SKILL.md)
- [`securing-traefik-tls-and-certificates`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/traefik-mcp-server/skills/securing-traefik-tls-and-certificates/SKILL.md)
- [`troubleshooting-traefik-routing`](https://github.com/talkops-ai/talkops-mcp/blob/main/src/traefik-mcp-server/skills/troubleshooting-traefik-routing/SKILL.md)

To copy the skills onto your workstation for Claude Code or Cursor:

```bash
docker run --rm --entrypoint tar talkopsai/traefik-mcp-server:latest -C /app/skills -cf - . | tar -xf - -C ~/.claude/skills/
```

---

## Support & Community

- **Source & full docs:** [github.com/talkops-ai/talkops-mcp/tree/main/src/traefik-mcp-server](https://github.com/talkops-ai/talkops-mcp/tree/main/src/traefik-mcp-server)
- **Issues & feature requests:** [GitHub Issues](https://github.com/talkops-ai/talkops-mcp/issues/new?labels=traefik-mcp-server)
- **Community Slack:** [talkops.ai/slack](https://talkops.ai/slack/)
