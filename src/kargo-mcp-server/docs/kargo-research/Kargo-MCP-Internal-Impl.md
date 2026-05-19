# Kargo MCP Server (Python) – Implementation Guide and Internal Architecture

## Overview

This document describes a Python implementation of a Model Context Protocol (MCP) server that exposes Kargo’s promotion capabilities via tools and resources for LLM‑driven workflows. It builds on the conceptual Kargo MCP design and focuses specifically on backend logic: module structure, Kargo REST client, Pydantic models, FastMCP wiring, and extension points for auth, RBAC, and observability.[^1][^2][^3][^4]

The goal is that a development team can implement and evolve the server using this document alone, without having to re‑consult MCP or Kargo documentation for basic design decisions.[^2][^4]

***

## High‑Level Architecture

### Components

The Python Kargo MCP server is organized into four main layers:

1. **Configuration layer (`config.py`)** – encapsulates Kargo API connection details (base URL, auth mode, tokens, timeouts) using Pydantic’s `BaseSettings` so everything is centrally managed via environment variables.[^3]
2. **Model layer (`kargo_models.py`)** – defines Pydantic models for Kargo resources as seen over REST: Projects, Stages, Warehouses, Freight, Promotions, and their summaries, mirroring Kargo’s CRD and API schemas.[^5][^2]
3. **Client layer (`kargo_client.py`)** – a thin, async HTTP client built on `httpx` that calls Kargo’s `/v1beta1` REST endpoints, handles authentication, and converts JSON payloads into Pydantic models.[^2][^3]
4. **MCP server layer (`server.py`)** – uses the MCP Python SDK’s FastMCP interface to register tools and resources that delegate to the `KargoApiClient`, with a typed lifespan context for initialization and cleanup.[^4][^3]

This separation lets the MCP layer stay small and declarative while all Kargo‑specific logic lives in the client and model layers.[^4]

### Process and transport

- The MCP server runs as a long‑lived Python process, typically using the SDK’s `mcp.run(transport="stdio")` entry point so editors and clients (e.g. Claude Desktop) can connect over stdio.[^3][^4]
- Alternatively, the FastMCP `streamable_http_app()` can be mounted under an ASGI server (Uvicorn/Starlette) for HTTP transport, using the same tools/resources with a different deployment topology.[^4]

***

## Configuration Layer (`config.py`)

### Settings model

The configuration layer uses a Pydantic `BaseSettings` class to keep all external configuration in environment variables:

- `base_url` – Kargo REST API base URL (e.g. `https://kargo.example.com` or `http://localhost:8080` for local port‑forward).[^2]
- `verify_ssl` – flag to enable/disable TLS verification (should be `True` in production).
- `auth_mode` – enum with values:
  - `ADMIN` – server logs in as Kargo admin and obtains a JWT.[^6]
  - `STATIC` – server uses a preconfigured bearer token (service account or API token).[^2]
  - `PASSTHROUGH` – server forwards the caller’s token (e.g. from an LLM gateway) to Kargo so Kargo enforces RBAC.
- Secrets:
  - `admin_password` – admin password for `ADMIN` mode.
  - `static_bearer_token` – token for `STATIC` mode.
- `timeout_seconds` – global timeout for all HTTP calls.

Environment variable naming is standardized via `env_prefix = "KARGO_"`, so variables like `KARGO_BASE_URL` and `KARGO_AUTH_MODE` configure the server at runtime.[^3]

### Auth modes and impact

Auth mode influences how the `KargoApiClient` constructs `Authorization` headers:

- In **ADMIN** mode, the client performs a one‑time login to obtain a JWT and caches it for subsequent calls; if the token expires, the client can refresh it on the next request.[^2]
- In **STATIC** mode, the token is loaded from settings once and reused across all requests.
- In **PASSTHROUGH** mode, tools that represent user actions (e.g. `approve_freight`, `create_promotion`) receive a `bearer_override` value derived from the MCP request context and forward that token unchanged, so Kargo’s RBAC and `promote` verb enforcement are applied per caller.[^7][^8]

***

## Model Layer (`kargo_models.py`)

### General conventions

The model layer mirrors Kargo’s REST JSON with Pydantic models:

- Each top‑level resource (Project, Stage, Warehouse, Freight, Promotion) uses Kubernetes‑style `apiVersion`, `kind`, `metadata`, `spec`, and `status` fields.[^5]
- `ObjectMeta` encapsulates metadata: `name`, `namespace`, `labels`, `annotations`, and `creationTimestamp`.
- Aliases (`Field(alias="...")`) are used wherever Kargo’s JSON uses camelCase or specific field names (e.g. `freightId`, `lastPromotionId`), while Python code uses snake_case for readability.[^5]

