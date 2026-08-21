# course-mcp

`course-mcp` is a local Python MCP server for referencing course files,
upcoming Canvas calendar work, and configured Piazza discussions.

The project combines safe local-file access with bounded, read-only course data
from configured external sources.

## Current Features

- Loads `ROOT_DIR` from `.env` or the process environment.
- Restricts file access to paths inside `ROOT_DIR`.
- Provides a `FileService` for safe file reads.
- Provides a `CourseService` for course/file listing and searching.
- Reads a private Canvas iCalendar feed without requiring a Canvas access token.
- Reads configured Piazza discussions through the community-built, unofficial
  `piazza-api` package.
- Exposes MCP tools:
  - `list-courses`: lists the top-level course directories under `ROOT_DIR`.
  - `list-course-files`: lists the direct files inside a course directory.
  - `search-course-file`: searches one UTF-8 text or text-extractable PDF file
    within a course using case-insensitive literal matching.
  - `search-course`: recursively searches eligible files throughout one course.
  - `get-upcoming-work`: returns assignments and events from a bounded date
    range in the Canvas calendar feed.
  - `list-piazza-courses`: lists configured Piazza courses accessible to the
    authenticated account.
  - `list-piazza-posts`: returns bounded recent post summaries without loading
    every full thread.
  - `get-piazza-post`: returns one bounded normalized Piazza thread.
  - `search-piazza-posts`: uses Piazza's feed search and returns bounded
    summaries.

`search-course-file` requires `course_title`, a course-relative `file_path`, and
a non-empty `keyword`. It optionally accepts `context_lines` (default 3, maximum
20) and `max_results` (default 20, maximum 100). Search results are returned as
JSON with matching line numbers and merged context excerpts. PDF results also
identify the one-based page containing each excerpt. Scanned PDFs require OCR
and are not supported.

`search-course` accepts the same `keyword`, `context_lines`, and `max_results`
search controls, but applies `max_results` independently to every matching file.
It searches direct course files and directories through depth 5. Hidden entries,
symbolic links, and directories named `venv`, `__pycache__`, `node_modules`,
`dist`, or `build` are skipped. Other unreadable or non-searchable files are
also skipped without failing the course-wide search.

Both search tools return schema-validated results in MCP `structuredContent`.
They also include the same result serialized as JSON `TextContent` for clients
that do not yet consume structured tool output.

`get-upcoming-work` accepts optional `start_date` and `end_date` values in
`YYYY-MM-DD` format. Both dates are inclusive; without them, the tool returns
the seven calendar dates beginning today. It also accepts an optional literal
`query` and `max_results` from 1 through 100. The result identifies whether its
calendar data is stale, whether it was truncated, and how many calendar events
could not be normalized through `skipped_event_count`. If a non-empty feed has
no usable events, the tool returns stale cached data when available or a clear
error instead of reporting a fresh empty calendar.

The calendar feed includes dated Canvas assignments and events, but it cannot
report submission state, grades, or Canvas To Do items. Course hints and item
types remain unknown unless they can be derived reliably from the feed.

Piazza tools are read-only and restricted to the course IDs explicitly listed
in `PIAZZA_COURSES`. Post text is returned as bounded plain text and identified
as untrusted user-generated content. The tools do not post, answer, edit,
download attachments, expose rosters, or perform instructor operations.

The Piazza integration depends on unpublished internal endpoints. It is useful
for personal experimentation but is not an official Piazza API, may break when
Piazza changes its website, and may be subject to Piazza or institutional usage
rules. Keep request limits conservative and do not use it for bulk collection.

## Project Layout

```text
src/course_mcp/
  server.py              MCP server boundary
  config/
    env.py               shared lazy .env loading
    filesystem.py        course-root configuration
    calendar.py          Canvas calendar configuration
    piazza.py            Piazza credentials and course allowlist
  mcp_schemas/           MCP JSON Schema contracts
  mcp_tools/             MCP tool catalog
  models/
    calendar_item.py     normalized calendar data
    piazza.py            bounded Piazza domain models
  services/
    calendar/
      feed_client.py     bounded private-feed loading and cache metadata
      parser.py          RFC 5545 parsing
      profiler.py        aggregate-only feed-shape diagnostics
      service.py         date filtering and result serialization
      factory.py         lazy configured calendar construction
    course/
      service.py         course-oriented operations
      factory.py         lazy course/file composition
    file/
      service.py         safe filesystem access
      pdf_extractor.py   page-oriented PDF text extraction
      factory.py         lazy configured file construction
    piazza/
      client.py          timeout-bound adapter around unofficial piazza-api
      normalizer.py      HTML cleanup and response normalization
      profiler.py        aggregate-only response-shape diagnostics
      service.py         allowlisting, limits, caching, and serialization
      factory.py         lazy configured Piazza construction
tests/                   pytest tests
skills/                  project-specific agent skills
```

