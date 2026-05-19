# Designing a Comprehensive Kargo MCP Server for Continuous Promotion

## Executive Summary

Kargo is a continuous promotion orchestration layer created by the Argo team to complement Argo CD by automating multi‑stage promotions using GitOps principles. It introduces core concepts such as Projects, Warehouses, Freight, Stages, and Promotions, each backed by Kubernetes custom resources, to model and control how changes flow across environments or other promotion targets.[^1][^2][^3][^4][^5][^6]

This report proposes a detailed design for a Model Context Protocol (MCP) server that fully exposes Kargo’s promotion capabilities to language‑model clients. The design defines a rich resource model, an extensive tool surface, and opinionated workflows that cover application and infrastructure promotion, policy management, approval flows, troubleshooting, and integration with Argo CD and other downstream systems. The goal is to make promotions discoverable, explainable, and automatable through natural‑language interaction while mapping cleanly to Kargo’s underlying CRDs and RBAC model.[^7][^8][^9][^10][^11][^12]

***

## Kargo Core Concepts and Resource Types

### Project

A Kargo project is the main unit of organization and tenancy, grouping all related Kargo resources that describe one or more delivery pipelines. Each project is represented by a cluster‑scoped `Project` Kubernetes resource; reconciling this resource creates a dedicated, specially labeled namespace and required boilerplate objects such as ServiceAccounts and RBAC bindings. Deleting the `Project` deletes (or can be triggered by deleting) the corresponding namespace, ensuring lifecycle coupling between the logical project and its Kubernetes resources.[^5][^11][^6]

Projects also embed promotion policies that control whether stages are eligible for automatic promotion of new freight or require manual intervention. These `PromotionPolicy` settings can be extended to support finer‑grained options such as per‑origin auto‑promotion and selection strategies.[^13][^11][^14]

### Stage

Stages are the most important Kargo concept and represent promotion targets, typically corresponding to environments such as dev, test, UAT, or production, but defined in a way that focuses on purpose rather than physical location. Stages form a directed acyclic graph (DAG) that describes the promotion flow, allowing multiple upstream and downstream relationships and complex multi‑pipeline topologies.[^15][^6][^13]

Each Stage is a namespaced `Stage` custom resource whose `spec` includes four main areas: variables, requestedFreight, promotionTemplate / referenced PromotionTask, and optional verification configuration. Stages decide what freight they accept (origin(s), upstream stages, availability strategy), how promotions are executed, and how successful promotions are verified before freight becomes eligible for downstream stages.[^16][^13][^15]

### Warehouse

Warehouses represent subscriptions to artifact sources such as container image registries, Git repositories, or Helm chart repositories. Each `Warehouse` monitors one or more sources and, when it observes a new revision of any subscribed artifact, it constructs a new `Freight` resource representing that collection of artifact revisions as a unit.[^2]
[^2]

This decouples discovery of change from promotion, enabling Kargo to treat collected artifacts as first‑class units for promotion, traceability, and policy evaluation across stages.[^17][^2]

### Freight

Freight is Kargo’s abstraction for a promotable change: a single piece of freight is a set of references to one or more versioned artifacts such as container images, Kubernetes manifests, or Helm charts. Freight is created by Warehouses when new artifacts are discovered, and then flows through stages according to promotion policies, templates, and verification outcomes.[^6][^13][^2]

At each Stage, freight can be auto‑promoted or wait for manual approval, and once verified, it becomes eligible for promotion to downstream stages, allowing Kargo to model multi‑stage application and infrastructure delivery pipelines.[^18][^13]

### Promotion, PromotionTask, and Promotion Steps

A promotion in Kargo is a request to move a specific piece of freight into a specified stage. At design time, users define promotion behavior via Stage `promotionTemplate` fields and reusable `PromotionTask` (and `ClusterPromotionTask`) resources, which are referenced by Stages for modular, DRY promotion logic. At runtime, Kargo creates `Promotion` resources, inflates tasks into step execution graphs, and runs them using built‑in step types for Git, Helm, Argo CD, CI integration, and notifications.[^19][^7][^16][^6]

The Promotion Steps reference includes a catalog of step types such as `git-clone`, `git-commit`, `git-push`, `git-open-pr`, `helm-template`, `yaml-update`, `kustomize-build`, `argocd-update`, `gha-dispatch-workflow`, `gha-wait-for-workflow`, Terraform/OpenTofu‑related steps such as `tf-apply` and `tf-output`, and integrations such as `jira` and ServiceNow steps. Together these allow promotions to drive Kubernetes, Helm, Terraform/OpenTofu, GitHub Actions, Jira, and Argo CD workflows.[^20][^21][^22][^23][^24][^25][^3][^7]

### RBAC and Kargo Roles

Kargo exposes RBAC primarily through the Project and Project namespace, relying on Kubernetes ServiceAccounts, Roles, and RoleBindings. Higher‑level "Kargo Roles" serve as abstractions over these components, with the Kargo CLI providing `create`, `grant`, `revoke`, and `delete` operations that manage the underlying ServiceAccount, Role, and RoleBinding triplet.[^26][^12][^5]

Promotion‑specific permissions such as the non‑standard `promote` verb can be scoped to specific stages or projects, enabling fine‑grained control over who can approve or trigger promotions in multi‑tenant systems.[^27][^28]

***

## Kargo Promotion Lifecycle and Usage Patterns

### End‑to‑End Promotion Flow

A typical Kargo promotion flow for an application or infrastructure change is as follows:[^13][^1]

1. A Warehouse detects a new artifact revision (e.g., new container image, Git commit, or Helm chart tag) and creates a corresponding Freight resource.
2. Freight becomes available to the first Stage that directly accepts freight from the Warehouse, subject to any requestedFreight and upstream conditions.
3. Depending on the Stage’s auto‑promotion policy, the freight is either auto‑promoted or waits for an explicit Promotion request and approval.
4. Promotion execution runs the Stage’s referenced PromotionTask or inline promotionTemplate, performing steps such as Git updates, Helm rendering, Argo CD application updates, and CI/test invocations.[^7][^13]
5. Optional verification runs after promotion, which may include health checks, Argo Rollouts analysis, integration tests, or other validation; only verified freight is considered eligible for downstream stages.[^29][^3]
6. Once verified, freight is exposed as available to downstream stages according to requestedFreight relationships and availability strategies, allowing subsequent promotions to propagate the same freight through staging, UAT, production, or infrastructure tiers.[^15][^13]

