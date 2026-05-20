# Designing a Comprehensive Kargo MCP Server for Continuous Promotion

## Executive Summary

Kargo is a continuous promotion orchestration layer created by the Argo team to complement Argo CD by automating multi‑stage promotions using GitOps principles. It introduces core concepts such as Projects, Warehouses, Freight, Stages, and Promotions, each backed by Kubernetes custom resources, to model and control how changes flow across environments or other promotion targets.[^1][^2][^3][^4][^5][^6]

This report proposes a detailed design for a Model Context Protocol (MCP) server that fully exposes Kargo’s promotion capabilities to language‑model clients. The design defines a rich resource model, an extensive tool surface, and opinionated workflows that cover application and infrastructure promotion, policy management, approval flows, troubleshooting, and integration with Argo CD and other downstream systems. The goal is to make promotions discoverable, explainable, and automatable through natural‑language interaction while mapping cleanly to Kargo’s underlying CRDs and RBAC model.[^7][^8][^9][^10][^11][^12]

***

## Kargo Core Concepts and Resource Types

### Project

A Kargo project is the main unit of organization and tenancy, grouping all related Kargo resources that describe one or more delivery pipelines. Each project is represented by a cluster‑scoped `Project` Kubernetes resource; reconciling this resource creates a dedicated, specially labeled namespace and required boilerplate objects such as ServiceAccounts and RBAC bindings. Deleting the `Project` deletes (or can be triggered by deleting) the corresponding namespace, ensuring lifecycle coupling between the logical project and its Kubernetes resources.[^5][^10][^6]

Projects also embed promotion policies that control whether stages are eligible for automatic promotion of new freight or require manual intervention. These `PromotionPolicy` settings can be extended to support finer‑grained options such as per‑origin auto‑promotion and selection strategies.[^13][^10][^14]

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

A promotion in Kargo is a request to move a specific piece of freight into a specified stage. At design time, users define promotion behavior via Stage `promotionTemplate` fields and reusable `PromotionTask` (and `ClusterPromotionTask`) resources, which are referenced by Stages for modular, DRY promotion logic. At runtime, Kargo creates `Promotion` resources, inflates tasks into step execution graphs, and runs them using built‑in step types for Git, Helm, Argo CD, CI integration, and notifications.[^19][^12][^16][^6]

The Promotion Steps reference includes a catalog of step types such as `git-clone`, `git-commit`, `git-push`, `git-open-pr`, `helm-template`, `helm-update-chart`, `argocd-update`, `argocd-wait`, `gha-dispatch-workflow`, `gha-wait-for-workflow`, `hcl-update`, `github-push`, and many others, allowing promotions to drive Kubernetes, Helm, Terraform/OpenTofu, GitHub Actions, and Argo CD workflows.[^3][^20][^12]

### RBAC and Kargo Roles

Kargo exposes RBAC primarily through the Project and Project namespace, relying on Kubernetes ServiceAccounts, Roles, and RoleBindings. Higher‑level "Kargo Roles" serve as abstractions over these components, with the Kargo CLI providing `create`, `grant`, `revoke`, and `delete` operations that manage the underlying ServiceAccount, Role, and RoleBinding triplet.[^11][^5]

Promotion‑specific permissions such as `promote` or approval rights can be scoped to specific stages or projects, enabling fine‑grained control over who can approve or trigger promotions in multi‑tenant systems.[^20][^11]

***

## Kargo Promotion Lifecycle and Usage Patterns

### End‑to‑End Promotion Flow

A typical Kargo promotion flow for an application or infrastructure change is as follows:[^1][^13]

1. A Warehouse detects a new artifact revision (e.g., new container image, Git commit, or Helm chart tag) and creates a corresponding Freight resource.
2. Freight becomes available to the first Stage that directly accepts freight from the Warehouse, subject to any requestedFreight and upstream conditions.
3. Depending on the Stage’s auto‑promotion policy, the freight is either auto‑promoted or waits for an explicit Promotion request and approval.
4. Promotion execution runs the Stage’s referenced PromotionTask or inline promotionTemplate, performing steps such as Git updates, Helm rendering, Argo CD application updates, and CI/test invocations.
5. Optional verification runs after promotion, which may include health checks, Argo Rollouts analysis, integration tests, or other validation; only verified freight is considered eligible for downstream stages.
6. Once verified, freight is exposed as available to downstream stages according to requestedFreight relationships and availability strategies, allowing subsequent promotions to propagate the same freight through staging, UAT, production, or infrastructure tiers.

