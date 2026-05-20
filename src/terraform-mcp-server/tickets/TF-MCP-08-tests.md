# TF-MCP-08 — Tests

## Goal

Add automated tests so the refactor is safe to validate in CI and during architect review.

## Scope

Create `src/terraform-mcp-server/tests/` (or agreed location) with at least:

1. **`test_tool_registry.py`** — `ToolRegistry.register_all_tools` with mock MCP; correct number of registrations.
2. **`test_bootstrap.py`** — patch Neo4j / heavy deps; `ServerBootstrap.initialize()` returns `(mcp, config)` without live services.
3. **`test_middleware_config.py`** — `setup_middleware` on fresh `FastMCP` does not raise.
4. **Domain tool tests** — e.g. `VectorSearchInput` validation; mocked vector search; mocked subprocess for execution; ingestion filter resolution / mocks.
5. **`test_resources.py`** — mocked graph for stats; config-summary redaction.

Use **pytest**, **pytest-asyncio**, **unittest.mock** (Traefik test style).

## Acceptance criteria

- [ ] `pytest` passes from package root / CI job.
- [ ] Async tests marked or configured correctly.
- [ ] Tests do not require real Neo4j/OpenAI for default CI run (mocks/fixtures).

## References

- `src/traefik-mcp-server/tests/test_servers_transport_service.py` (style)
- Migration plan “Test strategy” section

## Depends on

TF-MCP-02, TF-MCP-03, TF-MCP-04, TF-MCP-05 (test against stable APIs)

## Blocks

None (can land incrementally with features)
