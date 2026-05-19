# TF-MCP-01 — Dependencies and pyproject

## Goal

Align the Terraform MCP package with the same FastMCP stack as Traefik and separate development dependencies from runtime.

## Scope

- Add **`fastmcp`** to project dependencies; resolve overlap with **`mcp[cli]`** (prefer one coherent MCP stack; mirror Traefik’s approach in `src/traefik-mcp-server/pyproject.toml`).
- Move **`pytest`** and **`pytest-asyncio`** out of the main runtime dependency list into optional dev / `[dependency-groups] dev` (or equivalent).
- Pin or constrain versions where the team standard requires it.

## Acceptance criteria

- [ ] `from fastmcp import FastMCP, Context` is valid after install (no missing transitive deps).
- [ ] Production install path does not require pytest.
- [ ] `uv sync` / `pip install -e .` documented or unchanged for local dev including dev extras.

## References

- `src/terraform-mcp-server/pyproject.toml`
- `src/traefik-mcp-server/pyproject.toml`

## Depends on

None.

## Blocks

TF-MCP-02, TF-MCP-03 (imports assume fastmcp available).