This workflow applies equally to application deployments and to infrastructure changes driven via tools such as the Pulumi Kubernetes Operator, Terraform/OpenTofu, or Argo CD ApplicationSets.[^12][^3][^20]

### Auto‑Promotion vs Manual Promotion

Kargo supports both automated and manual promotion semantics aligned with promotion policies configured at the Project or Stage level.[^10][^13]

- Auto‑promotion policies like `NewestFreight` continuously promote the newest verified freight as soon as it becomes available, ideal for fast‑moving lower environments such as dev or test.
- Policies such as `MatchUpstream` promote whichever freight is currently active in the upstream Stage, allowing downstream stages to mirror another stage’s state instead of racing ahead.
- Project promotion policies and feature requests such as per‑Warehouse auto‑promotion control enable more granular behaviour, for example auto‑promoting from a dev‑tags Warehouse but requiring manual promotion for semver release tags.[^14][^13]

Manual approvals can be performed through the Kargo UI or CLI, where an approver explicitly approves promotion of a specific freight for a stage before promotion can proceed.[^18][^20]

### Multi‑Origin and Multi‑Pipeline Scenarios

Stages can request freight from one or more origins, including Warehouses and upstream stages, enabling the definition of multiple logical pipelines converging on shared stages. A Stage can thus participate in multiple pipelines that each deliver different collections of artifacts independently, although this is considered advanced configuration that should be used carefully.[^15]

Availability strategies in requestedFreight (e.g., requiring freight to be verified in multiple upstream stages) allow modeling complex release gates, such as requiring combined verification in both QA and UAT before a production stage accepts freight.[^13][^15]

### Infrastructure Promotion Use Cases

Kargo’s promotion concepts apply not only to Kubernetes applications but also to infrastructure deliveries using tools such as Terraform, Pulumi, or other GitOps‑managed stacks.[^21][^3][^20]

- Using the Pulumi Kubernetes Operator, each Stage can map to a Pulumi Stack that manages infrastructure for that environment, with promotions updating the Stack configuration to reference new freight or state.[^20]
- Promotion steps like `hcl-update` and Git operations enable OpenTofu/Terraform configuration updates to be modeled as freight promotions, with Kargo orchestrating the path across environments.[^3][^12]
- When combined with policy‑driven promotion, this allows infrastructure and applications to share promotion workflows, guardrails, and approvals while still being managed by distinct controllers or operators.[^21][^17]

***

## MCP Concepts Relevant to a Kargo Server

### MCP Resources

In the Model Context Protocol, resources represent data exposed by servers to clients, such as file contents, database records, API responses, or live system data, each identified by a unique URI. Resources can be listed, fetched, and sometimes watched, and they may contain either text or binary content, with metadata describing properties such as MIME type and description.[^8][^7]

For a Kargo MCP server, resources are the natural way to expose the state of Projects, Stages, Warehouses, Freight, Promotions, and PromotionTasks to the language model, providing structured context that can be combined with tool invocations.[^7][^6]

### MCP Tools

Tools in MCP are named operations that a server exposes for invocation by the language model, typically for actions such as querying databases, calling external APIs, or manipulating application state. Each tool is described with a schema for its input parameters and output shape, and tools are designed to be model‑controlled, meaning that the language model can discover and invoke them based on task context.[^9]

For Kargo, tools are used for imperative operations such as creating Projects, defining Stages, triggering Promotions, performing approvals, editing PromotionTasks, and inspecting recent events or logs.[^16][^18]

### MCP Server Implementation Practices

Reference MCP servers and development guides recommend a modular design where each capability (tools, resources, prompts) is defined with clear schemas and handlers, often using libraries such as Zod for validation and SDK helper classes for HTTP transport and JSON‑RPC handling.[^22][^23]

The recommended pattern is to create a central `McpServer` instance with metadata (name, version), then register tools and resources via registration functions that encapsulate logic, schemas, and annotations. HTTP or other transport integrations (e.g., Express‑based endpoints) delegate JSON‑RPC parsing, session management, and streaming to SDK transport helpers, simplifying implementation complexity.[^23][^22]