This workflow applies equally to application deployments and to infrastructure changes driven via tools such as the Pulumi Kubernetes Operator, Terraform/OpenTofu, or Argo CD ApplicationSets.[^3][^20][^7]

### Auto‑Promotion vs Manual Promotion

Kargo supports both automated and manual promotion semantics aligned with promotion policies configured at the Project or Stage level.[^11][^13]

- Auto‑promotion policies like `NewestFreight` continuously promote the newest verified freight as soon as it becomes available, ideal for fast‑moving lower environments such as dev or test.[^13][^15]
- Policies such as `MatchUpstream` promote whichever freight is currently active in the upstream Stage, allowing downstream stages to mirror another stage’s state instead of racing ahead.[^15]
- Project promotion policies and feature requests such as per‑Warehouse auto‑promotion control enable more granular behaviour, for example auto‑promoting from a dev‑tags Warehouse but requiring manual promotion for semver release tags.[^14][^13]

Manual approvals can be performed through the Kargo UI or CLI, where an approver explicitly approves promotion of a specific freight for a stage before promotion can proceed.[^26][^18]

### Multi‑Origin and Multi‑Pipeline Scenarios

Stages can request freight from one or more origins, including Warehouses and upstream stages, enabling the definition of multiple logical pipelines converging on shared stages. A Stage can thus participate in multiple pipelines that each deliver different collections of artifacts independently, although this is considered advanced configuration that should be used carefully.[^15]

Availability strategies in requestedFreight (e.g., requiring freight to be verified in multiple upstream stages) allow modeling complex release gates, such as requiring combined verification in both QA and UAT before a production stage accepts freight.[^13][^15]

### Infrastructure Promotion Use Cases

Kargo’s promotion concepts apply not only to Kubernetes applications but also to infrastructure deliveries using tools such as Terraform, Pulumi, or other GitOps‑managed stacks.[^30][^20][^3]

- Using the Pulumi Kubernetes Operator, each Stage can map to a Pulumi Stack that manages infrastructure for that environment, with promotions updating the Stack configuration to reference new freight or state.[^20]
- Promotion steps like `yaml-update`, `tf-apply`, and Git operations enable OpenTofu/Terraform configuration updates to be modeled as freight promotions, with Kargo orchestrating the path across environments.[^21][^24][^3]
- When combined with policy‑driven promotion, this allows infrastructure and applications to share promotion workflows, guardrails, and approvals while still being managed by distinct controllers or operators.[^30][^17]

***

## MCP Concepts Relevant to a Kargo Server

### MCP Resources

In the Model Context Protocol, resources represent data exposed by servers to clients, such as file contents, database records, API responses, or live system data, each identified by a unique URI. Resources can be listed, fetched, and sometimes watched, and they may contain either text or binary content, with metadata describing properties such as MIME type and description.[^8][^9]

For a Kargo MCP server, resources are the natural way to expose the state of Projects, Stages, Warehouses, Freight, Promotions, and PromotionTasks to the language model, providing structured context that can be combined with tool invocations.[^8][^6]

### MCP Tools

Tools in MCP are named operations that a server exposes for invocation by the language model, typically for actions such as querying databases, calling external APIs, or manipulating application state. Each tool is described with a schema for its input parameters and output shape, and tools are designed to be model‑controlled, meaning that the language model can discover and invoke them based on task context.[^10]

For Kargo, tools are used for imperative operations such as creating Projects, defining Stages, triggering Promotions, performing approvals, editing PromotionTasks, and inspecting recent events or logs.[^18][^16]

### MCP Server Implementation Practices

Reference MCP servers and development guides recommend a modular design where each capability (tools, resources, prompts) is defined with clear schemas and handlers, often using libraries such as Zod for validation and SDK helper classes for HTTP transport and JSON‑RPC handling.[^31][^32]

The recommended pattern is to create a central `McpServer` instance with metadata (name, version), then register tools and resources via registration functions that encapsulate logic, schemas, and annotations. HTTP or other transport integrations (e.g., Express‑based endpoints) delegate JSON‑RPC parsing, session management, and streaming to SDK transport helpers, simplifying implementation complexity.[^32][^31]

***

## High‑Level Goals for the Kargo MCP Server

The Kargo MCP server should provide a complete but safe interface to all Kargo promotion‑related capabilities, optimized for use by LLM‑driven agents and human operators collaborating through natural‑language interfaces.[^3][^30]

Key goals include:

- **Full promotion coverage:** Expose all relevant Kargo concepts—Projects, Stages, Warehouses, Freight, Promotions, PromotionTasks, PromotionPolicies, and RBAC roles—through MCP resources and tools.
- **GitOps‑aligned behaviour:** Ensure all operations respect GitOps principles, favoring declarative configuration changes over direct imperative modifications of running workloads, consistent with how Kargo treats configuration as code.[^4][^30]
- **Explainability:** Provide rich descriptions, promotion histories, verification results, and dependency graphs as resources so the model can explain promotion state and decisions.
- **Safety and guardrails:** Enforce Kargo’s promotion policies and RBAC, surface dry‑run and plan capabilities, and limit destructive operations through explicit tools and role checks.[^12][^27][^11]
- **Multi‑surface support:** Work equally well for application and infrastructure pipelines, including Argo CD, Helm, Terraform/OpenTofu, and Pulumi‑driven flows.[^7][^20][^3]

***

## Resource Model for the Kargo MCP Server

### Resource Naming and URIs

The server should define a coherent URI scheme under a `kargo://` authority, e.g.:

- `kargo://projects/{projectName}` — Project resources
- `kargo://projects/{projectName}/stages/{stageName}` — Stage resources
- `kargo://projects/{projectName}/warehouses/{warehouseName}` — Warehouse resources
- `kargo://projects/{projectName}/freight/{freightID}` — Freight resources
- `kargo://projects/{projectName}/promotions/{promotionID}` — Promotion resources
- `kargo://projects/{projectName}/promotionTasks/{taskName}` — PromotionTask resources
- `kargo://projects/{projectName}/roles/{roleName}` — Kargo Role abstractions

Each resource exposes a JSON representation of the corresponding Kargo CRD and selected status fields, plus derived fields such as computed DAG edges and effective auto‑promotion policies.[^5][^6][^15]

### Project Resource Schema

A Project resource should include:

- Metadata: `name`, `creationTimestamp`, labels/annotations.
- Core spec: promotion policies (including auto‑promotion enabled/disabled, default selection policies, per‑stage overrides), project RBAC configuration, and any project‑level defaults for Warehouses and Stages.[^11][^14]
- Derived fields: list of stages in the project, DAG topology (edges, roots, leaves), list of Warehouses, and summary of promotion flows.

This resource enables the model to understand the overall delivery topology and policy landscape for a project.[^6][^13]

### Stage Resource Schema

A Stage resource should include:

- Metadata: `name`, namespace, labels/annotations.
- Spec breakdown:
  - `variables` block, including templating variables for promotion tasks.[^15]
  - `requestedFreight` entries, including origin kind/name, sources (direct or upstream stages), availability strategy (e.g., All, Any), and any per‑origin auto‑promotion options.[^14][^15]
  - `promotionTemplate` reference or inline template, and associated PromotionTask references.[^16][^15]
  - `verification` configuration (e.g., Argo Rollouts analysis templates, test hooks, health checks).[^29]
- Status:
  - Current active freight, last promotion ID, last promotion status and timestamp.
  - Verification status for the current freight.
  - Condition summaries (e.g., healthy, degraded).

Derived fields should capture upstream/downstream stages and whether the stage participates in multiple pipelines or receives freight from multiple Warehouses.[^13][^15]

### Warehouse Resource Schema

A Warehouse resource should expose:

- Subscribed sources: container image repositories, Git repositories, Helm chart repositories, and any strategies (e.g., NewestBuild, SemVer) for selecting revisions.[^33][^2]
- Current and recent freight IDs created by the Warehouse, with artifact version summaries and timestamps.[^2]
- Status: last sync time, error conditions, and backoff behaviour if artifact discovery fails.[^2]

This information allows the MCP server to answer questions about where freight came from and why certain versions are present or missing.[^2][^13]

### Freight Resource Schema

Freight resources should include:

- Artifact references: list of container images (repo, tag, digest), Git commits (repo, branch, commit hash), Helm charts (repository, chart name, version), and other artifacts represented by the Freight.[^6][^2]
- Provenance: originating Warehouse, discovered time, triggering event/metadata (e.g., CI pipeline run, Git tag push).[^34][^2]
- Stage state: for each Stage in the project, fields indicating whether the freight is available, promoted, verified, or rolled back.[^18][^13]

This provides a project‑wide view of how a given change is progressing through the promotion graph.

### Promotion and PromotionTask Resource Schemas

Promotion resources represent individual promotion runs and should include:

- Target project and Stage.
- Freight ID.
- Trigger type (auto vs manual), initiator identity, and any approval metadata.[^18][^13]
- Step graph: list of steps executed (with types such as `git-clone`, `argocd-update`, `tf-apply`, `jira`), their statuses, durations, and logs URLs or summaries.[^23][^24][^21][^7]
- Verification outcome and any analysis results.[^29]

PromotionTask resources should include:

- Reusable step sequences, parameter schemas, and default values, including which steps interact with Argo CD, GitHub, Terraform/OpenTofu, or other systems.[^24][^16][^7]
- A list of Stages referencing the task, which the MCP server can derive by cross‑referencing Stage specs.[^35][^19]

### Role and RBAC Resource Schemas

RBAC abstractions should be modeled as Role resources that include:

- Underlying ServiceAccount name, Role rules, and RoleBindings affected by the Kargo Role.[^12]
- Effective permissions, particularly those related to promotion operations such as `promote`, `approve`, `rollback`, and configuration changes to Stages or PromotionTasks.[^36][^27]

These resources enable the MCP server to reason about whether a given operation should be exposed or blocked for a specific caller context.

***

## Tool Surface for the Kargo MCP Server

### Design Principles for Tools

The tool set should satisfy the following principles:

- **Idempotent where possible:** Declarative operations (e.g., upserting Projects, Stages, PromotionTasks) should be idempotent and safe to re‑invoke.
- **Separation of plan vs apply:** Tools that mutate promotion state (create Promotions, approve, rollback) should support dry‑run / plan modes where feasible, producing human‑readable plans.
- **Alignment with Kargo CRDs:** Tools should map closely to underlying Kargo APIs and CRDs, making it easy to reason about how they affect the system.[^5][^6]
- **Explicit side‑effects:** Tools that touch Argo CD, Git, or infrastructure controllers should clearly document their integration points and side‑effects.[^20][^7]

### Project‑Level Tools

- `kargo.list_projects`
  - **Purpose:** List all Kargo Projects, optionally filtered by label or name pattern.
  - **Backend:** Uses the Kargo API’s project‑listing endpoint (REST or gRPC, depending on deployment) to list CRD‑backed projects.[^37][^38]

- `kargo.get_project`
  - **Purpose:** Fetch a detailed Project resource, including DAG of stages and policies.
  - **Backend:** Retrieves a single Project plus associated ProjectConfig via Kargo API and Kubernetes CRDs.[^39][^5]

- `kargo.upsert_project`
  - **Purpose:** Create or update a Project with specified promotion policies and basic settings.
  - **Backend:** Applies a declarative manifest (either via Kargo’s resource‑apply API or directly via Kubernetes API) and returns the reconciled Project.[^40][^5]

