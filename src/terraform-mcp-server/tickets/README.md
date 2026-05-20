# Terraform MCP server — migration tickets

Work items for the Traefik-aligned refactor. **Specification:** internal migration plan (Terraform MCP × Traefik parity) plus reference implementation under `src/traefik-mcp-server/traefik_mcp_server/`. **Validation:** architect rubric in that plan (structure, imports, compatibility, tests).

**Suggested order:** 01 → 06 → 02 → 03 → 04 & 05 in parallel → 07 → 08 (alongside) → 09 → 10 optional.

| ID | File | Summary |
|----|------|---------|
| TF-MCP-01 | [TF-MCP-01-dependencies-and-pyproject.md](TF-MCP-01-dependencies-and-pyproject.md) | `fastmcp`, dev deps, pins |
| TF-MCP-02 | [TF-MCP-02-server-skeleton.md](TF-MCP-02-server-skeleton.md) | `main`, bootstrap, core, middleware |
| TF-MCP-03 | [TF-MCP-03-tool-registry-and-base.md](TF-MCP-03-tool-registry-and-base.md) | Tool registry, `BaseTool`, `initialize_tools` |
| TF-MCP-04 | [TF-MCP-04-tool-modules-and-services.md](TF-MCP-04-tool-modules-and-services.md) | Tool classes + thin services |
| TF-MCP-05 | [TF-MCP-05-mcp-resources.md](TF-MCP-05-mcp-resources.md) | Resource registry, `terraform://` URIs |
| TF-MCP-06 | [TF-MCP-06-server-config.md](TF-MCP-06-server-config.md) | `ServerConfig`, env vars, locator |
| TF-MCP-07 | [TF-MCP-07-base-tool-migration.md](TF-MCP-07-base-tool-migration.md) | Remove dead paths, single response contract |
| TF-MCP-08 | [TF-MCP-08-tests.md](TF-MCP-08-tests.md) | Pytest modules and CI |
| TF-MCP-09 | [TF-MCP-09-cli-entry-and-cleanup.md](TF-MCP-09-cli-entry-and-cleanup.md) | `__main__`, scripts, retire monolith |
| TF-MCP-10 | [TF-MCP-10-docs-and-operators.md](TF-MCP-10-docs-and-operators.md) | Optional: README, env, transport |