***

## High‑Level Goals for the Kargo MCP Server

The Kargo MCP server should provide a complete but safe interface to all Kargo promotion‑related capabilities, optimized for use by LLM‑driven agents and human operators collaborating through natural‑language interfaces.[^3][^21]

Key goals include:

- **Full promotion coverage:** Expose all relevant Kargo concepts—Projects, Stages, Warehouses, Freight, Promotions, PromotionTasks, PromotionPolicies, and RBAC roles—through MCP resources and tools.
- **GitOps‑aligned behaviour:** Ensure all operations respect GitOps principles, favoring declarative configuration changes over direct imperative modifications of running workloads, consistent with how Kargo treats configuration as code.[^4][^21]
- **Explainability:** Provide rich descriptions, promotion histories, verification results, and dependency graphs as resources so the model can explain promotion state and decisions.
- **Safety and guardrails:** Enforce Kargo’s promotion policies and RBAC, surface dry‑run and plan capabilities, and limit destructive operations through explicit tools and role checks.[^10][^11]
- **Multi‑surface support:** Work equally well for application and infrastructure pipelines, including Argo CD, Helm, Terraform/OpenTofu, and Pulumi‑driven flows.[^12][^20][^3]

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
- Core spec: promotion policies (including auto‑promotion enabled/disabled, default selection policies, per‑stage overrides), project RBAC configuration, and any project‑level defaults for Warehouses and Stages.[^14][^10]
- Derived fields: list of stages in the project, DAG topology (edges, roots, leaves), list of Warehouses, and summary of promotion flows.

This resource enables the model to understand the overall delivery topology and policy landscape for a project.[^6][^13]

### Stage Resource Schema

A Stage resource should include:

- Metadata: `name`, namespace, labels/annotations.
- Spec breakdown:
  - `variables` block, including templating variables for promotion tasks.
  - `requestedFreight` entries, including origin kind/name, sources (direct or upstream stages), availability strategy (e.g., All, Any), and any per‑origin auto‑promotion options.[^15][^14]
  - `promotionTemplate` reference or inline template, and associated PromotionTask references.[^16][^15]
  - `verification` configuration (e.g., Argo Rollouts analysis templates, test hooks, health checks).
- Status:
  - Current active freight, last promotion ID, last promotion status and timestamp.
  - Verification status for the current freight.
  - Condition summaries (e.g., healthy, degraded).

Derived fields should capture upstream/downstream stages and whether the stage participates in multiple pipelines or receives freight from multiple Warehouses.[^13][^15]

### Warehouse Resource Schema

A Warehouse resource should expose:

- Subscribed sources: container image repositories, Git repositories, Helm chart repositories, and any strategies (e.g., NewestBuild, SemVer) for selecting revisions.[^19][^2]
- Current and recent freight IDs created by the Warehouse, with artifact version summaries and timestamps.[^2]
- Status: last sync time, error conditions, and backoff behaviour if artifact discovery fails.

This information allows the MCP server to answer questions about where freight came from and why certain versions are present or missing.[^13][^2]

### Freight Resource Schema

Freight resources should include:

- Artifact references: list of container images (repo, tag, digest), Git commits (repo, branch, commit hash), Helm charts (repository, chart name, version), and other artifacts represented by the Freight.[^6][^2]
- Provenance: originating Warehouse, discovered time, triggering event/metadata (e.g., CI pipeline run, Git tag push).[^24][^2]
- Stage state: for each Stage in the project, fields indicating whether the freight is available, promoted, verified, or rolled back.[^18][^13]

This provides a project‑wide view of how a given change is progressing through the promotion graph.

### Promotion and PromotionTask Resource Schemas

Promotion resources represent individual promotion runs and should include:

- Target project and Stage.
- Freight ID.
- Trigger type (auto vs manual), initiator identity, and any approval metadata.[^18][^13]
- Step graph: list of steps executed (with types such as `git-clone`, `argocd-update`, `hcl-update`), their statuses, durations, and logs URLs or summaries.[^12][^16]
- Verification outcome and any analysis results.

PromotionTask resources should include:

- Reusable step sequences, parameter schemas, and default values, including which steps interact with Argo CD, GitHub, Terraform/OpenTofu, or other systems.[^16][^12]
- A list of Stages referencing the task, which the MCP server can derive by cross‑referencing Stage specs.[^19]

### Role and RBAC Resource Schemas

RBAC abstractions should be modeled as Role resources that include:

- Underlying ServiceAccount name, Role rules, and RoleBindings affected by the Kargo Role.[^11]
- Effective permissions, particularly those related to promotion operations such as `promote`, `approve`, `rollback`, and configuration changes to Stages or PromotionTasks.[^20][^11]

These resources enable the MCP server to reason about whether a given operation should be exposed or blocked for a specific caller context.

***

## Tool Surface for the Kargo MCP Server

### Design Principles for Tools

The tool set should satisfy the following principles:

- **Idempotent where possible:** Declarative operations (e.g., upserting Projects, Stages, PromotionTasks) should be idempotent and safe to re‑invoke.
- **Separation of plan vs apply:** Tools that mutate promotion state (create Promotions, approve, rollback) should support dry‑run / plan modes where feasible, producing human‑readable plans.
- **Alignment with Kargo CRDs:** Tools should map closely to underlying Kargo APIs and CRDs, making it easy to reason about how they affect the system.[^5][^6]
- **Explicit side‑effects:** Tools that touch Argo CD, Git, or infrastructure controllers should clearly document their integration points and side‑effects.[^20][^12]

### Project‑Level Tools

- `kargo.list_projects`
  - **Purpose:** List all Kargo Projects, optionally filtered by label or name pattern.
  - **Inputs:** Optional filter criteria.
  - **Outputs:** Array of Project summaries (name, namespace, promotionPolicy summary, stage count).
  - **Behaviour:** Reads `Project` CRDs from the cluster, aggregates basic metadata.

- `kargo.get_project`
  - **Purpose:** Fetch a detailed Project resource, including DAG of stages and policies.
  - **Inputs:** `projectName`.
  - **Outputs:** Full Project resource schema described above.

- `kargo.upsert_project`
  - **Purpose:** Create or update a Project with specified promotion policies and basic settings.
  - **Inputs:** Project spec fields including promotionPolicy, labels, and annotations.[^10][^14]
  - **Outputs:** Updated Project resource.
  - **Behaviour:** Applies a declarative manifest via Kubernetes API or Kargo CLI; may support `dryRun` to produce a patch preview.

- `kargo.delete_project`
  - **Purpose:** Delete a Project and associated namespace, subject to a confirmation flag.
  - **Inputs:** `projectName`, `force` boolean.
  - **Outputs:** Operation result and any blocking conditions.

### Stage‑Focused Tools

- `kargo.list_stages`
  - **Purpose:** List all stages in a project, with promotion topology metadata.
  - **Inputs:** `projectName`.
  - **Outputs:** Array of Stage summaries (name, upstream/downstream info, auto‑promotion status, current freight ID).[^15][^6]

- `kargo.get_stage`
  - **Purpose:** Fetch a detailed Stage resource.
  - **Inputs:** `projectName`, `stageName`.
  - **Outputs:** Full Stage schema.

- `kargo.upsert_stage`
  - **Purpose:** Create or update a Stage, including requestedFreight, promotionTemplate/PromotionTask references, and verification settings.[^15][^16]
  - **Inputs:** Stage spec fields.
  - **Outputs:** Updated Stage resource.

- `kargo.plan_stage_changes`
  - **Purpose:** Compute a plan summarizing how proposed Stage spec changes would affect promotion topology, auto‑promotion behavior, and freight availability.
  - **Inputs:** `projectName`, `stageName` (optional for new stage), desired spec.
  - **Outputs:** Plan summarizing added/removed upstream/downstream relationships, changed policies, and potential risks.

### Warehouse and Freight Tools

- `kargo.list_warehouses`
  - **Purpose:** List Warehouses for a project and their subscribed sources.[^2]
  - **Inputs:** `projectName`.
  - **Outputs:** Array of Warehouse summaries.

- `kargo.get_warehouse`
  - **Purpose:** Fetch a detailed Warehouse resource.
  - **Inputs:** `projectName`, `warehouseName`.
  - **Outputs:** Full Warehouse schema.

