# TF-MCP-05 — MCP resources (`terraform://`)

## Goal

Add MCP **resources** using the same registry + `BaseResource` pattern as Traefik (distinct from “Terraform resource” in domain language).

## Scope

- Add **`terraform_mcp_server/resources/registry.py`**, **`base.py`**, **`__init__.py`** with `initialize_resources(service_locator) -> ResourceRegistry` and `register_all_resources(mcp)`.
- Implement at least:
  - **`terraform://knowledge-graph/stats`** — aggregate Neo4j / graph stats (chunk counts, embedding coverage); reuse query patterns from `core/ingestion/neo4j_ingestion.py` where appropriate.
  - **`terraform://server/config-summary`** — operator-facing summary with **secrets redacted** (no passwords, API keys).
- Handlers return `str` (JSON or markdown), async, consistent error JSON on failure.

## Acceptance criteria

- [ ] Resources appear in MCP `resources/list`.
- [ ] `resources/read` works for each documented URI template.
- [ ] Config resource never echoes `NEO4J_PASSWORD` or other secrets.

## References

- `src/traefik-mcp-server/traefik_mcp_server/resources/registry.py`
- `src/traefik-mcp-server/traefik_mcp_server/resources/traffic_resources.py`
- `src/terraform-mcp-server/terraform_mcp_server/core/ingestion/neo4j_ingestion.py`

## Depends on

TF-MCP-02, TF-MCP-06

## Blocks

TF-MCP-08 (resource tests)