- `kargo.delete_project`
  - **Purpose:** Delete a Project and associated namespace, subject to a confirmation flag.
  - **Backend:** Deletes the Project CRD and relies on Kargo’s controller to garbage‑collect the namespace.[^41][^5]

### Stage‑Focused Tools

- `kargo.list_stages`
  - **Purpose:** List all stages in a project, with promotion topology metadata.
  - **Backend:** Lists Stage resources in the project namespace and derives upstream/downstream relationships from `requestedFreight`.[^6][^15]

- `kargo.get_stage`
  - **Purpose:** Fetch a detailed Stage resource.
  - **Backend:** Retrieves the Stage CRD plus recent Promotion and verification status for its current freight.[^29][^15]

- `kargo.upsert_stage`
  - **Purpose:** Create or update a Stage, including requestedFreight, promotionTemplate/PromotionTask references, and verification settings.[^16][^15]
  - **Backend:** Applies Stage manifests, preferably via a declarative API.

- `kargo.plan_stage_changes`
  - **Purpose:** Compute a plan summarizing how proposed Stage spec changes would affect promotion topology, auto‑promotion behavior, and freight availability.
  - **Backend:** Runs a local DAG analysis on the desired spec vs current specs to detect added/removed edges and policy changes.

### Warehouse and Freight Tools

- `kargo.list_warehouses`
  - **Purpose:** List Warehouses for a project and their subscribed sources.[^2]
  - **Backend:** Lists Warehouse CRDs in the project namespace and returns subscription and status information.

- `kargo.get_warehouse`
  - **Purpose:** Fetch a detailed Warehouse resource.
  - **Backend:** Retrieves the Warehouse CRD and recent reconciliation status.[^42][^2]

- `kargo.list_freight`
  - **Purpose:** List freight in a project or for a given Warehouse or Stage.
  - **Backend:** Calls the freight‑listing API and aggregates per‑Stage availability/verification state.[^13][^2]

- `kargo.get_freight`
  - **Purpose:** Fetch a detailed Freight resource.
  - **Backend:** Retrieves Freight metadata and per‑Stage status from the Kargo API.[^38][^13]

### Promotion and Approval Tools

- `kargo.plan_promotion`
  - **Purpose:** Generate a promotion plan for moving a given freight into a stage, explaining steps and verification.
  - **Backend:** Reads the Stage’s promotionTemplate or PromotionTask and resolves the concrete step graph that will execute, without yet creating a Promotion.

- `kargo.create_promotion`
  - **Purpose:** Create a Promotion resource to move freight into a stage, respecting auto‑promotion policies and RBAC.
  - **Backend:** Uses the Kargo REST API’s promotion endpoints, which, as of v1.9.x, are under `/v1beta1/projects/{project}/stages/{stage}/promotions` and `/promotions/downstream` for downstream promotions.[^28][^27]

- `kargo.get_promotion`
  - **Purpose:** Fetch detailed status of a specific Promotion.
  - **Backend:** Calls the promotion‑get API (REST or gRPC) and returns step statuses, logs references, and verification outcome.[^43][^38]

- `kargo.list_promotions`
  - **Purpose:** List Promotions for a project or stage, optionally filtered by freight, status, or time window.
  - **Backend:** Uses the promotion‑list API to return summaries.

- `kargo.approve_promotion` / `kargo.approve_freight`
  - **Purpose:** Approve a pending promotion or freight for a stage, analogous to `kargo approve` CLI and API calls.[^44][^26]
  - **Backend:** Uses the REST endpoint `/v1beta1/projects/{project}/freight/{freight}/approve`, which updates Freight status and is expected to enforce both Kubernetes RBAC and Kargo’s `promote` verb.[^27][^28]

- `kargo.abort_promotion`
  - **Purpose:** Abort a running promotion process.
  - **Backend:** Wraps the AbortPromotion API (defined by `AbortPromotionRequest`/response in the Kargo API docs), typically exposed via a REST endpoint under the `/v1beta1/projects/{project}/promotions/{promotion}` subtree.[^37][^38]

- `kargo.reverify_stage`
  - **Purpose:** Re‑run verification for the current freight in a stage, matching the `kargo verify stage` CLI behaviour.[^45][^29]
  - **Backend:** Wraps the stage‑verification API used by the CLI; the MCP server should mirror CLI behaviour rather than rely on undocumented assumptions about the exact REST path.

- `kargo.rollback_stage`
  - **Purpose:** Roll back a stage to a previous freight (where supported by Kargo’s promotion history model).
  - **Backend:** Creates a new Promotion targeting the desired freight or uses a dedicated rollback API if introduced in future Kargo versions.

### PromotionTask and Step Management Tools

- `kargo.list_promotion_tasks`
  - **Purpose:** List PromotionTask and ClusterPromotionTask resources in a project.[^35][^16]
  - **Backend:** Lists PromotionTask CRDs in the project namespace and returns summaries.

- `kargo.get_promotion_task`
  - **Purpose:** Fetch detailed PromotionTask configuration.
  - **Backend:** Retrieves the PromotionTask CRD and expands referenced steps.

- `kargo.upsert_promotion_task`
  - **Purpose:** Create or update a PromotionTask.
  - **Backend:** Applies the PromotionTask manifest.

- `kargo.validate_promotion_task`
  - **Purpose:** Validate a task’s step configuration offline (e.g., ensure step types and parameters are valid according to the Promotion Steps reference).
  - **Backend:** Uses a local catalogue of supported steps (see below) and schema validation based on the official promotion‑steps reference.[^46][^21][^7]

### RBAC and Role Tools

- `kargo.list_roles`
  - **Purpose:** List Kargo Roles in a project, including effective promotion‑related permissions.[^12]
  - **Backend:** Derives roles from ServiceAccounts, Roles, and RoleBindings created as part of the project’s boilerplate.

- `kargo.get_role`
  - **Purpose:** Fetch details for a Kargo Role (underlying ServiceAccount, Role, and RoleBindings).