- `kargo.list_freight`
  - **Purpose:** List freight in a project or for a given Warehouse or Stage.
  - **Inputs:** `projectName`, and filters such as `warehouseName`, `stageName`, `status` (available, promoted, verified).
  - **Outputs:** Freight summaries including artifact versions and stage states.[^13][^2]

- `kargo.get_freight`
  - **Purpose:** Fetch a detailed Freight resource.
  - **Inputs:** `projectName`, `freightID`.
  - **Outputs:** Full Freight schema.

### Promotion and Approval Tools

- `kargo.plan_promotion`
  - **Purpose:** Generate a promotion plan for moving a given freight into a stage, explaining steps and verification.
  - **Inputs:** `projectName`, `stageName`, `freightID`.
  - **Outputs:** A structured plan describing the PromotionTask steps, expected Git/Argo CD/infra changes, and verification checks.[^12][^16]

- `kargo.create_promotion`
  - **Purpose:** Create a Promotion resource to move freight into a stage, respecting auto‑promotion policies and RBAC.
  - **Inputs:** `projectName`, `stageName`, `freightID`, flags such as `dryRun`, `force` (where allowed).
  - **Outputs:** Promotion resource with initial status.

- `kargo.get_promotion`
  - **Purpose:** Fetch detailed status of a specific Promotion.
  - **Inputs:** `projectName`, `promotionID`.
  - **Outputs:** Promotion schema including step statuses, logs references, and verification outcome.[^16][^12]

- `kargo.list_promotions`
  - **Purpose:** List Promotions for a project or stage, optionally filtered by freight, status, or time window.
  - **Inputs:** `projectName`, filters.
  - **Outputs:** Promotion summaries.

- `kargo.approve_promotion`
  - **Purpose:** Approve a pending promotion for a stage, analogous to manual approval commands or UI actions.[^18][^20]
  - **Inputs:** `projectName`, `freightID`, `stageName`, optional `comment`.
  - **Outputs:** Updated Promotion or Freight state.

- `kargo.rollback_stage`
  - **Purpose:** Roll back a stage to a previous freight (where supported by Kargo’s promotion history model).
  - **Inputs:** `projectName`, `stageName`, target `freightID` or `rollbackStrategy` (e.g., previous verified freight).
  - **Outputs:** New Promotion or rollback record.

### PromotionTask and Step Management Tools

- `kargo.list_promotion_tasks`
  - **Purpose:** List PromotionTask and ClusterPromotionTask resources in a project.
  - **Inputs:** `projectName`.
  - **Outputs:** Task summaries with referenced steps and usage counts.[^19][^16]

- `kargo.get_promotion_task`
  - **Purpose:** Fetch detailed PromotionTask configuration.
  - **Inputs:** `projectName`, `taskName`.
  - **Outputs:** Task schema including reusable step sequences.

- `kargo.upsert_promotion_task`
  - **Purpose:** Create or update a PromotionTask.
  - **Inputs:** Task spec fields.
  - **Outputs:** Updated PromotionTask resource.

- `kargo.validate_promotion_task`
  - **Purpose:** Validate a task’s step configuration offline (e.g., ensure step types and parameters are valid according to the Promotion Steps reference).
  - **Inputs:** Proposed task spec.
  - **Outputs:** Validation report referencing supported step types such as `git-*`, `argocd-*`, `helm-*`, `gha-*`, `hcl-update`, etc.[^12]

### RBAC and Role Tools

- `kargo.list_roles`
  - **Purpose:** List Kargo Roles in a project, including effective promotion‑related permissions.[^11]
  - **Inputs:** `projectName`.
  - **Outputs:** Role summaries.

- `kargo.get_role`
  - **Purpose:** Fetch details for a Kargo Role (underlying ServiceAccount, Role, and RoleBindings).
  - **Inputs:** `projectName`, `roleName`.
  - **Outputs:** Role schema.

- `kargo.upsert_role`
  - **Purpose:** Create or update a Kargo Role with specific permissions, e.g., promoting or approving in selected stages.[^11][^20]
  - **Inputs:** Role spec with permission set.
  - **Outputs:** Updated Role resource.

- `kargo.check_permission`
  - **Purpose:** Check whether a given identity (ServiceAccount or derived caller identity) has permission for an operation (e.g., approve promotion in stage X).
  - **Inputs:** `projectName`, `stageName`, `operation`, `identity`.
  - **Outputs:** Boolean result and explanation referencing underlying Kubernetes RBAC.

