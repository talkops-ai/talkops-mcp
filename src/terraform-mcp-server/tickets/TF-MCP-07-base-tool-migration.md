# TF-MCP-07 — Base tool migration and dead code removal

## Goal

Remove inconsistent abstractions and ensure a **single** registration and response path.

## Scope

- Deprecate or remove **`BaseMCPTool`** / **`register_tool_with_fastmcp`** if superseded by Traefik-style `BaseTool` + class `register()` (or consolidate into one approach only).
- Remove **unused imports** (e.g. `register_tool_with_fastmcp` imported in `server.py` but never called).
- Align **`execute_with_validation`** vs direct **`execute`**: avoid nested `format_response` / duplicate `success` envelopes.
- Update **`terraform_mcp_server/core/tools/__init__.py`** exports to match the new public surface.

## Acceptance criteria

- [ ] No dead registration helper left in the package without tests or callers.
- [ ] Grep confirms no `mcp.server.fastmcp` for FastMCP/Context in terraform package after migration.
- [ ] At least one unit test asserts JSON shape for a tool success path (parse once).

## References

- `src/terraform-mcp-server/terraform_mcp_server/core/tools/base_tool.py`
- `src/terraform-mcp-server/terraform_mcp_server/server.py` (legacy; remove after TF-MCP-09)

## Depends on

TF-MCP-04

## Blocks

TF-MCP-09 (final cleanup)