- `kargo.upsert_role`
  - **Purpose:** Create or update a Kargo Role with specific permissions, e.g., promoting or approving in selected stages.[^36][^12]

- `kargo.check_permission`
  - **Purpose:** Check whether a given identity (ServiceAccount or derived caller identity) has permission for an operation (e.g., approve promotion in stage X).
  - **Backend:** Evaluates Kubernetes RBAC plus the Kargo‑specific `promote` verb against roles bound in the project namespace, aligning with the intended authorization model described in CVE‑2026‑27111.[^28][^27]

### Observability and Diagnostics Tools

- `kargo.describe_topology`
  - **Purpose:** Summarize the DAG of stages and the mapping from Warehouses to stages and promotions.[^6][^15]
  - **Backend:** Builds a graph from Stage requestedFreight specs.

- `kargo.analyze_promotion_blockers`
  - **Purpose:** Identify why a specific freight is not progressing (e.g., pending verification, failed promotion, policy constraints).
  - **Backend:** Combines Freight, Stage, and Promotion status to produce explanations.[^43][^13]

- `kargo.summarize_release`
  - **Purpose:** Summarize the status of all freight associated with a given release tag, commit, or version.
  - **Backend:** Filters Freight and Promotion resources by artifact identifiers.[^34][^2]

- `kargo.get_promotion_logs`
  - **Purpose:** Fetch logs for a failed promotion step for troubleshooting.
  - **Backend:** Uses step metadata stored in a Promotion’s status to identify the underlying Kubernetes Pod or AnalysisRun and then calls a configurable log endpoint or Kubernetes logs API to stream the relevant container logs.[^43][^29]

***

## Concrete Kargo API and MCP Mapping

### Connection and Authentication

Beginning in Kargo v1.9, the Kargo API server exposes a REST API alongside the legacy Connect/gRPC interface, and the CLI and UI use this REST API by default. The REST API currently uses a `v1beta1` version prefix for promotion‑related endpoints (for example, `/v1beta1/projects/{project}/stages/{stage}/promotions` and `/v1beta1/projects/{project}/freight/{freight}/approve`).[^37][^27][^28]

Authentication and identity mapping work as follows:

- **Admin account:** Kargo provides an optional, highly privileged admin account controlled by `api.adminAccount.*` chart values and backed by a JWT signing key; operators are strongly encouraged to disable this outside local environments.[^47][^48][^49]
- **SSO/OIDC:** For production, the recommended pattern is SSO with OpenID Connect; the API server maps OIDC claims to Kubernetes ServiceAccounts using `rbac.kargo.akuity.io/claims` annotations on ServiceAccounts in the project namespaces.[^47][^36]
- **MCP server behaviour:** In admin mode, the MCP server can either:
  - mimic the CLI’s `kargo login --admin` flow to obtain a JWT and forward it in the `Authorization: Bearer` header, or
  - run with its own ServiceAccount and rely on Kubernetes RBAC.

In SSO mode, the MCP server should treat the user’s bearer token as opaque, forwarding it unchanged so that Kargo can apply its own claims mapping and authorization checks.[^50][^36]

The REST API base URL is cluster‑specific (for example, an ingress such as `https://kargo.example.com` or an Akuity‑hosted instance URL); for local development, port‑forwarding to the Kargo API service commonly uses a localhost port such as `8080`.[^51][^52]

### MCP Resource Backends (`kargo://` URIs)

The MCP server’s resource URIs map to Kargo’s REST API as follows (assuming `v1beta1` for Kargo v1.9+):[^28][^37]

| MCP Resource URI | Description | Example REST endpoint (GET) |
|------------------|-------------|-----------------------------|
| `kargo://projects` | List of all Kargo projects visible to the caller. | `GET /v1beta1/projects` (or equivalent list RPC) |
| `kargo://projects/{project}` | Single project including promotion policies. | `GET /v1beta1/projects/{project}` |
| `kargo://projects/{project}/stages` | All stages in a project. | `GET /v1beta1/projects/{project}/stages` |
| `kargo://projects/{project}/warehouses` | All warehouses in a project. | `GET /v1beta1/projects/{project}/warehouses` |
| `kargo://projects/{project}/freight` | Freight in a project. | `GET /v1beta1/projects/{project}/freight` |
| `kargo://projects/{project}/promotions` | Promotions in a project. | `GET /v1beta1/projects/{project}/promotions` |

All resource payloads should be returned as JSON, mirroring the REST API’s responses, and the MCP server must proactively redact sensitive configuration values such as registry credentials, Git tokens, or Jira/API tokens embedded in Secrets, step configs, or environment variables before exposing them to the LLM.[^48][^21][^47]

### MCP Tools and REST API Mappings

The team’s proposed tools align well with Kargo’s API surface, with the following concrete mappings and corrections:

**Promotion execution tools**

- `promote_to_stage(project, stage, freight)`
  - Maps to `POST /v1beta1/projects/{project}/stages/{stage}/promotions` with a body containing the freight identifier and optional parameters.[^27][^28]
  - Internally creates a Promotion resource and kicks off the promotion steps for the given stage.

- `approve_freight(project, name, stage)`
  - Maps to `POST /v1beta1/projects/{project}/freight/{name}/approve`.[^28]
  - Approves freight for promotion to the given stage; the endpoint is expected to enforce both Kubernetes RBAC and Kargo’s `promote` verb for the target stage.[^36][^27]

- `abort_promotion(project, promotion_name)`
  - Wraps the AbortPromotion API described by `AbortPromotionRequest` in the API docs and typically maps to a REST endpoint under `/v1beta1/projects/{project}/promotions/{promotion}` (exact path may vary slightly by Kargo version).[^38][^37]

- `reverify_stage(project, stage)`
  - Matches the CLI’s `kargo verify stage --project <project> <stage>` command.[^45]
  - The MCP server should call the same API used by the CLI rather than assuming an endpoint name; this API re‑runs verification for the current freight in the stage.[^29]

**Lifecycle and discovery tools**

