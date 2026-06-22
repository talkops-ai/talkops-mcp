<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/prometheus/stacked/color/prometheus-stacked-color.svg" alt="Alertmanager MCP Server" width="140" onError="this.style.display='none'"/>
</p>

<h1 align="center">Alertmanager MCP Server</h1>

<p align="center">
  An MCP server that gives AI assistants the power to triage alerts, manage silences, inspect routing, and govern Alertmanager operations — from on-call summarization to notification pipeline testing.
</p>

<p align="center">
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://prometheus.io/docs/alerting/latest/alertmanager/"><img src="https://img.shields.io/badge/Alertmanager-Compatible-E6522C.svg?style=flat-square&logo=prometheus&logoColor=white" alt="Alertmanager"/></a>
  <a href="https://discord.gg/tSN2Qn9uM8"><img src="https://img.shields.io/badge/Discord-Join%20Us-5865F2.svg?style=flat-square&logo=discord&logoColor=white" alt="Discord"/></a>
</p>

<p align="center">
  <a href="#getting-started">Quick Start</a> · <a href="https://github.com/talkops-ai/talkops-mcp">Docs</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=bug_report.md">Report Bug</a> · <a href="https://github.com/talkops-ai/talkops-mcp/issues/new?template=feature_request.md">Request Feature</a>
</p>

---

## Why Alertmanager MCP Server?

**The problem:** Alertmanager is the notification brain of the Prometheus ecosystem, but operating it effectively requires deep knowledge. Understanding the routing tree to know who gets paged, creating silences with the right matchers and durations, auditing why an alert didn't reach the right receiver, and managing maintenance windows — each of these requires familiarity with Alertmanager's configuration model. If you ask an AI assistant to help, it typically guesses at matcher syntax, creates overly broad silences, or can't explain the routing logic.

**The solution:** The Alertmanager MCP Server gives AI assistants (like Claude, Cline, or Cursor) structured, safe tools to operate Alertmanager natively. Instead of guessing at matchers or writing silence payloads from memory, your AI can now confidently manage the entire alert lifecycle:

1. **On-Call Triage:** The AI summarizes active alerts grouped by severity and service, explains routing paths, and identifies alerts falling into the default route — all in one guided workflow.
2. **Safe Silence Management:** Mandatory preview dry-runs before creating silences, duplicate detection, 24-hour duration caps, blast-radius warnings, and policy validation — preventing overly broad silences that could mask real incidents.
3. **Routing Introspection:** Simulate routing for any label set (`amtool config routes test`-equivalent), inspect the full routing tree, list receivers with integration types, and audit which alerts hit the default route.
4. **Governance & Compliance:** Export effective configuration for Git storage, audit recent silence changes with author tracking, and validate proposed silences against organizational policy.
5. **Multi-Backend Support:** Manage multiple Alertmanager backends with explicit `backend_id` on every call — no hidden defaults.

---

## Key Features

**Backend Discovery & Multi-Backend**
- Discover and inspect multiple Alertmanager backends
- Health checks, version info, cluster peer status
- Supports standalone and clustered Alertmanager deployments

