# TF-MCP-06 — ServerConfig and service locator

## Goal

Compose **MCP server/runtime settings** with the existing `Config` class without rewriting the full config system.

## Scope

- Introduce **`ServerConfig`** (dataclass or equivalent): `name`, `version`, `transport`, `host`, `port`, `path`, `debug`, and optional flags (e.g. gate dangerous terraform execution) as the plan specifies.
- Load from **environment** with predictable names (e.g. `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_PATH`, `MCP_DEBUG`) aligned with Traefik naming where sensible.
- **`service_locator`** built in bootstrap: include `config` (existing `Config`), `server_config` or merged surface, and service instances (`neo4j_graph` / graph service, etc.).

## Acceptance criteria

- [ ] Bootstrap constructs one clear locator dict passed to `initialize_tools` and `initialize_resources`.
- [ ] `BaseTool` (or equivalent) fails fast if required keys are missing (e.g. `config`).
- [ ] Document default transport and how it differs from legacy Click defaults (if changed).

## References

- `src/traefik-mcp-server/traefik_mcp_server/config.py`
- `src/terraform-mcp-server/terraform_mcp_server/config/config.py`

## Depends on

TF-MCP-01 (optional: none if only dataclass + env)

## Blocks

TF-MCP-02, TF-MCP-04, TF-MCP-05
