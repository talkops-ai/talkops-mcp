# Kargo MCP Server Instructions

You are connected to the **Kargo MCP Server**, which provides tools, resources, and prompts for managing Kargo continuous promotion pipelines.

## Core Concepts

| Concept | Description |
|---------|-------------|
| **Project** | Organizational boundary; maps to a Kubernetes namespace |
| **Warehouse** | Subscribes to artifact sources (images, Git repos, Helm charts) and produces Freight |
| **Freight** | A set of versioned artifact references discovered by a Warehouse |
| **Stage** | A promotion target in the pipeline DAG (e.g., dev, staging, production) |
| **Promotion** | A request to move Freight into a Stage, executing promotion steps |
| **PromotionTask** | A reusable set of promotion steps (DRY pipeline abstractions) |
| **Credentials** | Repository credentials for authenticating to Git repos or container registries |

## Available Tools

### Unified Management Tools
- `kargo_project_mgmt` — Manage projects (create, update, delete, list, get)
- `kargo_stage_mgmt` — Manage stages (list, get, upsert, reverify)
- `kargo_warehouse_mgmt` — Manage warehouses (list, get, upsert, refresh)
- `kargo_freight_mgmt` — Manage freight (list, get, approve)
- `kargo_promotion_mgmt` — Manage promotions (list, get, create, abort)
- `kargo_promotion_task_mgmt` — Manage promotion tasks (list, get, upsert with presets)
- `kargo_credentials_mgmt` — Manage repository credentials (list, get, create, delete)

### Observability Tools
- `kargo_describe_topology` — Visualize pipeline DAG

## MCP Resources

Use `resources/read` to browse Kargo entities without needing tool calls:

| Resource URI | Description |
|---|---|
| `kargo://projects` | List all projects |
| `kargo://projects/{name}` | Get project details |
| `kargo://projects/{project}/stages` | List stages with topology |
| `kargo://projects/{project}/stages/{name}` | Get stage details |
| `kargo://projects/{project}/warehouses` | List warehouses |
| `kargo://projects/{project}/warehouses/{name}` | Get warehouse details |
| `kargo://projects/{project}/freight` | List freight |
| `kargo://projects/{project}/freight/{id}` | Get freight details |
| `kargo://projects/{project}/promotions` | List promotions |
| `kargo://projects/{project}/promotions/{name}` | Get promotion details |
| `kargo://projects/{project}/promotiontasks` | List promotion tasks |
| `kargo://projects/{project}/promotiontasks/{name}` | Get promotion task details |
| `kargo://projects/{project}/credentials` | List credentials (redacted) |
| `kargo://projects/{project}/credentials/{name}` | Get credential details (redacted) |
| `kargo://best-practices` | Kargo best practices guide |
| `kargo://promotion-steps` | Built-in promotion steps catalogue |

## Workflow Patterns

### Typical Promotion Flow
1. List freight to find available versions
2. Describe topology to understand the pipeline
3. Approve freight for the target stage (if manual approval required)
4. Create promotion to move freight
5. Monitor promotion progress

### Pipeline Setup Flow
1. Create a project
2. Create a warehouse with artifact subscriptions
3. Create a promotion task (or use inline steps)
4. Create stages referencing the warehouse and promotion task
5. Configure credentials if private repos are involved

### Investigation Flow
1. List projects to find the relevant project
2. Describe topology to see the pipeline DAG
3. List stages and freight to understand current state
4. Get specific resource details as needed

## Safety Rules
- Always check `allow_write` before mutating operations
- Verify freight approval status before promoting
- Use `kargo_describe_topology` to understand the DAG before making changes
- Monitor promotion status after creation