The model layer also adds “summary” models that present a compact, LLM‑friendly view of resources for MCP tools and resources.

### Project models

- `PromotionPolicy` captures project‑level promotion defaults such as `autoPromotionEnabled` and `selectionStrategy` to reflect Kargo’s promotion policy concepts.[^5]
- `ProjectSpec` includes an optional `promotionPolicy` and leaves room for other project‑wide defaults.
- `ProjectStatus` contains a generic `conditions` list that can be extended if the REST API exposes rich status.
- `Project` aggregates the above and is used for full project reads, while `ProjectSummary` includes derived fields like `stage_count` and `auto_promotion_enabled` for quick overviews.

### Stage models

- `RequestedFreightOrigin` represents a source of freight (Warehouse or Stage, identified by kind/name).[^5]
- `RequestedFreight` includes the origin and `availabilityStrategy` (e.g., All/Any), matching the semantics of Kargo’s `requestedFreight` blocks.[^9][^5]
- `StageSpec` contains `variables`, `requestedFreight`, `promotionTemplateRef`, and leaves room for verification settings.
- `StageStatus` tracks `currentFreightId`, `lastPromotionId`, and `conditions` (health, error states).[^10]
- `Stage` is the full resource; `StageSummary` adds derived `upstream_stages`, `downstream_stages`, `current_freight_id`, and a boolean `auto_promotion_enabled` for quick consumption by the LLM.

### Warehouse models

- `WarehouseSource` encodes each subscribed artifact source (type, URL, selector), consistent with Kargo’s Warehouse spec.[^11]
- `WarehouseSpec` is a list of `sources`.
- `WarehouseStatus` tracks `lastSyncTime` and `conditions` for sync health.
- `Warehouse` is the full resource; `WarehouseSummary` lists name and `source_types` derived from `sources`.

### Freight models

- `ArtifactReference` captures a `type` (`image`, `git`, `helm`) and a `ref` (tag, commit, version).[^5]
- `FreightSpec` is a list of `artifacts`.
- `FreightStageState` tracks, per stage, whether freight is `available`, `promoted`, and `verified`.
- `FreightStatus` adds `discoveredTime`, per‑stage states, summary `message`, and high‑level `state` (for infra steps, e.g., Terraform success/failure).[^12][^13]
- `Freight` is the full resource; `FreightSummary` rolls up ID, artifacts, and per‑stage data for LLM use.

### Promotion models

- `PromotionStepStatus` represents each step’s name, type, status, start/finish timestamps, and an optional `logUrl` if Kargo exposes it.[^14][^2]
- `PromotionSpec` includes `stage`, `project`, `freightId`, and `triggerType` (`auto` or `manual`).
- `PromotionStatus` aggregates overall `state`, `message`, the list of `steps`, and timing data.
- `Promotion` is the full resource; `PromotionSummary` captures commonly used fields for tools.

These models create a strongly‑typed bridge between the Kargo REST API and MCP, allowing FastMCP to auto‑derive schemas from return types and tool arguments.[^3][^4]

***

## Client Layer (`kargo_client.py`)

### Responsibilities

`KargoApiClient` is a thin async wrapper over Kargo’s REST API that is responsible for:

- Constructing REST paths under `/v1beta1` for projects, stages, warehouses, freight, and promotions.[^2]
- Injecting `Authorization` headers based on the configured auth mode and any per‑request overrides.
- Parsing JSON into Pydantic models via `model_validate`.
- Raising a typed `ApiError` for non‑2xx responses, including status code, reason phrase, and raw body for diagnostics.

All MCP tools and resources call into this client; no tool calls Kargo directly.

### HTTP plumbing

The client uses `httpx.AsyncClient` with:

- `base_url` set from settings.
- TLS verification and timeouts configured from settings.[^3]

A private `_request` method handles:

1. Ensuring an admin login if needed (`ensure_admin_login` for `ADMIN` mode).
2. Merging the appropriate headers (`Accept: application/json` and `Authorization: Bearer <token>` if present).
3. Performing the HTTP request and turning non‑2xx into `ApiError` exceptions.

This centralizes retry, timeout, and error handling logic.

### Admin login helper

`ensure_admin_login` is responsible for obtaining and caching an admin token:

- It validates that `KARGO_ADMIN_PASSWORD` is set when `auth_mode == ADMIN`.
- It posts to an admin login endpoint (e.g. `/v1beta1/admin/login` – adapt to your actual deployment).[^2]
- On success, it caches `self._token` for subsequent calls.

