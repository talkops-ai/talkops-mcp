# TF-MCP-10 — Docs and operators (optional)

## Goal

Short operator-facing notes so deployers know env vars, transports, and entrypoints after the refactor.

## Scope (optional)

- Update **`README.md`** (root of `terraform-mcp-server` or monorepo section): how to run stdio vs HTTP, required env vars (`MCP_*`, `NEO4J_*`, embedding keys).
- Update **`.env.example`** if new `MCP_*` variables are introduced.
- Document **breaking changes** (script rename, transport default change) if any.

## Acceptance criteria

- [ ] New team member can start server and point an MCP client using only README + `.env.example`.
- [ ] Secrets and cache TTL philosophy summarized in one paragraph (optional).

## References

- `src/terraform-mcp-server/README.md`
- `src/terraform-mcp-server/.env.example`

## Depends on

TF-MCP-09

## Blocks

None