- `refresh_warehouse(project, name)`
  - Maps to `POST /v1beta1/projects/{project}/warehouses/{name}/refresh`, which enqueues the Warehouse for immediate reconciliation and artifact discovery.[^53][^42]

- `create_project(name)` and `update_resource(manifest)`
  - Rather than assuming a generic `/v1alpha1/resources` endpoint, the recommended implementation is:
    - Use Kargo’s own "apply" API if present (the same one used by `kargo apply`), or
    - Apply manifests directly to the Kubernetes API for `Project`, `Stage`, `Warehouse`, `PromotionTask`, etc.[^41][^26]
  - This keeps the MCP server aligned with Kargo’s supported APIs and avoids relying on unverified REST paths.

**Troubleshooting tool**

- `get_promotion_logs(project, promotion_name)`
  - Reads the Promotion’s status and step metadata to determine the failing step and associated Kubernetes Pod or Argo Rollouts/AnalysisRun.[^43][^29]
  - Uses a configurable log backend (for example, Kubernetes `pods/log`, Loki, or an internal log proxy) to stream logs for that container back to the client.

### Built‑in Promotion Steps Catalogue

To help the LLM assemble valid PromotionTasks, the MCP server should expose a "catalogue of steps" resource summarizing at least the following step families:[^22][^21][^23][^46][^24][^7]

- **Git:** `git-clone`, `git-commit`, `git-push`, `git-open-pr`, `git-wait-for-pr`, plus related utility steps.
- **Manifests:** `yaml-update`, `yaml-merge`, `json-update`, `helm-template`, `kustomize-build`.
- **Cloud/infra:** `tf-plan`, `tf-apply`, `tf-output` (Akuity platform), `hcl-update`, archive utilities such as `untar`.
- **CI/CD integrations:** `gha-dispatch-workflow`, `gha-wait-for-workflow` for GitHub Actions.[^22]
- **Project/ITSM integrations:** `jira` and ServiceNow steps (Akuity platform), which create/update issues or track change requests.[^54][^23]
- **Custom steps:** `custom-steps` / `CustomPromotionStep` for arbitrary containers running user‑defined commands.[^55]

The catalogue can be exposed either as a dedicated MCP resource (for example, `kargo://promotion-steps`) or as a static prompt template that tools reference for validation.

### Handling Implementation Gaps and Guardrails

Several additional behaviours from the team’s design align with Kargo’s documented capabilities and best practices:

- **Non‑Kubernetes infrastructure state:** For Terraform/OpenTofu‑driven promotions, the MCP server should not query cloud providers directly; instead, it should rely on the `tf-output` step’s outputs and Promotion status fields (for example, `status.state`, `status.message`) to determine whether infrastructure applies were successful.[^25][^24]

- **Multi‑origin DAG guardrails:** Before applying Stage changes via `update_resource`, the MCP server can perform client‑side validation of `spec.requestedFreight` to prevent cycles such as a Stage listing itself as a source or forming circular upstream/downstream references. This complements Kargo’s own assumptions that Stage graphs form DAGs.[^15][^6]

- **Approval workflow details:** Because Kargo uses a dedicated `promote` verb to gate promotion‑triggering operations, the MCP server must forward caller tokens unchanged (`Authorization: Bearer <token>`) when calling approval and promotion endpoints, allowing Kargo to enforce both standard Kubernetes RBAC and the `promote` verb.[^27][^36][^28]

- **Real‑time streaming:** While MCP is fundamentally request‑response, it supports notifications, and Kargo provides watch streams such as `WatchFreight`, `WatchStages`, `WatchPromotion`, and `WatchWarehouses` on its service API. The MCP server can subscribe to these gRPC or long‑polling streams and emit MCP notifications whenever a Promotion transitions to `Succeeded` or `Failed`, or when new Freight becomes available.[^56][^43]

***

## Internal Architecture of the Kargo MCP Server

### Integration with Kubernetes and Kargo APIs

The MCP server should integrate with Kargo primarily through the Kubernetes API for Kargo CRDs (`Project`, `ProjectConfig`, `Stage`, `Warehouse`, `Freight`, `Promotion`, `PromotionTask`, etc.), plus Kargo’s REST/gRPC APIs for promotion‑specific operations such as approval, promotion creation, refresh, and verification.[^57][^38][^26]

- A dedicated Kubernetes client layer handles CRUD operations on CRDs and watches for updates where resource streams are supported.
- A Kargo API client layer encapsulates REST and/or gRPC calls to endpoints such as `/v1beta1/projects/{project}/stages/{stage}/promotions`, `/freight/{freight}/approve`, `/warehouses/{warehouse}/refresh`, and the various watch methods.[^53][^43][^28]
- When necessary, the server can reuse Kargo’s CLI in a controlled environment (for example, invoking `kargo promote`, `kargo approve`, or `kargo verify`) to match behaviour exactly, especially where REST paths are not yet formally documented.

### MCP Layer and Capability Registration

Following MCP server development guidelines and reference implementations, the architecture should include:[^31][^32]

- A core `McpServer` instance initialized with server metadata and capabilities.
- Separate modules for tools and resources:
  - `tools/projects`, `tools/stages`, `tools/promotions`, `tools/tasks`, `tools/rbac`, etc.
  - `resources/project`, `resources/stage`, `resources/freight`, `resources/promotion`, `resources/warehouse`, `resources/steps`.
- Schema definitions for inputs/outputs using a validation library (e.g., Zod) to match MCP tool/resource schema expectations.
- HTTP (or other) transport that exposes a single MCP endpoint, handling JSON‑RPC, sessions, and streaming according to the MCP spec.

This modular approach aligns with best practices for MCP servers and simplifies future extensions.[^32][^10]

### Security, RBAC, and Multi‑Tenancy

The Kargo MCP server must respect Kargo and Kubernetes RBAC:

- Each request should map to a Kubernetes identity (ServiceAccount or user) whose permissions are enforced by the Kubernetes API when interacting with Kargo CRDs.[^5][^12]
- Tools that change promotion state or configuration must perform explicit permission checks using Role and RoleBinding information, and should call approval and promotion endpoints in a way that preserves and respects the `promote` verb boundary.[^27][^28]
- Multi‑tenant environments use Project‑scoped namespaces and Kargo Roles to isolate tenants; the MCP server should ensure that resource URIs and tools do not leak data across projects.

### Observability and Auditing

To support enterprise use, the server should integrate with existing logs and metrics:

- Promotion and approval actions should be logged with identity and request metadata for auditing and compliance.
- Metrics about tool usage, promotion success/failure rates, and latency can be exposed to monitoring systems.
- When combined with Akuity’s enterprise platform, Kargo’s promotion audit trails can be surfaced via the MCP server for AI‑driven analysis.[^17][^30]

***

## Conclusion

Kargo provides a rich, GitOps‑native model for continuous promotion across application and infrastructure environments, built on Projects, Warehouses, Freight, Stages, Promotions, and reusable PromotionTasks. The Model Context Protocol offers a natural fit for exposing these concepts to AI agents, using resources for state and tools for actions, all while respecting Kargo’s policies and RBAC.[^1][^7][^6]

The design in this report defines a comprehensive resource model, extensive tool surface, concrete REST/gRPC mappings, and opinionated workflows that together allow an MCP server to cover "everything the platform is giving" around promotions, from pipeline design and automation to approvals, troubleshooting, and cross‑stack orchestration. Implemented with standard MCP server patterns and careful Kubernetes integration, this Kargo MCP server can become a powerful foundation for multi‑agent DevOps and platform engineering workflows.[^30][^37][^20][^28][^13]

---

## References

