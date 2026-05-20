# TF-MCP-03 — Tool registry and BaseTool

## Goal

Introduce the same registry and abstract base class pattern as Traefik for all MCP tools.

## Scope

- Add **`terraform_mcp_server/tools/registry.py`**: `ToolRegistry` with `register_tool`, `register_all_tools(mcp)`.
- Add **`terraform_mcp_server/tools/base.py`**: `BaseTool` with `__init__(service_locator: Dict[str, Any])`, abstract `register(self, mcp) -> None`; require `config` (or agreed key) in locator.
- Add **`terraform_mcp_server/tools/__init__.py`**: `initialize_tools(service_locator) -> ToolRegistry` that instantiates tool category classes and registers them (empty or stub list until TF-MCP-04 fills implementations).

## Acceptance criteria

- [ ] API mirrors Traefik’s `ToolRegistry` / `BaseTool` responsibilities (naming may stay `terraform_*` prefixed).
- [ ] No tool registration remains only inside a 400-line `server.py` after TF-MCP-04/09.

## References

- `src/traefik-mcp-server/traefik_mcp_server/tools/registry.py`
- `src/traefik-mcp-server/traefik_mcp_server/tools/base.py`
- `src/traefik-mcp-server/traefik_mcp_server/tools/__init__.py`

## Depends on

TF-MCP-01

## Blocks

TF-MCP-04