If tokens expire, this logic can be extended to detect 401 responses and refresh the token automatically.

### Project operations

Key methods:

- `list_projects()`:
  - Calls `GET /v1beta1/projects` and parses the JSON `items` array into `Project` models.
  - Derives `ProjectSummary` objects, computing `auto_promotion_enabled` from the spec.
- `get_project(name)`:
  - Calls `GET /v1beta1/projects/{name}` and returns a `Project`.

Optionally, `stage_count` can be computed by calling `list_stages(project)` and counting stages.

### Stage operations

- `list_stages(project)`:
  - Calls `GET /v1beta1/projects/{project}/stages` and parses `Stage` items.[^10]
  - Builds `upstream_map` and `downstream_map` by inspecting `spec.requestedFreight` where the origin kind is `Stage`, producing `StageSummary` objects.
- `get_stage(project, stage)`:
  - Calls `GET /v1beta1/projects/{project}/stages/{stage}` and returns a `Stage`.
- `upsert_stage(project, stage, spec)`:
  - Calls a `PUT` or `apply`‑style endpoint under `/v1beta1/projects/{project}/stages/{stage}` with a CRD‑like payload.
  - Uses a helper `_validate_stage_spec_for_cycles` to reject obvious self‑referential `requestedFreight` entries before applying, reducing the chance of creating cyclic DAGs.

The DAG guardrail implementation can be extended to perform full cycle detection by fetching all stages and running graph analysis.

### Warehouse operations

- `list_warehouses(project)`:
  - Calls `GET /v1beta1/projects/{project}/warehouses` and transforms each item into a `WarehouseSummary` with name and `source_types`.[^11]
- `get_warehouse(project, name)`:
  - Calls `GET /v1beta1/projects/{project}/warehouses/{name}` and returns a `Warehouse`.
- `refresh_warehouse(project, name)`:
  - Calls `POST /v1beta1/projects/{project}/warehouses/{name}/refresh` to enqueue a refresh.[^15][^16]

### Freight operations

- `list_freight(project)`:
  - Calls `GET /v1beta1/projects/{project}/freight` and produces `FreightSummary` objects.
- `get_freight(project, freight_id)`:
  - Calls `GET /v1beta1/projects/{project}/freight/{freight}`.
- `approve_freight(project, freight_id, stage, bearer_override)`:
  - Calls `POST /v1beta1/projects/{project}/freight/{freight}/approve` with a JSON body containing the target stage.[^17]
  - Uses `bearer_override` to forward the caller’s token in `PASSTHROUGH` mode, ensuring Kargo enforces its `promote` verb on the stage.[^8][^7]

### Promotion operations

- `create_promotion(project, stage, freight_id, trigger_type, bearer_override)`:
  - Calls `POST /v1beta1/projects/{project}/stages/{stage}/promotions` with `{ "freightId": ..., "triggerType": ... }`.[^17][^2]
- `get_promotion(project, promotion_name)`:
  - Calls `GET /v1beta1/projects/{project}/promotions/{promotion}` and returns a `Promotion`.
- `list_promotions(project)`:
  - Calls `GET /v1beta1/projects/{project}/promotions` and builds `PromotionSummary` objects.
- `abort_promotion(project, promotion_name, bearer_override)`:
  - Calls a REST endpoint under `/v1beta1/projects/{project}/promotions/{promotion}:abort` or equivalent, mirroring the AbortPromotion API documented in Kargo.

### Verification operations

- `reverify_stage(project, stage, bearer_override)`:
  - Calls a verification endpoint (e.g., `/v1beta1/projects/{project}/stages/{stage}:verify`), matching the CLI’s `kargo verify stage` semantics.[^18]
  - Returns the updated `Stage` and allows the MCP server to surface new verification status.

An `asynccontextmanager` `kargo_client_ctx` wraps the client’s lifecycle so it can be used in FastMCP’s lifespan handler.[^3]

***

## MCP Server Layer (`server.py`)

### FastMCP server and lifespan context

The MCP server is defined via:

- `mcp = FastMCP(name="kargo-mcp-server", lifespan=app_lifespan)`

where `app_lifespan` is an async context manager that:

1. Loads `KargoApiSettings` from the environment.
2. Instantiates a `KargoApiClient` with those settings.
3. Yields an `AppContext` dataclass containing both.
4. Closes the HTTP client on shutdown.[^3]

Within tools/resources, the typed context is retrieved via:

```python
app = ctx.request_context.lifespan_context
```

which gives direct access to `app.kargo` (the REST client) and `app.settings`.