**Alert Triage & On-Call**
- List and filter alerts by label, severity, state, and receiver
- Alert group inspection (Alertmanager's native grouping)
- Human-readable on-call summaries with severity/service breakdowns
- Push test alerts to verify notification integrations

**Silence Lifecycle Management**
- Full CRUD: create, update (extend), expire silences
- Mandatory preview dry-run before broad silences
- Duplicate silence detection — blocks creating equivalent active silences
- 24-hour duration cap (configurable)
- LLM-friendly `silence_alert` helper with scope control (instance/service/env)
- Policy validation for compliance checks

**Routing & Notification Introspection**
- Full nested routing tree inspection
- Receiver enumeration with integration type detection (Slack, PagerDuty, email, webhook)
- Route simulation for any label set with human-readable explanations
- Default route audit — identifies misconfigured alerts

**Governance & Audit**
- Export effective configuration as YAML or JSON
- Track recent silence lifecycle changes with author attribution
- In-memory audit log for all MCP-initiated operations
- Silence policy validation (duration caps, comment requirements, blast radius)

**Production-Ready**
- Structured logging (JSON/text)
- Environment-based configuration with multi-backend JSON support

---

## Architecture

```
                    ┌─────────────────────────┐
                    │     MCP Client          │
                    │ (Claude, Cline, Cursor) │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   FastMCP Server Core   │
                    │  (HTTP / SSE / stdio)   │
                    └──────────┬──────────────┘
                               │
      ┌────────────┬───────────┼───────────┬────────────┐
      │            │           │           │            │
 ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐
 │  Tools  │ │Resources│ │ Prompts │ │  Utils  │ │ Models  │
 │ (6 grp) │ │ (11)    │ │ (3)     │ │         │ │         │
 └────┬────┘ └────┬────┘ └─────────┘ └─────────┘ └─────────┘
      │            │
      └──────┬─────┘
             │
  ┌──────────▼──────────┐
  │    Service Layer     │
  │                      │
  │ alertmanager_service │
  └──────────┬──────────┘
             │
  ┌──────────▼──────────┐
  │ Alertmanager HTTP API│
  │ (v2 API)             │
  └─────────────────────┘
```

**How it works:**

1. An AI assistant connects via HTTP, SSE, or stdio.
2. The AI loads `am://system/backends` resource to discover available backends.
3. Every subsequent tool call requires an explicit `backend_id` — no hidden state.
4. The service layer interacts with Alertmanager's v2 HTTP API.
5. Safety guardrails enforce silence duration caps and blast-radius warnings.

---

## Table of Contents

- [Why Alertmanager MCP Server?](#why-alertmanager-mcp-server)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Available Tools](#available-tools)
- [Available Resources](#available-resources)
- [Available Prompts](#available-prompts)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [FAQ](#faq)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
- [License](#license)
- [Contact](#contact)
- [Acknowledgments](#acknowledgments)

---

## Tech Stack

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.12+ |
| **MCP Framework** | [FastMCP](https://github.com/jlowin/fastmcp) ≥2.13.3 |
| **Protocol** | [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) |
| **Alertmanager** | HTTP API v2 · Silence API · Route Simulation |
| **Transport** | HTTP · SSE · Streamable-HTTP · stdio |
| **Infrastructure** | Docker · [uv](https://github.com/astral-sh/uv) |

---

## Getting Started

### Prerequisites

- **Docker** (recommended) or **Python 3.12+** (for local dev)
- **Access to an Alertmanager instance** (standalone or clustered)

### Quick Start with Docker (recommended)

```bash
docker run --rm -it \
  -p 8769:8769 \
  -e ALERTMANAGER_BASE_URL=http://host.docker.internal:9093 \
  -e MCP_TRANSPORT=http \
  talkopsai/alertmanager-mcp-server:latest
```

The server is now listening on `http://localhost:8769/mcp`.

Point your MCP client at it:

```json
{
  "mcpServers": {
    "alertmanager": {
      "url": "http://localhost:8769/mcp",
      "description": "MCP Server for Alertmanager alert triage, silence management, and routing"
    }
  }
}
```

### From Source (Python)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management.

2. Clone and set up:

```bash
git clone https://github.com/talkops-ai/talkops-mcp.git
cd talkops-mcp/src/alertmanager-mcp-server
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

3. Configure your `.env`:

```bash
ALERTMANAGER_BASE_URL=http://localhost:9093
MCP_TRANSPORT=http
MCP_LOG_LEVEL=INFO
```

4. Run the server:

```bash
uv run alertmanager-mcp-server
```

Or, with the venv activated: `alertmanager-mcp-server`.

5. Run tests:

```bash
source .venv/bin/activate
pytest tests/
```

---

## Configuration

All configuration is via environment variables (loaded from `.env` via python-dotenv).

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_NAME` | `alertmanager-mcp-server` | Server name identifier |
| `MCP_SERVER_VERSION` | `0.1.0` | Server version string |
| `MCP_TRANSPORT` | `stdio` | Transport mode: `http`, `sse`, `streamable-http`, or `stdio` |
| `MCP_HOST` | `0.0.0.0` | Host address for HTTP server |
| `MCP_PORT` | `8769` | Port for HTTP server |
| `MCP_PATH` | `/mcp` | MCP endpoint path |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `MCP_LOG_FORMAT` | `json` | Log format: `json` or `text` |

### Alertmanager Backend (Single)

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERTMANAGER_BASE_URL` | `http://localhost:9093` | Alertmanager HTTP API base URL |
| `ALERTMANAGER_BACKEND_ID` | `default` | Backend identifier used in all tool calls |
| `ALERTMANAGER_DISPLAY_NAME` | *(empty)* | Human-readable backend name |
| `ALERTMANAGER_AUTH_HEADER` | *(empty)* | Authorization header value (e.g. `Bearer <token>`) |
| `ALERTMANAGER_VERIFY_SSL` | `true` | Verify SSL certificates |
| `ALERTMANAGER_TIMEOUT` | `30` | HTTP timeout for Alertmanager API calls (seconds) |

### Alertmanager Backends (Multi)

For multiple backends, set `ALERTMANAGER_BACKENDS` as a JSON array:

```bash
ALERTMANAGER_BACKENDS='[
  {"id": "prod", "base_url": "https://alertmanager-prod.example.com", "labels": {"env": "prod"}},
  {"id": "staging", "base_url": "https://alertmanager-staging.example.com", "labels": {"env": "staging"}}
]'
```

### Silence Safety

| Variable | Default | Description |
|----------|---------|-------------|
| `AM_MAX_SILENCE_MINUTES` | `1440` | Maximum silence duration in minutes (24h) |
| `AM_SILENCE_WARNING_THRESHOLD` | `50` | Warn if a silence would affect ≥ N alerts |

---

## Available Tools

### Alert Triage
| Tool | Description |
|------|-------------|
| `am_list_alerts` | List alerts with label/state filters and pagination. |
| `am_list_alert_groups` | List alert groups as computed by Alertmanager for high-level triage. |
| `am_push_test_alert` | Fire a synthetic test alert to verify notification integrations. |

### Silence Lifecycle
| Tool | Description |
|------|-------------|
| `am_list_silences` | List silences with optional state filter and pagination. |
| `am_create_silence` | Create a silence to suppress matching alerts (with duplicate detection). |
| `am_update_silence` | Update an existing silence (extend duration or modify end time). |
| `am_expire_silence` | Expire a silence to reactivate alert notifications. |

### Silence Helpers
| Tool | Description |
|------|-------------|
| `am_preview_silence` | Preview the blast radius of a silence before creating it. |
| `am_silence_alert` | Create a narrowly-scoped silence for a specific alert (fingerprint or labels). |

### Routing & Notifications
| Tool | Description |
|------|-------------|
| `am_explain_routing` | Simulate routing and inhibition for a given label set with explanation. |
| `am_audit_default_route` | Show alerts falling into the default route, highlighting misconfigurations. |

### Governance & Audit
| Tool | Description |
|------|-------------|
| `am_list_recent_changes` | List recent silence changes (created, expired, updated) within a time window. |
| `am_validate_silence_policy` | Validate a proposed silence against organizational policy before creation. |

### On-Call Triage
| Tool | Description |
|------|-------------|
| `am_summarize_oncall` | Generate a human-readable on-call summary of active alerts. |

---

## Available Resources

| Resource URI | Description |
|--------------|-------------|
| `am://system/backends` | All known backends with health status — use this as the **first step** in any workflow |
| `am://system/backends/{backend_id}` | Detailed status, version, cluster info, and health for a specific backend |
| `am://system/status` | Alertmanager version, uptime, cluster info, and config summary |
| `am://system/receivers` | Configured receivers (Slack, PagerDuty, email, webhook) with redacted config |
| `am://system/config` | Routing tree and inhibition rules (secrets redacted) |
| `am://system/audit-log` | Recent MCP-initiated operations (create/expire/extend silence, push test alert) |
| `am://alerts/active` | Bounded snapshot of active alerts for default backend |
| `am://alerts/groups` | Snapshot of alert groups as computed by Alertmanager |
| `am://silences/active` | Snapshot of active silences for default backend |
| `am://best-practices` | Alerting best practices |
| `am://onboarding-guide` | Alert onboarding guide |

---

## Available Prompts

Guided workflow prompts that orchestrate multiple tools into step-by-step journeys:

| Prompt Name | Description | Parameters |
|-------------|-------------|------------|
| `am-alert-triage-guided` | Guided workflow for triaging active alerts | `backend_id`, `service`, `env` |
| `am-maintenance-silence-guided` | Guided workflow for creating a maintenance silence | `backend_id`, `service`, `env`, `duration` |
| `am-integration-test-guided` | Guided workflow for testing notification integrations (Slack, PagerDuty) | `backend_id`, `team`, `receiver` |

---

## Usage

Supported workflows with prompt examples and links to detailed guides:

| Workflow | Prompt Example | Documentation |
|----------|----------------|---------------|
| **On-Call Triage** | `"Summarize what's firing right now for the checkout service in prod."` | [AM_TRIAGE_TEST_GUIDE.md](docs/AM_TRIAGE_TEST_GUIDE.md) |
| **Maintenance Silence** | `"Silence alerts for the payments service in prod for 2 hours during deployment."` | [AM_SILENCE_TEST_GUIDE.md](docs/AM_SILENCE_TEST_GUIDE.md) |
| **Routing Audit** | `"Who gets paged when a critical alert fires for the api-server?"` | [AM_GOVERNANCE_TEST_GUIDE.md](docs/AM_GOVERNANCE_TEST_GUIDE.md) |
| **Integration Testing** | `"Push a test alert to verify that the slack-sre receiver is working."` | [AM_GOVERNANCE_TEST_GUIDE.md](docs/AM_GOVERNANCE_TEST_GUIDE.md) |
| **Governance Review** | `"Show me all silence changes in the last 24 hours and who created them."` | [AM_GOVERNANCE_TEST_GUIDE.md](docs/AM_GOVERNANCE_TEST_GUIDE.md) |

See [WORKFLOW_JOURNEYS.md](docs/WORKFLOW_JOURNEYS.md) for the full workflow reference and [PROMPT_REFERENCE.md](docs/PROMPT_REFERENCE.md) for natural-language prompts.

---

## Project Structure

```text
alertmanager-mcp-server/
├── alertmanager_mcp_server/        # Main package
│   ├── tools/                      # MCP Tools (6 active tool groups, 14 tools)
│   │   ├── alert_tools.py          # Alert listing, grouping, test alerts
│   │   ├── silence_tools.py        # Silence CRUD lifecycle
│   │   ├── helper_tools.py         # Preview & quick silence helpers
│   │   ├── routing_tools.py        # Routing simulation, default route audit
│   │   ├── governance_tools.py     # Audit, policy validation
│   │   └── triage_tools.py         # On-call summarization
│   ├── resources/                  # MCP Resources (11 URIs)
│   │   ├── backend_resources.py    # Backend health & capabilities
│   │   ├── alert_resources.py      # Active alerts & groups
│   │   ├── silence_resources.py    # Active silences
│   │   ├── config_resources.py     # Receivers & routing config
│   │   ├── status_resources.py     # Version, uptime, cluster info
│   │   ├── audit_resources.py      # MCP operation audit log
│   │   └── static_resources.py     # Best practices & onboarding guide
│   ├── prompts/                    # MCP Prompts (3 guided workflows)
│   │   ├── triage_prompts.py       # Alert triage workflow
│   │   ├── silence_prompts.py      # Maintenance silence workflow
│   │   └── onboarding_prompts.py   # Integration test workflow
│   ├── services/                   # Business logic
│   │   └── alertmanager_service.py # Alertmanager HTTP API wrapper
│   ├── server/                     # FastMCP server setup
│   │   ├── core.py                 # Server creation
│   │   └── bootstrap.py            # Component initialization
│   ├── models/                     # Pydantic data models
│   │   ├── alert.py                # Alert & AlertMatcher
│   │   ├── silence.py              # Silence & PostableSilence
│   │   ├── backend.py              # BackendDescriptor
│   │   ├── config.py               # ConfigSnapshot, RouteNode, Receiver
│   │   └── audit.py                # AuditEntry
│   ├── utils/                      # Helpers
│   │   ├── __init__.py             # Matcher logic, silence window calc
│   │   └── audit.py                # In-memory audit log
│   ├── static/                     # Static documentation
│   │   ├── ALERTMANAGER_BEST_PRACTICES.md
│   │   ├── ALERTMANAGER_ONBOARDING_GUIDE.md
│   │   └── ALERTMANAGER_MCP_INSTRUCTIONS.md
│   ├── exceptions/                 # Custom exception hierarchy
│   ├── config.py                   # Environment parsing
│   └── main.py                     # Entry point
├── tests/                          # Test suites
├── docs/                           # Documentation
├── pyproject.toml                  # Package definitions (Python 3.12)
└── README.md                       # This documentation
```

---

## Roadmap

**Shipped:**

- [x] Multi-backend discovery with health checks
- [x] Alert listing with label/state filtering and pagination
- [x] Alert group inspection (Alertmanager native grouping)
- [x] Full silence lifecycle (create, update, expire) with safety guardrails
- [x] Silence preview dry-run with blast-radius analysis
- [x] Duplicate silence detection
- [x] LLM-friendly silence_alert helper with scope control
- [x] Full routing tree introspection
- [x] Route simulation with human-readable explanations
- [x] Receiver enumeration with integration type detection
- [x] Default route audit for misconfiguration detection
- [x] On-call alert summarization grouped by severity/service
- [x] Silence policy validation (duration caps, comment requirements)
- [x] Config export (YAML/JSON) for Git storage
- [x] Silence change audit with author tracking
- [x] Test alert injection for integration verification
- [x] In-memory audit log for all MCP operations
- [x] 3 guided workflow prompts (triage, silence, integration test)

**Coming next:**

- [ ] Prometheus MCP cross-integration for metric-level diagnostics
- [ ] AlertmanagerConfig CRD management for Prometheus Operator
- [ ] Silence templates for recurring maintenance windows
- [ ] Webhook receiver testing with response validation
- [ ] Multi-tenant silence policies with team-scoped permissions

See [open issues](https://github.com/talkops-ai/talkops-mcp/issues) for the full list of proposed features.

---

## Contributing

Contributions are welcome. The process is straightforward:

1. Fork the repo
2. Create a branch (`git checkout -b feature/SilenceTemplates`)
3. Make your changes and commit
4. Push and open a PR

If you're considering something bigger, open an issue first so we can align on the approach.

---

## FAQ

<details>
<summary><b>Which MCP clients work with this?</b></summary>
Any MCP-compatible client including Claude Desktop, Cline, Cursor, and custom clients. Connect via <code>http://localhost:8769/mcp</code> for HTTP transport, or configure stdio for direct process communication.
</details>

<details>
<summary><b>Does this modify my Alertmanager configuration?</b></summary>
Most tools are read-only. The exceptions are: <code>am_create_silence</code>/<code>am_update_silence</code>/<code>am_expire_silence</code>/<code>am_silence_alert</code> (create/expire silences), and <code>am_push_test_alert</code> (fires a real alert into Alertmanager). Governance and routing tools are strictly read-only — they inspect but never modify configuration.
</details>

<details>
<summary><b>Why does the server enforce silence duration caps?</b></summary>
Unbounded silences are a leading cause of missed incidents. The default 24-hour cap ensures silences are time-boxed. If a maintenance window needs to be extended, use <code>am_update_silence</code> to incrementally extend. Override the cap via <code>AM_MAX_SILENCE_MINUTES</code>.
</details>

<details>
<summary><b>Can I use this with a clustered Alertmanager?</b></summary>
Yes. Point <code>ALERTMANAGER_BASE_URL</code> at any cluster member or a load balancer. The server uses the standard Alertmanager v2 API, which handles cluster replication internally.
</details>

<details>
<summary><b>How does it relate to the Prometheus MCP Server?</b></summary>
They are complementary. The Prometheus MCP Server handles metric querying, exporter deployment, and TSDB management. The Alertmanager MCP Server handles alert triage, silences, routing, and notification management. Use both together for full observability coverage.
</details>

---

## Troubleshooting

### Backend Connection Issues

1. Verify `ALERTMANAGER_BASE_URL` points to a reachable Alertmanager instance.
2. Load the `am://system/backends` resource to check health status.
3. If using auth, verify `ALERTMANAGER_AUTH_HEADER` is set correctly.
4. For SSL issues, try `ALERTMANAGER_VERIFY_SSL=false` (development only).

### Silence Creation Failures

1. **Duration cap exceeded**: The default cap is 24 hours (1440 minutes). Increase `AM_MAX_SILENCE_MINUTES` or use shorter durations.
2. **Duplicate silence**: An equivalent active silence already exists. Use `am_list_silences` to find it.
3. **Missing matchers**: At least one matcher is required. Use `am_preview_silence` first to validate.

### Routing Simulation Issues

1. **Empty routing tree**: The Alertmanager instance may not have a configuration loaded. Check `am://system/config`.
2. **No receivers found**: Verify Alertmanager has receivers configured in its `alertmanager.yml`.
3. **Unexpected routing**: Use `am_explain_routing` with the specific alert labels to trace the routing path.

---

## Security Considerations

- **Never expose the MCP server to the public internet** without proper authentication.
- **Silences affect real alert notifications** — always preview before creating silences in production.
- **Test alerts fire real notifications** — `am_push_test_alert` will trigger downstream integrations (Slack, PagerDuty, email).
- **Configuration export may contain sensitive routing rules** — treat exported configs as confidential.

---

## License

Apache 2.0 — see [LICENSE](../../LICENSE).

---

## Contact

**TalkOps AI** — [github.com/talkops-ai](https://github.com/talkops-ai)

**Project:** [github.com/talkops-ai/talkops-mcp](https://github.com/talkops-ai/talkops-mcp)

**Discord:** [Join the community](https://discord.gg/tSN2Qn9uM8)

---

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io/) for enabling AI-native tool interfaces.
- [FastMCP](https://github.com/jlowin/fastmcp) for the Python MCP server framework.
- [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) for the alert notification engine.
- [Prometheus](https://prometheus.io/) for the foundational monitoring ecosystem.