### Observability and Diagnostics Tools

- `kargo.describe_topology`
  - **Purpose:** Summarize the DAG of stages and the mapping from Warehouses to stages and promotions.[^6][^15]
  - **Inputs:** `projectName`.
  - **Outputs:** Topology description and adjacency lists.

- `kargo.analyze_promotion_blockers`
  - **Purpose:** Identify why a specific freight is not progressing (e.g., pending verification, failed promotion, policy constraints).
  - **Inputs:** `projectName`, `freightID`.
  - **Outputs:** Diagnostic explanation referencing Stage and Promotion states.[^13][^18]

- `kargo.summarize_release`
  - **Purpose:** Summarize the status of all freight associated with a given release tag, commit, or version.
  - **Inputs:** `projectName`, artifact identifier (e.g., image tag, Git SHA).
  - **Outputs:** Summary of which stages have promoted and verified the associated freight, plus links to Promotions.[^24][^2]

***

## Supported Workflows in the Kargo MCP Server

### Onboarding a New Application or Infrastructure Pipeline

End‑to‑end onboarding involves:

1. Using `kargo.upsert_project` to declare a project with promotion policies.
2. Creating one or more Warehouses with `kargo.upsert_warehouse` (analogous to `kargo create warehouse` in CLI) pointing to image, Git, or Helm sources.[^2][^19]
3. Defining a basic DAG of stages (e.g., dev → staging → prod) with `kargo.upsert_stage`, specifying requestedFreight origins and PromotionTask references.[^6][^15]
4. Defining reusable PromotionTasks that update Git manifests, Helm charts, or infrastructure configurations, plus Argo CD or operator integrations.[^20][^16][^12]
5. Validating the configuration with `kargo.plan_stage_changes` and `kargo.validate_promotion_task` tools.

The MCP server orchestrates these steps with the model, enabling conversational design of a promotion pipeline aligned with GitOps principles.[^4][^21]

### Inspecting and Explaining Promotion State

For ongoing operations, typical workflows include:

- Listing stages and their current freight using `kargo.list_stages` and `kargo.list_freight`.
- For a given freight, retrieving its per‑stage status and explaining why it has or has not advanced using `kargo.get_freight` and `kargo.analyze_promotion_blockers`.[^18][^13]
- Visualizing the pipeline topology and where a release currently sits using `kargo.describe_topology` and `kargo.summarize_release`.

The model can then generate narrative explanations, incident reports, or deployment notes based on these resources.

### Manual Promotion and Approval Flows

When auto‑promotion is disabled for production or regulated environments, the MCP server enables human‑in‑the‑loop flows:

- Propose a promotion plan with `kargo.plan_promotion`, showing which artifacts will move, which Argo CD Applications or Pulumi stacks will change, and what verification steps will run.[^16][^20][^12]
- Once approved by a human operator via chat, execute the promotion with `kargo.create_promotion`.
- When Kargo requires explicit approval at the Stage, use `kargo.approve_promotion` to record an approval decision, which corresponds to manual approval actions in the Kargo UI or CLI.[^20][^18]

These workflows make approvals auditable and explainable while still driven by Kargo’s policies and RBAC.

### Debugging Failed Promotions

For failed promotions, the MCP server can:

- Use `kargo.get_promotion` to inspect the step graph, identify which step failed (e.g., `git-push` or `argocd-wait`), and surface log and error summaries.[^12][^16]
- Correlate failure with verification results, such as failed health checks or blocked Argo Rollouts analysis.
- Suggest remediation actions, such as rolling back via `kargo.rollback_stage`, updating PromotionTasks, or adjusting verification thresholds.

By combining this with resource data from Warehouses and Stages, the model can provide rich incident analysis and playbooks.

### Coordinated Application and Infrastructure Promotions

In scenarios where application and infrastructure must be coordinated:

- Stages corresponding to infrastructure environments (e.g., Pulumi stacks or Terraform configurations) and application environments can be connected in the same DAG or linked via requestedFreight conditions.[^3][^20]
- PromotionTasks use `hcl-update` or other infrastructure steps alongside Argo CD or Helm steps, ensuring that infrastructure changes and application releases are promoted together with shared policies and verification.[^21][^12]
- The MCP server can manage and explain these complex pipelines, ensuring that guardrails are respected and that operators can reason about resource dependencies.

