# Project Agent Instructions

This project is a Python MCP server. The package source lives under
`src/piazza_mcp/`.

## Runtime Compatibility

- Support Python 3.10 through 3.14.
- The server currently uses the MCP Python SDK v1 low-level `Server` decorator
  API. Keep the runtime requirement at `mcp>=1.28.1,<2` until an intentional
  MCP 2 migration updates the handlers, result construction, tests, and
  transport setup together.
- When changing dependencies, update both `pyproject.toml` and `uv.lock`.
- Do not assume that passing locked tests proves package compatibility. For
  dependency or packaging changes, install the built wheel in a clean
  environment so its declared dependency ranges are resolved independently of
  `uv.lock`.

## Architecture

- `src/piazza_mcp/server.py` is the MCP protocol boundary. Keep MCP handlers thin.
- `src/piazza_mcp/mcp_tools/` owns tool descriptions, input schemas, and MCP
  annotations.
- `src/piazza_mcp/mcp_schemas/` owns structured-output schemas.
- `src/piazza_mcp/services/` contains domain and service logic.
- `src/piazza_mcp/models/` contains simple data structures.
- `src/piazza_mcp/config/` owns environment and configuration loading.

Prefer putting reusable behavior in services instead of in MCP handlers. Keep
configuration loading out of services except through injected values or config
exports. Keep external APIs behind injectable client protocols or adapters, and
perform lazy configured composition in the domain factory modules.

## Secrets and External Data

- Never read, print, search, or include the contents of `.env` in command
  output. Discover configuration names from `src/piazza_mcp/config/`, tests, or
  the redacted `.env.example`.
- Never expose Piazza passwords, cookies, course IDs, post contents, or personal
  names in logs, fixtures, documentation, or prompts.
- Do not make live Piazza calls during ordinary tests. Use fixtures, fakes, and
  injected clients.
- Run the live inspection scripts only when the user explicitly authorizes
  access to the configured external service.
- Preserve Piazza's read-only behavior, configured-course allowlist, request
  and response bounds, truncation, and untrusted-content warnings.

## Coding Workflow

- Ask when requirements are ambiguous.
- Prefer small, targeted changes.
- Do not refactor unrelated code.
- Match the existing project style.
- Avoid speculative abstractions or features that were not requested.
- Every changed line should trace back to the user's request.

## Verification

Choose checks proportional to the change. CI's primary checks are:

```bash
uv lock --check
uv run --frozen pytest -q
uv run --frozen python -m compileall -q src/piazza_mcp tests scripts
uv build
```

- For dependency or packaging changes, also install the wheel into a clean
  Python 3.14 environment and verify `import piazza_mcp.server` plus the
  `piazza-mcp` console entry point.
- For MCP tool changes, test the catalog, registered dispatch path, input
  schema, and structured-output schema.
- For configuration changes, test lazy loading so importing the server never
  requires credentials.
- Never use real credentials or live external calls as test fixtures.
