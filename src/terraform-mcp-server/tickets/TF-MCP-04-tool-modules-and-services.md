# TF-MCP-04 — Tool modules and services

## Goal

Move the three existing tools (search, ingestion, execution) into Traefik-style tool classes that implement `register()`, and optionally introduce thin **services** for Neo4j/graph and Terraform CLI boundaries.

## Scope

- Implement tool category classes (e.g. `TerraformSearchTools`, `TerraformIngestionTools`, `TerraformExecutionTools`) under `terraform_mcp_server/tools/` (subpackage as the team prefers), each with `register(mcp)` defining `@mcp_instance.tool()` handlers.
- Use **`pydantic.Field`** on MCP-facing parameters where it improves schema (Traefik pattern); keep or reuse existing Pydantic input models inside `execute` logic in `core/tools/` or colocated modules.
- **Services (recommended):** e.g. `Neo4jGraphService` / facades wrapping `Neo4jGraph` and vector lifecycle; execution validation/subprocess behind a small service. Wire via **`service_locator`** keys agreed in TF-MCP-06.
- **Compatibility:** preserve public MCP tool **names** and primary **JSON response shape** (`terraform_doc_search`, ingestion tool name, execution tool name—match current behavior unless versioned alias is introduced).

## Acceptance criteria

- [ ] All three tools registered only through `initialize_tools` → `ToolRegistry` → `register_all_tools`.
- [ ] `from fastmcp import Context` (not `mcp.server.fastmcp`) in touched modules.
- [ ] No double JSON wrapping: client-visible payload parses as one JSON object with the legacy contract.

## References

- `src/traefik-mcp-server/traefik_mcp_server/tools/traefik/backend_endpoints_tools.py` (registration + Field pattern)
- `src/terraform-mcp-server/terraform_mcp_server/core/tools/tf_search_tool.py`
- `src/terraform-mcp-server/terraform_mcp_server/core/tools/tf_ingestion_tool.py`
- `src/terraform-mcp-server/terraform_mcp_server/core/tools/tf_execution_tool.py`

## Depends on

TF-MCP-02, TF-MCP-03, TF-MCP-06 (locator keys stable)

## Blocks

TF-MCP-07, TF-MCP-08, TF-MCP-09