## Configuration

Create a `.env` file at the project root:

```bash
ROOT_DIR="/Users/markseeliger/Desktop/Classes/UMD"
CANVAS_ICAL_URL="https://umd.instructure.com/feeds/calendars/user_REDACTED.ics"
CALENDAR_TIMEZONE="America/New_York"
PIAZZA_EMAIL="student@example.edu"
PIAZZA_PASSWORD="replace-with-your-password"
PIAZZA_COURSES='{"abc123":"CMSC 132","xyz789":"CMSC 216"}'
```

`ROOT_DIR` must point to an existing directory. Each direct child directory is
treated as a course. It is loaded only when a course-backed tool is called;
importing the server does not require course or calendar configuration.

You can also pass `ROOT_DIR` directly through the environment instead of using
`.env`.

To obtain the calendar URL, sign in to ELMS-Canvas, open the global
**Calendar**, select **Calendar Feed** in the sidebar, and copy the URL field.
The URL is a private credential: do not commit it, paste it into tickets or
chat, or include it in logs and screenshots. This repository ignores `.env`;
restrict that file so only your account can read it.

For offline use, configure a downloaded snapshot instead of the URL:

```bash
CANVAS_ICAL_PATH="/absolute/private/path/calendar.ics"
CALENDAR_TIMEZONE="America/New_York"
```

Configure exactly one of `CANVAS_ICAL_URL` and `CANVAS_ICAL_PATH`. Calendar
configuration is loaded only when `get-upcoming-work` is called, so the
existing local course tools remain available without it. Live results are
cached in memory for five minutes; after a refresh failure, a previous result
may be returned with `stale: true`.

Piazza configuration is also lazy: the server and unrelated tools work without
Piazza variables. `PIAZZA_COURSES` is a JSON mapping from Piazza course IDs to
the names the agent should display. A course ID is the value after `/class/` in
a Piazza course URL. Every course-scoped call is rejected unless its ID appears
in this mapping, and `list-piazza-courses` returns only configured courses that
the authenticated account can access.

Store the Piazza password only in a private local environment or MCP process
configuration. Never commit `.env`, paste credentials into prompts, or include
them in logs. Accounts that require institution-only SSO may not support the
email/password flow used by the unofficial package.

## Run Locally

From this project directory:

```bash
uv run course-mcp
```

Because MCP servers run over stdio, they are usually launched by an MCP client
rather than run directly by hand.

## Install In Codex

Register the server with Codex:

```bash
codex mcp add course-mcp \
  --env ROOT_DIR=/Users/markseeliger/Desktop/Classes/UMD \
  -- uv --directory /Users/markseeliger/Desktop/Coding/create-python-server/course_mcp run course-mcp
```

Verify the registration:

```bash
codex mcp get course-mcp
```

Or refresh the registration with the project script:

```bash
ROOT_DIR=/Users/markseeliger/Desktop/Classes/UMD ./scripts/update_mcp_server.sh
```

If you change MCP tools, restart Codex or start a new Codex session so the tool
list is reloaded.

## Development

Inspect the configured Canvas calendar's structure without printing event
values or the private feed URL:

```bash
uv run python scripts/inspect_canvas_calendar.py
```

The command reports only aggregate counts for usable/skipped events, date and
time shapes, selected field presence, and coarse URL types. A zero event count
means the feed is valid but does not yet provide representative data for course
matching; it is not evidence that the calendar integration is broken.

After knowingly selecting the unofficial Piazza transport, inspect a bounded
sample's structure without printing course IDs, post numbers, titles, bodies,
names, or cookies:

```bash
uv run python scripts/inspect_piazza_shapes.py
```

The inspector loads at most five feed summaries and one full thread from the
first configured course. Its output contains aggregate key/type/depth counts
only. It still makes live calls to unpublished Piazza endpoints, so do not run
it unless that access route is acceptable for your account.

Run the test suite:

```bash
uv run pytest
```

Run a compile check:

```bash
python3 -m compileall src/course_mcp tests
```

Debug with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv --directory /Users/markseeliger/Desktop/Coding/create-python-server/course_mcp run course-mcp
```