### Resource handlers (`@mcp.resource`)

Resource URIs are implemented using FastMCP’s `@mcp.resource` decorator, which maps URI templates to Python coroutines.[^1][^4]

Examples:

- `kargo://projects` → `list_projects_resource`
  - Returns `list[ProjectSummary]` by calling `kargo.list_projects()`.
- `kargo://projects/{project}/stages` → `list_stages_resource`
  - Returns `list[StageSummary]` by calling `kargo.list_stages(project)`.
- `kargo://projects/{project}/warehouses` → `list_warehouses_resource`.
- `kargo://projects/{project}/freight` → `list_freight_resource`.
- `kargo://projects/{project}/promotions` → `list_promotions_resource`.

FastMCP uses function type hints and parameter names to derive JSON schemas for MCP clients automatically.[^1][^4]

### Tool handlers (`@mcp.tool`)

Tools are exposed via `@mcp.tool()` and are grouped into functional areas:

#### Promotion execution tools

- `promote_to_stage(project, stage, freight_id, ctx)`:
  - Retrieves the `AppContext` via `_ctx(ctx)`.
  - Determines `bearer_override` based on `AuthMode`; in `PASSTHROUGH`, it should pull the caller’s token from the MCP request metadata (to be wired by your gateway).[^3]
  - Calls `kargo.create_promotion(...)` and returns a `PromotionSummary`.

- `approve_freight(project, freight_id, stage, ctx)`:
  - Uses `bearer_override` for `PASSTHROUGH`.
  - Calls `kargo.approve_freight(...)` and returns a `FreightSummary`.

- `abort_promotion(project, promotion_name, ctx)`:
  - Calls `kargo.abort_promotion(...)` and returns a `PromotionSummary`.

- `reverify_stage(project, stage, ctx)`:
  - Calls `kargo.reverify_stage(...)` and returns a `StageSummary` reflecting updated verification state.

#### Lifecycle and discovery tools

- `refresh_warehouse(project, warehouse, ctx)`:
  - Calls `kargo.refresh_warehouse()` and returns a human‑readable confirmation string.

- Convenience tools `list_projects` and `list_stages(project)` call the corresponding client methods and are redundant with resources but useful for LLM‑driven flows.

#### Typed spec management tool

A structured `UpsertStageInput` Pydantic model is defined:

```python
class UpsertStageInput(BaseModel):
    project: str
    stage: str
    spec: StageSpec
```

and used as the argument to an `upsert_stage` tool:

- `upsert_stage(args: UpsertStageInput, ctx)`:
  - Calls `kargo.upsert_stage(project=args.project, stage=args.stage, spec=args.spec)`.
  - Returns a `StageSummary`.

Using Pydantic input models for complex payloads gives the MCP client a precise schema to drive correct tool invocation and validation.[^3]

### Entry point and transport

The main script ends with:

```python
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

which makes the server runnable as a stdio MCP server for local development and editor integration. For HTTP deployments, `streamable_http_app()` can be mounted instead.[^4][^3]

***

## Extension Points and Best Practices

### Error handling and observability

- Wrap all Kargo client calls in try/except blocks at the tool level when you want to translate `ApiError` into more user‑friendly error messages for the LLM.
- Use FastMCP’s `ctx.info`, `ctx.debug`, and `ctx.report_progress` helpers in long‑running tools (e.g., promotions or rollbacks) to surface progress updates and troubleshooting details.[^4]
- Integrate structured logging (e.g., `structlog` or `logging` with JSON formatters) to record each MCP tool invocation and its Kargo API calls, including status codes and durations.

### RBAC and security

- In `PASSTHROUGH` mode, design a stable convention for passing caller tokens from your MCP client/gateway to the server (e.g., via custom fields in `ClientRequest.meta`) and use that token as `bearer_override` for all promotion and approval tools.[^3]
- Enforce additional, MCP‑side guardrails (e.g., deny `abort_promotion` for production stages unless a feature flag or extra confirmation is present), even if Kargo would allow the call.
- Continue to rely on Kargo/Kubernetes RBAC and the `promote` verb as the ultimate gatekeeper for promotion and approval operations.[^7][^8]

### Additional tools and resources

The same patterns can be used to add:

- `get_promotion_logs(project, promotion_name)` – lookup the failing step in `Promotion.status.steps` and fetch logs from your log backend.
- `describe_topology(project)` – call `list_stages(project)`, build a graph, and return a structured topology object.
- `analyze_promotion_blockers(project, freight_id)` – combine `get_freight`, `list_promotions`, and `get_stage` to produce diagnostics.
- `list_promotion_tasks` / `get_promotion_task` – additional model and client methods for PromotionTask CRDs, wired to tools and resources.

### Testing and local development

- Use the MCP Python SDK’s client (`ClientSession`) to drive end‑to‑end tests of tools and resources over stdio, ensuring the server responds as expected.[^19][^3]
- For integration tests against Kargo, run a local Kargo instance (e.g., using Helm and Kubernetes in Kind), port‑forward the API service, and set `KARGO_BASE_URL=http://localhost:8080` in your test environment.[^2]
- Mock the `KargoApiClient` in unit tests of the MCP layer, verifying that tools call the correct client methods with the expected arguments.