***

## Internal Architecture of the Kargo MCP Server

### Integration with Kubernetes and Kargo APIs

The MCP server should integrate with Kargo primarily through the Kubernetes API for Kargo CRDs (`Project`, `Stage`, `Warehouse`, `Freight`, `Promotion`, `PromotionTask`, etc.), possibly using the Kargo CLI for certain workflows where the CLI packages recommended logic.[^25][^5][^15]

- A dedicated Kubernetes client layer handles CRUD operations on CRDs and watches for updates where resource streams are supported.
- When necessary, the server can call Kargo’s HTTP APIs (if available) or reuse CLI commands in a controlled environment to align behaviour with official tooling.[^25]

### MCP Layer and Capability Registration

Following MCP server development guidelines and reference implementations, the architecture should include:[^22][^23]

- A core `McpServer` instance initialized with server metadata and capabilities.
- Separate modules for tools and resources:
  - `tools/projects`, `tools/stages`, `tools/promotions`, `tools/tasks`, `tools/rbac`, etc.
  - `resources/project`, `resources/stage`, `resources/freight`, `resources/promotion`, etc.
- Schema definitions for inputs/outputs using a validation library (e.g., Zod) to match MCP tool/resource schema expectations.
- HTTP (or other) transport that exposes a single MCP endpoint, handling JSON‑RPC, sessions, and streaming according to the MCP spec.

This modular approach aligns with best practices for MCP servers and simplifies future extensions.[^23][^9]

### Security, RBAC, and Multi‑Tenancy

The Kargo MCP server must respect Kargo and Kubernetes RBAC:

- Each request should map to a Kubernetes identity (ServiceAccount or user) whose permissions are enforced by the Kubernetes API when interacting with Kargo CRDs.[^5][^11]
- Tools that change promotion state or configuration must perform explicit permission checks using Role and RoleBinding information, possibly exposing `kargo.check_permission` as both an internal and external helper.[^11]
- Multi‑tenant environments use Project‑scoped namespaces and Kargo Roles to isolate tenants; the MCP server should ensure that resource URIs and tools do not leak data across projects.

### Observability and Auditing

To support enterprise use, the server should integrate with existing logs and metrics:

- Promotion and approval actions should be logged with identity and request metadata for auditing and compliance.
- Metrics about tool usage, promotion success/failure rates, and latency can be exposed to monitoring systems.
- When combined with Akuity’s enterprise platform, Kargo’s promotion audit trails can be surfaced via the MCP server for AI‑driven analysis.[^17][^21]

***

## Conclusion

Kargo provides a rich, GitOps‑native model for continuous promotion across application and infrastructure environments, built on Projects, Warehouses, Freight, Stages, Promotions, and reusable PromotionTasks. The Model Context Protocol offers a natural fit for exposing these concepts to AI agents, using resources for state and tools for actions, all while respecting Kargo’s policies and RBAC.[^1][^6][^12]

The design in this report defines a comprehensive resource model, extensive tool surface, and concrete workflows that together allow an MCP server to cover "everything the platform is giving" around promotions, from pipeline design and automation to approvals, troubleshooting, and cross‑stack orchestration. Implemented with standard MCP server patterns and careful Kubernetes integration, this Kargo MCP server can become a powerful foundation for multi‑agent DevOps and platform engineering workflows.[^21][^13][^20]

---

## References

