# TF-MCP-02 — Server skeleton (main, bootstrap, core, middleware)

## Goal

Replace monolithic `server.py` startup with the same layering as Traefik: thin entry, bootstrap wiring, FastMCP factory, middleware setup.

## Scope

- Add **`terraform_mcp_server/main.py`**: path/bootstrap if needed; call `ServerBootstrap.initialize()`; `mcp.run()` with transport branching (`stdio` vs `streamable-http` with host/port/path), matching the pattern in `traefik_mcp_server/main.py` + config.
- Add **`terraform_mcp_server/server/bootstrap.py`**: load configs, create MCP instance, build service locator, run any required init (e.g. Neo4j), register tools and resources.
- Add **`terraform_mcp_server/server/core.py`**: `create_mcp_server(server_config)` → `FastMCP(name=..., version=..., instructions=...)`; call `setup_middleware`.
- Add **`terraform_mcp_server/server/middleware.py`**: port middleware stack from `traefik_mcp_server/server/middleware.py` (error handling, optional transformation middleware, response caching, structured logging, timing). **Tune TTLs** for Terraform (search/ingestion vs list operations).

## Acceptance criteria

- [ ] Server starts via new entry path without importing the old monolithic registration functions for tools (those move in later tickets).
- [ ] Middleware order and types match Traefik categories; Terraform-specific cache behavior documented in code or ticket notes.
- [ ] Instructions load from static file or inline string; behavior defined.

## References

- `src/traefik-mcp-server/traefik_mcp_server/main.py`
- `src/traefik-mcp-server/traefik_mcp_server/server/bootstrap.py`
- `src/traefik-mcp-server/traefik_mcp_server/server/core.py`
- `src/traefik-mcp-server/traefik_mcp_server/server/middleware.py`
- `src/terraform-mcp-server/terraform_mcp_server/server.py` (source to decompose)

## Depends on

TF-MCP-01

## Blocks

TF-MCP-04, TF-MCP-05, TF-MCP-09