***

## Summary

This implementation guide specifies a complete but modular Python architecture for a Kargo MCP server: configuration via `BaseSettings`, Pydantic models for Kargo resources, an async REST client for `/v1beta1` endpoints, and a FastMCP server exporting tools and resources. By following this design, a development team can focus on wiring and testing concrete endpoints and fields against a live Kargo instance while keeping the MCP surface clean, typed, and aligned with both MCP and Kargo best practices.[^20][^1][^4][^2][^3]

---

## References

1. [How to Create an MCP Server in Python - FastMCP](https://gofastmcp.com/tutorials/create-mcp-server) - A step-by-step guide to building a Model Context Protocol (MCP) server using Python and FastMCP, fro...

2. [What's New in Kargo v1.9: API Tokens, Warehouse Performance ...](https://burrell.tech/blog/kargo-v1-9/) - Kargo v1.9 adds a REST API, JWT tokens for automation, and Warehouse caching that cuts artifact disc...

3. [MCP Python SDK - PyPI](https://pypi.org/project/mcp/1.7.1/) - Model Context Protocol SDK

4. [The official Python SDK for Model Context Protocol servers ...](https://github.com/modelcontextprotocol/python-sdk) - The official Python SDK for Model Context Protocol servers and clients - modelcontextprotocol/python...

5. [Key Kargo Concepts | Kargo Docs](https://docs.kargo.io/concepts/) - Find out more about key Kargo concepts - stages, freight, warehouses, promotions, and more

6. [Secure Configuration | Kargo Docs](https://docs.kargo.io/operator-guide/security/secure-configuration/) - The purpose of this document is to direct operators' attention to specific

7. [CVE-2026-27111: Kargo has Missing Authorization Vulnerabilities ...](https://advisories.gitlab.com/pkg/golang/github.com/akuity/kargo/CVE-2026-27111/) - Kargo's authorization model includes a promote verb – a non-standard Kubernetes "dolphin verb" – tha...

8. [Access Controls - Kargo Docs](https://docs.kargo.io/user-guide/security/access-controls/) - Most access controls in Kargo are within the purview of highly-privileged

9. [Working with Stages | Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-stages) - The spec.vars field allows you to define variables that can be referenced anywhere in the Stage spec...

10. [Working with Stages](https://release-1-1.docs.kargo.io/how-to-guides/working-with-stages/) - Learn how to work effectively with Stages

11. [Working with Warehouses - Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-warehouses/) - When a Warehouse observes a new revision of any artifact to which it subscribes, it creates a new Fr...

12. [tf-apply | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/tf-apply) - Promotion Steps; tf-apply. On this page. tf-apply. info. This promotion step is only available in Ka...

13. [tf-output | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/tf-output) - This promotion step is only available in Kargo on the Akuity Platform, versions v1.9 and above. Addi...

14. [promotion](https://pkg.go.dev/github.com/akuity/kargo/pkg/promotion)

15. [GitLab Webhook Receiver - Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/webhook-receivers/gitlab/) - "Refreshing" a Warehouse resource means enqueuing it for immediate reconciliation by the Kargo contr...

16. [Unable to properly authenticate with `--kubeconfig` · akuity kargo ...](https://github.com/akuity/kargo/discussions/5722) - $ kargo refresh warehouse --project <project> <warehouse> Error: refresh Warehouse: [POST /v1beta1/p...

17. [CVE-2026-27111 | Tenable®](https://www.tenable.com/cve/CVE-2026-27111) - Kargo manages and automates the promotion of software artifacts. From v1.9.0 to v1.9.2, Kargo's auth...

18. [Verifying Freight in a Stage - Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/verification/) - Learn how to verify a Stage after Promotion

19. [Building a Simple MCP Server in Python - Machine Learning Mastery](https://machinelearningmastery.com/building-a-simple-mcp-server-in-python/) - Build a working MCP server in Python using FastMCP with tools, resources, and prompts.

20. [Home | Kargo Docs](https://docs.kargo.io)