1. [Kargo the New Promotion Orchestrator for Argo CD - Alexander Extim](https://www.extim.su/blog/kargo-the-new-promotion-orchestrator-for-argo-cd-%F0%9F%94%A5/) - A continuous promotion orchestrator that complements Argo CD for Kubernetes. Built and maintained by...

2. [Working with Warehouses - Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-warehouses/) - When a Warehouse observes a new revision of any artifact to which it subscribes, it creates a new Fr...

3. [Multi-Environment Promotion Is the Missing GitOps Piece ... - YouTube](https://www.youtube.com/watch?v=--Wz2-PZI-g) - ... Argo CD at Intuit to launching Kargo, the multi-environment promotion engine that's now seeing m...

4. [Kargo](https://kargo.io) - Kargo is a continuous promotion orchestration layer, that complements Argo CD for Kubernetes. Built ...

5. [Working with Projects | Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-projects) - Each Kargo project is represented by a cluster-scoped Kubernetes resource of type Project. Reconcili...

6. [Key Kargo Concepts](https://release-1-1.docs.kargo.io/concepts/) - A promotion is a request to move a piece of freight into a specified stage. Corresponding Resource T...

7. [Resources - Model Context Protocol （MCP）](https://modelcontextprotocol.info/docs/concepts/resources/) - Expose data and content from your servers to LLMs

8. [Resources - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)

9. [Tools - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

10. [What's New in Kargo v0.4.0 - Akuity Blog](https://akuity.io/blog/whats-new-kargo-0-4-0) - Deploy with Argo CD, promote seamlessly with Kargo, and gain real-time visibility into your infrastr...

11. [What's New in Kargo v0.6.0 - Akuity](https://akuity.io/blog/whats-new-kargo-0-6-0) - A Kargo Role exists as long as an underlying ServiceAccount resource with the same name exists in th...

12. [Promotion Steps Reference | Kargo Docs](https://docs.kargo.io/user-guide/reference-docs/promotion-steps/) - Below is an overview of the available promotion steps that can be used in

13. [Introduction to Kargo: GitOps Promotion Pipelines for Kubernetes](https://burrell.tech/blog/kargo/) - It does not require you to change how Argo CD deploys applications. It simply adds the orchestration...

14. [Feature request: per-warehouse auto-promotion control on stages ...](https://github.com/akuity/kargo/issues/5952) - Allow promotionPolicies in ProjectConfig to scope auto-promotion to specific warehouse origins, rath...

15. [Working with Stages | Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-stages) - When a Stage accepts Freight directly from its origin, all new Freight created by that origin (e.g. ...

16. [kargo-pipeline-helm/docs/PROMOTIONS.md at main - GitHub](https://github.com/pww217/kargo-pipeline-helm/blob/main/docs/PROMOTIONS.md) - A promotionTemplate is part of the Stage spec (not a separate CRD). It defines what steps run when F...

17. [Akuity: The Enterprise Software Delivery Platform, Powered by AI](https://akuity.io) - Built by the creators of Argo CD and Kargo, Akuity provides enterprise-ready delivery, continuous pr...

18. [Working With Freight | Kargo Docs](https://docs.kargo.io/user-guide/how-to-guides/working-with-freight) - Freight is an important Kargo concept. A single "piece of freight" is a set of references to one or ...

19. [Implementing a Modular Kargo Promotion Workflow](https://dev.to/josephcc/implementing-a-modular-kargo-promotion-workflow-extracting-promotiontask-from-stage-for-4npi) - A fully operational GitOps-native upgrade pipeline, designed for reuse and scalability This is Part....

20. [Configuring Kargo](https://www.pulumi.com/blog/pulumi-kubernetes-operator-and-kargo/) - Use Kargo with the Pulumi Kubernetes Operator to control how infrastructure changes are promoted acr...

21. [What is Kargo? Simplifying Continuous Promotion with GitOps - Akuity](https://akuity.io/what-is-kargo) - With Kargo, teams can automate and secure application promotions using GitOps workflows - without ma...

22. [GitHub - modelcontextprotocol/servers: Model Context Protocol Servers](https://github.com/modelcontextprotocol/servers) - Model Context Protocol Servers. Contribute to modelcontextprotocol/servers development by creating a...

23. [Model Context Protocol (MCP) Server Development Guide … - GitHub](https://github.com/cyanheads/model-context-protocol-resources/blob/main/guides/mcp-server-development-guide.md) - Exploring the Model Context Protocol (MCP) through practical guides, clients, and servers I've built...

24. [How to Automate CI/CD Pipelines with Kargo (Live Demo) - YouTube](https://www.youtube.com/watch?v=2O1eQntjR-U) - Key Kargo concepts: Freight, Warehouses, Stages, and Subscriptions ... Live demo: End-to-end deploym...

25. [akuity/kargo: Application lifecycle orchestration - GitHub](https://github.com/akuity/kargo) - If you are interested in enterprise-scale Kargo hosted, managed, and professionally supported by Aku...

