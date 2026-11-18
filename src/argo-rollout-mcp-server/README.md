<p align="center">
  <img src="https://raw.githubusercontent.com/cncf/artwork/main/projects/argo/icon/color/argo-icon-color.svg" alt="Argo Rollouts logo" height="100"/>
</p>

<h1 align="center">Argo Rollout MCP Server &amp; Agent Plugin</h1>

<p align="center">
  An Agent Plugin (v1.0.0) and FastMCP Execution Server for Kubernetes Progressive Delivery with Argo Rollouts — separating reasoning workflows (<code>SKILL.md</code>) from live cluster execution (MCP Tools & Resources).
</p>

<p align="center">
  <a href="https://pypi.org/project/talkops-argo-rollout-mcp-server/"><img src="https://img.shields.io/pypi/v/talkops-argo-rollout-mcp-server.svg?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"/></a>
  <a href="https://github.com/talkops-ai/talkops-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="License"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-Model%20Context%20Protocol-4A90D9.svg?style=flat-square" alt="MCP"/></a>
  <a href="https://argoproj.github.io/argo-rollouts/"><img src="https://img.shields.io/badge/Argo%20Rollouts-v1.6%2B-EF7B4D.svg?style=flat-square&logo=argo&logoColor=white" alt="Argo Rollouts v1.6+"/></a>
</p>

---

## Architecture: Skill & Execution Separation (`v0.2.0`)

Following the TalkOps Skill & Execution Separation standard (`docs/skill-and-execution-separation.md`), this repository packages two distinct layers in a single Agent Plugin (`plugin.json` + `mcp.json`):

1. **Reasoning Layer (`skills/*/SKILL.md` + `references/` + `scripts/`)**:
   - **4 Agent Skills** loaded progressively on-demand (~100 tokens at startup for metadata, `<500` lines when activated).
   - **8 Offline Deterministic Scripts** (`skills/*/scripts/*.py`) for local/GitOps YAML generation, transformation, and validation — zero live Kubernetes API dependencies.
   - **8 Domain Reference Guides** (`skills/*/references/*.md`) loaded only when needed.

2. **Execution Layer (`argo_rollout_mcp_server/`)**:
   - **15 Live Cluster Tools** across 4 selectable toolsets (`rollouts`, `analysis`, `migration`, `diagnostics`), each strictly `<= 8` parameters with Pydantic `Field(description=...)` schemas.
   - **13 Sanitized Live Resources** (`argorollout://...`) for read-only cluster discovery, revision history, AnalysisRun inspection, and Prometheus health.
   - **0 MCP Prompts** — all multi-step runbooks and decision trees live in `skills/`.
   - **Safety-First Execution**: Read-only by default (`allow_write=False`), tiered `dry_run` defaults (`dry_run=True` on structural mutations, `dry_run=False` on runtime step/image operations), MCP Elicitation (`ctx.elicit()`) + `confirm=True` fallback on destructive operations, and automatic secret/annotation redaction.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        AI Host (Cursor, Claude, Agent)                     │
└───────────────────┬────────────────────────────────────┬───────────────────┘
                    │ Progressive Disclosure             │ MCP Protocol (stdio / HTTP)
                    ▼                                    ▼
