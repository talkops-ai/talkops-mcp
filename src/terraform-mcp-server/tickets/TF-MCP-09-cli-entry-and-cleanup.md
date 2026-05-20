# TF-MCP-09 — CLI entry and legacy cleanup

## Goal

Point the console entry at the new `main`, delegate Click options to bootstrap, and retire the monolithic `server.py` wiring.

## Scope

- Update **`terraform_mcp_server/__main__.py`**: Click options call into new `main()` / bootstrap (host, port, transport aligned with `ServerConfig`).
- Update **`pyproject.toml`** `[project.scripts]`: add **`terraform-mcp-server`** entry (or alias) pointing at `terraform_mcp_server.main:main`; keep or deprecate `agents-mcp-server` per product decision.
- Remove or shrink **`terraform_mcp_server/server.py`**: delete `register_tf_*` and `main()` once equivalent behavior lives in bootstrap + tools; leave a thin re-export or remove file if unused.
- Update **`.gitignore** / packaging** if tests or new modules need inclusion (setuptools `packages.find`).

## Acceptance criteria

- [ ] `python -m terraform_mcp_server` and installed script both start the new stack.
- [ ] No duplicate server entrypoints with conflicting behavior.
- [ ] Legacy `server.py` either gone or documented shim with removal date.

## References

- `src/traefik-mcp-server/pyproject.toml` (`traefik-mcp-server` script)
- `src/terraform-mcp-server/terraform_mcp_server/__main__.py`

## Depends on

TF-MCP-02, TF-MCP-04, TF-MCP-07

## Blocks

None