1. [Kargo the New Promotion Orchestrator for Argo CD - Alexander Extim](https://www.extim.su/blog/kargo-the-new-promotion-orchestrator-for-argo-cd-%F0%9F%94%A5/) - A continuous promotion orchestrator that complements Argo CD for Kubernetes. Built and maintained by...

2. [Working with Warehouses - Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-warehouses/) - When a Warehouse observes a new revision of any artifact to which it subscribes, it creates a new Fr...

3. [Multi-Environment Promotion Is the Missing GitOps Piece ... - YouTube](https://www.youtube.com/watch?v=--Wz2-PZI-g) - ... Argo CD at Intuit to launching Kargo, the multi-environment promotion engine that's now seeing m...

4. [Kargo](https://kargo.io) - Kargo is a continuous promotion orchestration layer, that complements Argo CD for Kubernetes. Built ...

5. [Working with Projects | Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-projects) - Each Kargo project is represented by a cluster-scoped Kubernetes resource of type Project. Reconcili...

6. [Key Kargo Concepts](https://release-1-1.docs.kargo.io/concepts/) - A promotion is a request to move a piece of freight into a specified stage. Corresponding Resource T...

7. [Promotion Steps Reference | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/) - Below is an overview of the available promotion steps that can be used in

8. [Resources - Model Context Protocol （MCP）](https://modelcontextprotocol.info/docs/concepts/resources/) - Expose data and content from your servers to LLMs

9. [Resources - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)

10. [Tools - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

11. [What's New in Kargo v0.4.0 - Akuity Blog](https://akuity.io/blog/whats-new-kargo-0-4-0) - Deploy with Argo CD, promote seamlessly with Kargo, and gain real-time visibility into your infrastr...

12. [What's New in Kargo v0.6.0 - Akuity](https://akuity.io/blog/whats-new-kargo-0-6-0) - A Kargo Role exists as long as an underlying ServiceAccount resource with the same name exists in th...

13. [Introduction to Kargo: GitOps Promotion Pipelines for Kubernetes](https://burrell.tech/blog/kargo/) - It does not require you to change how Argo CD deploys applications. It simply adds the orchestration...

14. [Feature request: per-warehouse auto-promotion control on stages ...](https://github.com/akuity/kargo/issues/5952) - Allow promotionPolicies in ProjectConfig to scope auto-promotion to specific warehouse origins, rath...

15. [Working with Stages | Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-stages) - When a Stage accepts Freight directly from its origin, all new Freight created by that origin (e.g. ...

16. [kargo-pipeline-helm/docs/PROMOTIONS.md at main - GitHub](https://github.com/pww217/kargo-pipeline-helm/blob/main/docs/PROMOTIONS.md) - A promotionTemplate is part of the Stage spec (not a separate CRD). It defines what steps run when F...

17. [Akuity: The Enterprise Software Delivery Platform, Powered by AI](https://akuity.io) - Built by the creators of Argo CD and Kargo, Akuity provides enterprise-ready delivery, continuous pr...

18. [Working With Freight | Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-freight) - Freight is an important Kargo concept. A single "piece of freight" is a set of references to one or ...

19. [Implementing a Modular Kargo Promotion Workflow](https://dev.to/josephcc/implementing-a-modular-kargo-promotion-workflow-extracting-promotiontask-from-stage-for-4npi) - A fully operational GitOps-native upgrade pipeline, designed for reuse and scalability This is Part....

20. [Configuring Kargo](https://www.pulumi.com/blog/pulumi-kubernetes-operator-and-kargo/) - Use Kargo with the Pulumi Kubernetes Operator to control how infrastructure changes are promoted acr...

21. [yaml-update](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/yaml-update/) - Updates the values of specified keys in any YAML file.

22. [gha-dispatch-workflow | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/gha-dispatch-workflow) - tf-apply · tf-output · tf-plan · toml-parse · toml-update · untar · yaml-merge ... This promotion st...

23. [jira | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/jira/) - Integrates with Jira to manage issues, comments, and track promotion workflows.

24. [tf-apply | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/tf-apply) - Promotion Steps; tf-apply. On this page. tf-apply. info. This promotion step is only available in Ka...

25. [tf-output | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/tf-output) - This promotion step is only available in Kargo on the Akuity Platform, versions v1.9 and above. Addi...

26. [Lab K704 - Kargo - Kubernetes Tutorial with CKA/CKAD Prep](https://kubernetes-tutorial.schoolofdevops.com/argo_kargo/)

27. [CVE-2026-27111: Kargo has Missing Authorization Vulnerabilities ...](https://advisories.gitlab.com/pkg/golang/github.com/akuity/kargo/CVE-2026-27111/) - Kargo's authorization model includes a promote verb – a non-standard Kubernetes "dolphin verb" – tha...

28. [CVE-2026-27111 | Tenable®](https://www.tenable.com/cve/CVE-2026-27111) - Kargo manages and automates the promotion of software artifacts. From v1.9.0 to v1.9.2, Kargo's auth...

29. [Verifying Freight in a Stage - Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/verification/) - Learn how to verify a Stage after Promotion

30. [What is Kargo? Simplifying Continuous Promotion with GitOps - Akuity](https://akuity.io/what-is-kargo) - With Kargo, teams can automate and secure application promotions using GitOps workflows - without ma...

31. [GitHub - modelcontextprotocol/servers: Model Context Protocol Servers](https://github.com/modelcontextprotocol/servers) - Model Context Protocol Servers. Contribute to modelcontextprotocol/servers development by creating a...

32. [Model Context Protocol (MCP) Server Development Guide … - GitHub](https://github.com/cyanheads/model-context-protocol-resources/blob/main/guides/mcp-server-development-guide.md) - Exploring the Model Context Protocol (MCP) through practical guides, clients, and servers I've built...

33. [Deep Dive into Kargo Configuration: Best Practices and YAML ...](https://freedium.cfd/b8afce83811a) - This is our Kargo GitOps series' third chapter with a focus on the best practices of Kargo...

34. [How to Automate CI/CD Pipelines with Kargo (Live Demo) - YouTube](https://www.youtube.com/watch?v=2O1eQntjR-U) - Key Kargo concepts: Freight, Warehouses, Stages, and Subscriptions ... Live demo: End-to-end deploym...

35. [akuity/kargo v1.2.0 on GitHub](https://newreleases.io/project/github/akuity/kargo/release/v1.2.0) - New release akuity/kargo version v1.2.0 on GitHub.

36. [Access Controls - Kargo Docs](https://docs.kargo.io/user-guide/security/access-controls/) - Most access controls in Kargo are within the purview of highly-privileged

37. [What's New in Kargo v1.9: API Tokens, Warehouse Performance ...](https://burrell.tech/blog/kargo-v1-9/) - Kargo v1.9 adds a REST API, JWT tokens for automation, and Warehouse caching that cuts artifact disc...

38. [API Documentation - Kargo Docs](https://main.docs.kargo.io/api-documentation/) - Top

39. [Working with Projects | Kargo Docs](https://docs.kargo.io/how-to-guides/working-with-projects/) - Learn how to work effectively with Projects

40. [What's New in Kargo v0.4.0](https://akuity.io/blog/whats-new-kargo-0.4.0/) - In this post, we will go over the exciting new features and updates of Kargo v0.4.0

41. [Working with Projects | Kargo Docs](https://release-1-0.docs.kargo.io/how-to-guides/working-with-projects/) - Learn how to work effectively with Projects

42. [GitLab Webhook Receiver - Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/webhook-receivers/gitlab/) - "Refreshing" a Warehouse resource means enqueuing it for immediate reconciliation by the Kargo contr...

43. [After Update to 1.5.2, Kargo Promotions all Pending Indefinitely #4383](https://github.com/akuity/kargo/issues/4383) - Kargo Stage Promotions sit idle. In Pending state. This might be related to our earlier issue where ...

44. [gRPC API Documentation (Deprecated) - Kargo Docs](https://docs.kargo.io/api-documentation/) - Top

45. [UI: ability to rerun the verification of a Stage's current Freight · Issue #1792 · akuity/kargo](https://github.com/akuity/kargo/issues/1792) - Proposed Feature We should make it possible to rerun the verification of a Stage's current Freight f...

46. [Promotion Steps Reference | Kargo Docs](https://release-1-0.docs.kargo.io/references/promotion-steps/) - Learn about all of Kargo's built-in promotion steps

47. [Secure Configuration | Kargo Docs](https://docs.kargo.io/operator-guide/security/secure-configuration/) - The purpose of this document is to direct operators' attention to specific

48. [kargo/charts/kargo/README.md at main · akuity/kargo](https://github.com/akuity/kargo/blob/main/charts/kargo/README.md) - Application lifecycle orchestration. Contribute to akuity/kargo development by creating an account o...

49. [Kargo Quickstart - Akuity Docs](https://docs.akuity.io/tutorials/kargo-quickstart/) - This quickstart will walk you through implementing Kargo with Akuity Platform, to manage the promoti...

50. [Accessing Kargo | Akuity Docs](https://docs.akuity.io/kargo/getting-started/access-kargo-instance/) - How to access the Kargo instance in the Akuity Platform

51. [Logging In](https://docs.kargo.io/user-guide/how-to-guides/logging-in/) - Learn how to log in to Kargo

52. [Kargo by Akuity CD of the Future - RodrigTech](https://rodrigtech.com/kargo-by-akuity-cd-of-the-future/) - Introduction Kargo is a new tool presented by Akuity that aims at treating your releases as stages r...

53. [Unable to properly authenticate with `--kubeconfig` · akuity kargo ...](https://github.com/akuity/kargo/discussions/5722) - $ kargo refresh warehouse --project <project> <warehouse> Error: refresh Warehouse: [POST /v1beta1/p...

54. [snow-wait-for-condition | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/snow-wait-for-condition/) - Kargo Documentation. Kargo DocsAkuity.io Kargo ... This promotion step is only available in Kargo on...

55. [custom-steps | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/custom-steps/) - Execute command in user-provided image

56. [gRPC API Documentation (Deprecated) | Kargo Docs](https://docs.kargo.io/api-documentation) - project, string, project is the name of the project whose promotions should be watched. stage, strin...

57. [akuity/kargo: Application lifecycle orchestration - GitHub](https://github.com/akuity/kargo) - If you are interested in enterprise-scale Kargo hosted, managed, and professionally supported by Aku...

