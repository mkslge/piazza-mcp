# piazza-mcp

`piazza-mcp` is a local, read-only MCP server for searching and reading
configured Piazza discussions.

The server uses the community-built `piazza-api` package and Piazza's
unpublished internal endpoints. It is not an official Piazza integration and
may break when Piazza changes its website. Keep request limits conservative and
confirm that this access method is acceptable for your account and institution.

## Requirements

- Python 3.10 through 3.14.
- [`uv`](https://docs.astral.sh/uv/) for dependency and environment management.
- MCP Python SDK 1.x. The server uses the v1 low-level `Server` decorator API
  and declares `mcp>=1.28.1,<2`.

## Tools

- `list-piazza-courses`: lists configured courses accessible to the account.
- `list-piazza-posts`: returns bounded recent post summaries for one course.
- `get-piazza-post`: returns one bounded normalized thread.
- `search-piazza-posts`: searches one configured course and returns bounded
  summaries.

All tools are read-only. Course-scoped calls are restricted to IDs in
`PIAZZA_COURSES`. Returned post text is bounded plain text and is labeled as
untrusted user-generated content. The server does not post, answer, edit,
download attachments, expose rosters, or perform instructor operations.

`list-piazza-posts` accepts a `limit` from 1 through 25 and an `offset` from 0
through 500. Request another page only when the previous response reports
`truncated: true`. Searches accept a query of at most 200 characters and return
at most 25 results. Responses are cached in memory for 60 seconds; stale cached
data may be returned after a refresh failure.

## Configuration

Copy the redacted template and keep the resulting file private:

```bash
cp .env.example .env
chmod 600 .env
```

```bash
PIAZZA_EMAIL="student@example.edu"
PIAZZA_PASSWORD="replace-with-your-password"
PIAZZA_COURSES='{"abc123":"CMSC 132","xyz789":"CMSC 216"}'
```

`PIAZZA_COURSES` maps Piazza course IDs to display names. A course ID is the
value after `/class/` in a Piazza course URL. Process environment variables take
precedence over `.env`. When running an installed wheel outside this checkout,
provide the variables through the process environment.

Never commit `.env`, paste credentials into prompts, or include credentials,
cookies, course IDs, or post contents in logs. Accounts requiring
institution-only SSO may not support the email/password flow used by the
unofficial package.

## Run and Register

```bash
uv sync --locked
uv run --frozen piazza-mcp
```

Register the checkout with Codex:

```bash
codex mcp add piazza-mcp \
  -- uv --directory /absolute/path/to/piazza_mcp run --frozen piazza-mcp
```

The checkout-local `.env` is loaded lazily when the first Piazza tool is
called. You can refresh the registration with:

```bash
./scripts/update_mcp_server.sh
```

Restart the MCP client after changing the tool catalog.

## Project Layout

```text
src/piazza_mcp/
  server.py              MCP protocol boundary and dispatch
  config/
    env.py               lazy checkout-local .env loading
    piazza.py            credentials and course allowlist
  mcp_schemas/
    piazza.py            structured-output contracts
  mcp_tools/
    piazza.py            tool descriptions, inputs, and annotations
  models/
    piazza.py            bounded Piazza data structures
  services/piazza/
    client.py            timeout-bound unofficial API adapter
    normalizer.py        HTML cleanup and response normalization
    profiler.py          privacy-safe aggregate shape diagnostics
    service.py           allowlisting, limits, caching, and serialization
    factory.py           lazy configured service construction
tests/
  config/
  mcp_schemas/
  mcp_tools/
  server/
  services/piazza/
```

## Development

The privacy-safe inspector loads at most five summaries and one full thread,
then prints aggregate key, type, and nesting counts without printing post
values:

```bash
uv run --frozen python scripts/inspect_piazza_shapes.py
```

It still makes live requests. Run it only when you explicitly intend to access
the configured Piazza account.

Run the offline verification suite:

```bash
uv lock --check
uv run --frozen pytest -q
uv run --frozen python -m compileall -q src/piazza_mcp tests scripts
uv build
```

Debug the server with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector \
  uv --directory /absolute/path/to/piazza_mcp run --frozen piazza-mcp
```