┌───────────────────────────────────────┐  ┌─────────────────────────────────┐
│     Agent Skills Layer (skills/)      │  │   FastMCP Execution Server      │
│                                       │  │  (argo_rollout_mcp_server/)     │
│ • onboarding-and-migrating-to-...     │  │                                 │
│ • progressing-argo-rollouts           │  │ • 15 Tools (4 Toolsets, <=8 args│
│ • gating-rollouts-with-analysis-...   │  │ • 13 Resources (argorollout://) │
│ • troubleshooting-argo-rollouts       │  │ • 0 Prompts                     │
│ • 8 Offline Scripts & 8 References    │  │ • Redaction & Write/Elicit Gate │
└───────────────────────────────────────┘  └────────────────┬────────────────┘
                                                            │
                                                            ▼
                                           ┌─────────────────────────────────┐
                                           │  Kubernetes Cluster + Prometheus│
                                           └─────────────────────────────────┘
```

---

## Bundled Agent Skills (`skills/`)

| Skill Name | Purpose | Offline Scripts (`scripts/`) | Reference Docs (`references/`) |
|------------|---------|------------------------------|--------------------------------|
| `onboarding-and-migrating-to-argo-rollouts` | Validate Deployments, choose Direct vs `workloadRef` migration, convert live or offline, and safely scale down/delete legacy Deployments | `lint_deployment_manifest.py`, `convert_deployment_to_rollout.py`, `convert_rollout_to_deployment.py`, `generate_scale_down_manifest.py`, `generate_argocd_ignore_differences.py` | `migration-modes.md`, `gitops-integration.md` |
| `progressing-argo-rollouts` | Trigger canary/blue-green rollouts, verify step health & metrics, promote, pause/resume, or abort across single or multi-cluster waves | `render_canary_steps.py` | `strategy-playbooks.md`, `traffic-routing.md`, `multi-cluster-waves.md` |
| `gating-rollouts-with-analysis-and-experiments` | Configure Prometheus `AnalysisTemplate` / `ClusterAnalysisTemplate`, run A/B `Experiment`s with `specRef`, and compare canary vs stable metrics | `generate_analysis_template.py`, `validate_analysis_template.py` | `prometheus-analysis-queries.md`, `experiment-design.md` |
| `troubleshooting-argo-rollouts` | Diagnose degraded, stuck, paused, or `InvalidSpec` rollouts using `argo_diagnose_rollout` and execute targeted recovery | *(uses live `argo_diagnose_rollout`)* | `rollout-error-catalog.md` |

---

## Available MCP Tools (15 Tools across 4 Toolsets)

Every tool enforces `<= 8` parameters and returns structured Pydantic models (`ExecutionResult`, `ReadinessReport`, `RolloutDiagnosisReport`, `CanaryMetricsComparison`).

### Toolset: `rollouts`
| Tool | Read-Only? | `dry_run` Default | Destructive Gate | Description |
|------|------------|-------------------|------------------|-------------|
| `argo_create_rollout` | No | `True` | No | Create a Rollout (`canary`, `bluegreen`, or `rolling`) and auto-create companion Services |
| `argo_set_rollout_image` | No | `False` | No | Update container image on a direct or `workloadRef` Rollout |
| `argo_configure_rollout_strategy` | No | `True` | No | Patch canary steps, Services, Traefik/Gateway API routing, `workloadRef.scaleDown`, or repair conflicting strategy blocks |
| `argo_manage_rollout_lifecycle` | No | N/A | On `abort` / `skip_analysis` | Execute `promote`, `promote_full`, `pause`, `resume`, `abort`, `retry`, or `skip_analysis` |
| `argo_delete_rollout` | No | N/A | Yes (`confirm` / elicit) | Delete a Rollout (and optionally companion resources); blocks if `workloadRef` Deployment is at 0 replicas |

### Toolset: `analysis`
| Tool | Read-Only? | `dry_run` Default | Destructive Gate | Description |
|------|------------|-------------------|------------------|-------------|
| `argo_configure_analysis_template` | No | `True` | No | Create/update an `AnalysisTemplate` or `ClusterAnalysisTemplate` and link it to a Rollout |
| `argo_delete_analysis_template` | No | N/A | Yes (`confirm` / elicit) | Delete a namespace or cluster-scoped AnalysisTemplate |
| `argo_create_experiment` | No | `False` | No | Launch an A/B `Experiment` with `specRef` (`stable`/`canary`/`active`/`preview`) or pod templates |
| `argo_delete_experiment` | No | N/A | Yes (`confirm` / elicit) | Delete an Experiment resource |
| `argo_compare_canary_metrics` | **Yes** | N/A | No | Compare live Prometheus metrics (error rate, P99/P95 latency) between canary and stable pods |

### Toolset: `migration`
| Tool | Read-Only? | `dry_run` Default | Destructive Gate | Description |
|------|------------|-------------------|------------------|-------------|
| `argo_validate_deployment_readiness` | **Yes** | N/A | No | Score a live Deployment (0–100) for migration readiness and detect container ports |
| `argo_convert_deployment_to_rollout` | No | `True` | No | Convert a live Deployment into a Rollout (`direct` or `workload_ref`) and create Services |
| `argo_convert_rollout_to_deployment` | No | `True` | No | Reverse-migrate a live Rollout back into a standard Kubernetes Deployment |
| `argo_manage_legacy_deployment` | No | `True` | On `delete` / `scale=0` | Scale or delete a legacy Deployment after verifying the replacing Rollout is `Healthy` |

### Toolset: `diagnostics`
| Tool | Read-Only? | `dry_run` Default | Destructive Gate | Description |
|------|------------|-------------------|------------------|-------------|
| `argo_diagnose_rollout` | **Yes** | N/A | No | Single-call diagnostic snapshot returning deterministic `diagnosis_codes`, conditions, failing metrics, warning events, and pod statuses |

---

## Available MCP Resources (13 Live Resources)

| Resource URI | Description |
|--------------|-------------|
| `argorollout://server/capabilities` | Server write mode (`allow_write`), enabled `toolsets`, cluster connectivity, and installed CRDs |
| `argorollout://cluster/health` | Cluster API reachability and Argo Rollouts controller health |
| `argorollout://cluster/namespaces` | Available Kubernetes namespaces |
| `argorollout://cluster/contexts` | Available kubeconfig contexts and active context (credentials stripped) |
| `argorollout://rollouts/list` | Cluster-wide Rollout inventory with phase, replica counts, and `health_score` (0–100) |
| `argorollout://rollouts/{namespace}/{name}/detail` | Concise JSON status (`phase`, `healthScore`, `canaryWeight`, `currentStep`, `pauseConditions`, `replicas`) |
| `argorollout://rollouts/{namespace}/{name}/manifest` | Sanitized live Rollout YAML (`managedFields`, `last-applied-configuration`, and literal env values redacted) |
| `argorollout://rollouts/{namespace}/{name}/analysisruns` | Recent `AnalysisRun` phases, metric measurements, and failure messages for a Rollout |
| `argorollout://analysistemplates/{namespace}` | Available `AnalysisTemplate` and `ClusterAnalysisTemplate` definitions |
| `argorollout://experiments/{namespace}/{name}/status` | Live `Experiment` phase, template replica counts, and linked `AnalysisRun` statuses |
| `argorollout://history/{namespace}/{deployment}` | Separated ReplicaSet `revisions` and Kubernetes status `conditions` |
| `argorollout://metrics/prometheus/status` | Prometheus reachability and query readiness (`status: "unavailable"` when Prometheus is unreachable) |
| `argorollout://metrics/{namespace}/{service}/summary` | Live service Golden Signals summary (request rate, error ratio, latency quantiles) |

---

## Configuration & CLI Flags

The server defaults to **read-only mode** (`allow_write=False`) and supports both CLI flags and environment variables:

```bash
uv run argo-rollout-mcp-server \
  --allow-write \
  --toolsets rollouts,analysis,migration,diagnostics \
  --prometheus-url http://prometheus:9090 \
  --kubeconfig ~/.kube/config \
  --context prod-us-east-1 \
  --transport stdio
```

| CLI Flag | Environment Variable | Default | Description |
|----------|----------------------|---------|-------------|
| `--allow-write` | `MCP_ALLOW_WRITE=true` | `false` | Enable mutating tools (create, update, lifecycle, convert, delete) |
| `--read-only` | `MCP_READ_ONLY=true` | `true` | Force read-only mode (overrides `--allow-write`) |
| `--toolsets` | `MCP_TOOLSETS` | `all` | Comma-separated toolsets: `all`, `rollouts`, `analysis`, `migration`, `diagnostics` |
| `--prometheus-url` | `PROMETHEUS_URL` | *(none)* | Prometheus base URL for `argo_compare_canary_metrics` and metrics resources |
| `--kubeconfig` | `K8S_KUBECONFIG` | `~/.kube/config` | Path to kubeconfig file |
| `--context` | `K8S_CONTEXT` | *(active)* | Kubernetes context name |
| `--transport` | `MCP_TRANSPORT` | `stdio` | Transport protocol: `stdio`, `http`, or `sse` |
| `--host` | `MCP_HOST` | `0.0.0.0` | HTTP bind host |
| `--port` | `MCP_PORT` | `8768` | HTTP bind port |
| `--path` | `MCP_PATH` | `/mcp` | HTTP endpoint path |
| `--debug` | `MCP_LOG_LEVEL=DEBUG` | `INFO` | Enable debug logging |

### Multi-Cluster Configuration (`mcp.json`)

For multi-cluster progressive delivery, configure one server entry per Kubernetes context in `mcp.json` (see `skills/progressing-argo-rollouts/references/multi-cluster-waves.md` for wave progression gates).

---

## Migration Guide: `v0.1.x` → `v0.2.0` (Clean Break)

### Tool Migration Table

| `v0.1.x` Tool Name | `v0.2.0` Replacement | Notes |
|--------------------|----------------------|-------|
| `argo_update_rollout(update_type="image", ...)` | `argo_set_rollout_image` | Dedicated runtime tool (`dry_run=False` default) |
| `argo_update_rollout(update_type="strategy" \| "traffic_routing" \| "workload_ref_scale_down" \| "remove_conflicting_strategy")` | `argo_configure_rollout_strategy` | Dedicated strategy/routing configuration tool (`dry_run=True` default) |
| `validate_deployment_ready` | `argo_validate_deployment_readiness` | Live cluster readiness validator; use `scripts/lint_deployment_manifest.py` for offline files |
| `convert_deployment_to_rollout` | `argo_convert_deployment_to_rollout` | Live cluster converter (`dry_run=True` default); use `scripts/convert_deployment_to_rollout.py` for offline files |
| `convert_rollout_to_deployment` | `argo_convert_rollout_to_deployment` | Live cluster reverse converter (`dry_run=True` default); use `scripts/convert_rollout_to_deployment.py` for offline files |
| `create_stable_canary_services` | `argo_create_rollout` / `argo_configure_rollout_strategy` | Services are created automatically or via `scripts/convert_deployment_to_rollout.py --include-services` |
| `generate_argocd_ignore_differences` | `skills/onboarding-and-migrating-to-argo-rollouts/scripts/generate_argocd_ignore_differences.py` | Moved to deterministic offline skill script |
| `argo_configure_analysis_template(mode="generate_yaml")` | `argo_configure_analysis_template(dry_run=True)` or `scripts/generate_analysis_template.py` | Unified around `dry_run=True` preview and offline script |

### Resource & Prompt Migration Table

| `v0.1.x` Resource / Prompt | `v0.2.0` Replacement |
|----------------------------|----------------------|
| `argorollout://health/summary` | Folded into `argorollout://rollouts/list` (`health_score` per rollout) |
| `argorollout://health/{ns}/{name}/details` | Replaced by `argo_diagnose_rollout` tool and `argorollout://rollouts/{ns}/{name}/detail` |
| `argorollout://history/all` | Removed (avoid O(N) cluster-wide ReplicaSet scan); use `argorollout://history/{ns}/{name}` |
| `onboard_application_guided` prompt | `skills/onboarding-and-migrating-to-argo-rollouts/SKILL.md` |
| `canary_deployment_guided` / `blue_green_deployment_guided` / `rolling_update_guided` / `multi_cluster_canary_guided` prompts | `skills/progressing-argo-rollouts/SKILL.md` |
| `cost_optimized_deployment_guided` prompt | Removed (simulated `orch_*` dead code removed) |

---

## Running Tests

```bash
cd src/argo-rollout-mcp-server
uv run pytest -v
```

The test suite includes **78 tests** across three layers:
- `tests/unit/` — Service `dry_run` propagation, `workloadRef` outage guards, `diagnose_rollout` classification, redaction, middleware coercion/caching, error translation, `specRef` resolution, and named port resolution.
- `tests/integration/` — In-memory FastMCP `Client(mcp)` tests for toolsets/read-only filtering, `<= 8` parameter schema budgets, `dry_run` defaults, MCP Elicitation + `confirm` gates, all 13 live resources, 0 prompts, and end-to-end onboarding/canary/analysis workflows.
- `tests/skills/` — Contract tests for `plugin.json` (closed Agent Plugins v1.0.0 schema), `mcp.json`, `SKILL.md` frontmatter and line budgets (`< 500` lines), gate markers, tool/resource cross-reference integrity, and offline execution of all 8 skill scripts.

---

## License

Apache 2.0 — see [LICENSE](../../LICENSE).
