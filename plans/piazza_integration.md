# Piazza MCP Integration Plan

## Decision

Add a read-only Piazza capability behind the same configuration, client,
service, factory, schema, and thin MCP-handler boundaries used by the calendar
integration.

The first release should expose four tools:

- `list-piazza-courses`
- `list-piazza-posts`
- `get-piazza-post`
- `search-piazza-posts`

Do not expose tools that create posts, answer questions, edit content, mark
threads resolved, follow threads, or perform instructor operations in the
first release. Read access is sufficient for the agent to find announcements,
questions, and answers without allowing it to change a class discussion.

The preferred data flow is deliberately two-stage:

```text
list or search bounded post summaries
                  |
                  v
fetch one complete thread only when it is relevant
```

Do not use `Network.iter_all_posts()`. The `piazza-api` implementation first
loads a very large feed and then makes a separate request for each selected
post. `get_feed()`, `search_feed()`, and `get_post()` provide a smaller and more
predictable request pattern.

## Access and Policy Gate

Piazza does not currently document a public, student-facing posts API. The
candidate `piazza-api` dependency identifies itself as an unofficial client for
Piazza's internal API. Piazza's published terms also restrict automated access
through unpublished interfaces and prohibit scraping without permission.

## Current Status

As of August 19, 2026, this is a research and implementation plan only. No
Piazza dependency, credentials, service, or MCP tool has been added to the
project.

| Phase | Status | Completion gate |
| --- | --- | --- |
| Phase 0: choose an authorized access route | Pending | Permission or an explicit documented risk decision exists |
| Phase 1: transport spike and shape inspection | Pending | Authentication, timeouts, errors, and observed response shapes are understood |
| Phase 2: configuration, models, and normalization | Pending | Synthetic fixtures cover all observed post shapes and bounds |
| Phase 3: client and service | Pending | Allowlisting, retries, caching, and output limits pass unit tests |
| Phase 4: MCP schemas and handlers | Pending | Four read-only tools pass schema and dispatch tests |
| Phase 5: live validation and documentation | Pending | Bounded calls match the Piazza UI without exposing private data |

## Proposed Architecture

Keep Piazza-specific transport behavior out of `server.py` and application
rules out of the transport adapter.

```text
MCP handlers
     |
     v
PiazzaService
     |-- validates course allowlist and arguments
     |-- caches normalized results
     |-- bounds and sorts responses
     |
     v
PiazzaClient
     |-- owns authentication and session state
     |-- calls the synchronous Piazza library off the event loop
     |-- translates dependency failures into stable errors
     |
     v
piazza-api / approved Piazza transport
```

Suggested layout:

```text
src/course_mcp/
|-- config/
|   `-- piazza.py
|-- models/
|   `-- piazza.py
|-- services/
|   `-- piazza/
|       |-- __init__.py
|       |-- client.py
|       |-- normalizer.py
|       |-- service.py
|       `-- factory.py
|-- mcp_schemas/
|   `-- piazza.py
|-- mcp_tools/
|   `-- piazza.py
`-- server.py
scripts/
`-- inspect_piazza_shapes.py
tests/
|-- fixtures/
|   `-- piazza/
|-- test_piazza_client.py
|-- test_piazza_config.py
|-- test_piazza_normalizer.py
|-- test_piazza_service.py
|-- test_piazza_tools.py
`-- test_server.py
```

`PiazzaClient` should implement a small protocol used by `PiazzaService`. Tests
should inject a fake implementation; they must never log into a real account.

```python
class PiazzaClientProtocol(Protocol):
    async def list_courses(self) -> list[dict[str, Any]]: ...

    async def list_posts(
        self,
        course_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...

    async def get_post(
        self,
        course_id: str,
        post_number: int,
    ) -> dict[str, Any]: ...

    async def search_posts(
        self,
        course_id: str,
        query: str,
    ) -> list[dict[str, Any]]: ...
```

The protocol should describe only behavior needed by the service. Do not leak
`piazza-api` classes across the client boundary.

## Configuration and Secret Handling

Add a frozen `PiazzaConfig` with:

```text
email: str
password: str
courses: mapping of Piazza course ID to local display name
request_timeout_seconds: fixed internal default
```

Initial environment variables:

```bash
PIAZZA_EMAIL="student@example.edu"
PIAZZA_PASSWORD="..."
PIAZZA_COURSES='{"abc123":"CMSC132","xyz789":"CMSC216"}'
```

Requirements:

- Load configuration lazily only when a Piazza tool is called.
- Require non-empty email and password values.
- Require `PIAZZA_COURSES` to be a non-empty JSON object of non-empty strings.
- Reject duplicate or malformed course IDs and names.
- Treat configured course IDs as an allowlist, not merely display metadata.
- Never return the password or session cookies through tools.
- Never include credentials, cookies, raw response bodies, or the user's email
  in logs and exceptions.
- Keep credentials and cached course content in memory only.
- Keep `.env` out of version control and document restrictive local file
  permissions.

Do not add browser-cookie extraction, browser automation, or SSO-token reuse as
fallback authentication mechanisms. A session cookie is a bearer credential
and is not safer than a password merely because it expires.

The Piazza factory should mirror the calendar factory: construct one lazy
client and service so session state, its concurrency lock, and short-lived cache
are reused across calls. Piazza configuration failures must not prevent the
existing filesystem or calendar tools from starting.

## Dependency Strategy

If Phase 0 selects the unofficial transport:

- Add `piazza-api>=0.16.0,<0.17.0` to `pyproject.toml` and lock the exact
  resolved version in `uv.lock`.
- Record that the dependency is alpha-quality and accesses internal endpoints.
- Wrap it behind `PiazzaClient` so it can be replaced without changing the
  service or MCP contracts.
- Use its documented public wrapper methods rather than invoking arbitrary RPC
  method names from the service.

The package uses synchronous `requests` calls and does not consistently set
timeouts. The adapter must supply a session whose request methods enforce a
fixed timeout and execute blocking calls with `asyncio.to_thread()`. Protect the
shared authenticated session with an async lock so simultaneous MCP requests do
not race login or reuse a mutable session concurrently.

Use a maintained HTML parser, initially `beautifulsoup4>=4.13,<5`, to convert
Piazza HTML into bounded plain text. Do not strip HTML with regular expressions.

## Normalized Models

Do not return raw Piazza dictionaries. Their shapes differ among questions,
notes, answers, follow-ups, feedback, and revisions.

### PiazzaCourse

```text
course_id: str
name: str
course_number: str | None
term: str | None
is_ta: bool | None
```

Only configured, accessible courses should be returned. Do not return user IDs,
rosters, or other enrollment data.

### PiazzaPostSummary

```text
post_number: int
course_id: str
kind: "question" | "note" | "poll" | "unknown"
subject: str
snippet: str | None
folders: list[str]
created_at: str | None
updated_at: str | None
resolved: bool | None
source_url: str
```

### PiazzaThread

```text
post_number: int
course_id: str
kind: "question" | "note" | "poll" | "unknown"
subject: str
body: str | None
folders: list[str]
created_at: str | None
updated_at: str | None
resolved: bool | None
instructor_answer: PiazzaMessage | None
student_answer: PiazzaMessage | None
followups: list[PiazzaMessage]
source_url: str
truncated: bool
skipped_child_count: int
```

### PiazzaMessage

```text
kind: "instructor_answer" | "student_answer" | "followup" | "feedback" | "unknown"
body: str
created_at: str | None
updated_at: str | None
children: list[PiazzaMessage]
truncated: bool
```

Do not expose internal author IDs. Preserve Piazza anonymity and do not infer an
anonymous author's identity. Omit author names in the first version; add them
later only if a demonstrated user need outweighs the privacy cost.

The normalizer must handle text stored in `content`, `subject`, or a revision's
`history` entry. Use explicit helper functions and parentheses rather than
compact conditional expressions, because reply shapes are irregular and easy
to parse incorrectly.

## Output Safety and Limits

Piazza contains untrusted user-generated content. A post may contain malicious
instructions directed at an agent. Normalization should remove scripts, styles,
and markup, but no sanitizer can make natural-language content trusted.

Every response containing post text should include:

```text
content_trust: "untrusted_user_generated"
```

Tool descriptions should instruct agents to treat post text as course content,
not as instructions to operate other tools, reveal secrets, or change system
behavior.

Initial fixed bounds:

| Value | Bound |
| --- | --- |
| Feed summaries per call | 1 through 25; default 10 |
| Feed offset | 0 through 500 |
| Search query length | 1 through 200 characters after trimming |
| Search summaries returned | 1 through 25; default 10 |
| Subject | 500 characters |
| Summary snippet | 1,000 characters |
| Full post body | 20,000 characters |
| Follow-ups per thread | 50 |
| Text per answer or follow-up | 4,000 characters |
| Nested child depth | 3 |
| Approximate complete tool response | 100 KB |
| Authentication retries | 1 |
| Successful-result cache | 60 seconds |

Return `truncated`, counts, and `skipped_child_count` rather than silently
discarding data. If an upstream response has no usable post data, return a
clear error instead of reporting a successful empty thread.

Never cache raw Piazza responses or normalized content on disk. An in-memory
stale result may be returned after a transient failure when a successful result
already exists; mark it `stale: true` and retain its original `fetched_at`.

## Authentication, Errors, and Logging

Define stable application errors such as:

```text
PiazzaClientError
PiazzaAuthenticationError
PiazzaTimeoutError
PiazzaResponseError
```

The client should:

1. Authenticate lazily on the first live request.
2. Reuse the authenticated session.
3. Retry authentication once only when a recognized authentication/session
   error occurs.
4. Never classify every JSON-decoding failure as an expired session.
5. Translate dependency and HTTP exceptions into short, redacted messages.
6. Never return raw HTML error pages or dependency exception strings to the
   MCP client.

All server logging must use Python logging directed to stderr. Never call
`print()` because stdout belongs to the MCP stdio protocol. Log operation name,
duration, course alias, result count, and high-level failure category only. Do
not log credentials, course IDs, post numbers, titles, bodies, search queries,
or raw responses.

## MCP Tool Contracts

Use hyphenated names to match the existing tool catalog. Keep Piazza tools
separate from `list-courses`, whose existing meaning is local course
directories.

All four tools should declare:

```python
types.ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
```

`openWorldHint=True` communicates that the tools read an external service.

### `list-piazza-courses`

Arguments: none.

Behavior:

- Retrieve the authenticated user's classes.
- Intersect them with the configured allowlist.
- Return only course metadata needed to select another Piazza tool.
- Return a clear configuration or authentication error if no configured course
  is accessible.

Suggested response:

```json
{
  "source": "piazza",
  "fetched_at": "2026-08-19T20:00:00Z",
  "stale": false,
  "returned_count": 1,
  "courses": [
    {
      "course_id": "abc123",
      "name": "CMSC132",
      "course_number": "CMSC 132",
      "term": "Fall 2026",
      "is_ta": false
    }
  ]
}
```

### `list-piazza-posts`

Arguments:

```text
course_id: required configured course ID
limit: optional integer, default 10, maximum 25
offset: optional integer, default 0, maximum 500
```

Return feed summaries only. Do not retrieve each full thread. Sort using the
order returned by Piazza unless live inspection proves that a stable timestamp
sort is needed.

### `get-piazza-post`

Arguments:

```text
course_id: required configured course ID
post_number: required positive integer
```

Return one normalized thread, including bounded answers and follow-ups. Include
a normal Piazza web URL so the user can verify the authoritative thread in the
browser.

### `search-piazza-posts`

Arguments:

```text
course_id: required configured course ID
query: required non-empty string, maximum 200 characters
max_results: optional integer, default 10, maximum 25
```

Use Piazza's server-side feed search and normalize the bounded summaries it
returns. Do not implement search by downloading every thread.

Each tool should have an explicit JSON output schema with
`additionalProperties: false`, fixed enums, maximum array sizes, and required
freshness/truncation metadata. Return schema-validated `structuredContent` plus
equivalent JSON `TextContent` for clients that do not consume structured tool
output, matching the existing course-search and calendar behavior.

## Development-Only Shape Inspection

Raw Piazza response shapes should be inspected before finalizing the
normalizer, but real course content must not become a fixture or log artifact.

Add `scripts/inspect_piazza_shapes.py` after Phase 0. It may report only:

- Top-level key names and Python value types.
- Counts of post kinds and child kinds.
- Counts of fields present or absent.
- History lengths.
- Child nesting depths.
- HTML/plain-text occurrence counts.
- Coarse timestamp shapes.
- Aggregate response byte ranges.

It must not print emails, names, course IDs, post numbers, titles, bodies,
folders, links, raw timestamps, cookies, or raw responses. Use the aggregate
results to construct synthetic fixtures containing invented course content.

## Implementation Phases

### Phase 0: Select the access route

- Request supported integration guidance or permission from Piazza.
- Confirm whether the account supports direct email/password authentication.
- Choose approved API, supported email ingestion, or explicitly accepted
  unofficial access.
- Record the decision and known limitations in this plan and the README.

Verification: no live internal endpoint is called until this decision is
recorded.

### Phase 1: Transport spike and response-shape evidence

- Add the selected transport in an isolated development branch/change.
- Prove bounded authentication and one read-only course-list operation.
- Enforce request timeouts before making live calls.
- Verify which exceptions represent bad credentials, expired sessions,
  timeouts, malformed responses, and unavailable courses.
- Run the aggregate-only shape inspector against one representative course.
- Confirm the behavior of feed ordering, search results, answers, follow-ups,
  anonymity, and HTML fields.

Verification: a written/redacted shape summary exists; no real response is
committed.

### Phase 2: Configuration, models, and normalization

- Implement lazy `PiazzaConfig` validation.
- Add normalized frozen dataclasses.
- Add bounded HTML-to-text normalization.
- Add explicit handling for all observed question, note, answer, follow-up,
  feedback, missing-history, and nested-child shapes.
- Create wholly synthetic test fixtures based on the aggregate evidence.

Verification: normalizer and configuration tests cover valid, malformed,
missing, oversized, anonymous, and deeply nested inputs.

### Phase 3: Client and service

- Implement the async client protocol around the synchronous transport.
- Add timeout-enabled requests, a session lock, lazy authentication, and one
  recognized-authentication retry.
- Add course allowlist enforcement before any course-scoped network request.
- Implement the four service operations.
- Add 60-second in-memory caching and explicit stale metadata.
- Bound all arguments and normalized outputs independently of MCP schemas.

Verification: fake-client tests prove request counts, retry behavior,
allowlisting, cache behavior, truncation, and redacted errors.

### Phase 4: MCP schemas, tools, and dispatch

- Add four tool definitions and their read-only/open-world annotations.
- Add strict input and output schemas.
- Export the tools through `mcp_tools/__init__.py` and `build_tools()`.
- Add lazy service dispatch branches in `server.py`.
- Return structured content and JSON text fallback consistently.

Verification: tool-catalog and server-dispatch tests pass without Piazza
configuration or network access.

### Phase 5: Live validation and documentation

- Run one bounded call for each tool against the configured account.
- Compare returned summaries and one full thread with the Piazza UI.
- Confirm anonymous content remains anonymous.
- Confirm logs and errors contain no private values.
- Confirm existing filesystem and calendar tools still work when Piazza is
  unconfigured or unavailable.
- Document setup, limits, unofficial-API status, troubleshooting, and secret
  handling in the README.

Verification: the complete test suite, compile check, MCP Inspector smoke test,
and manual privacy review pass.

## Test Matrix

At minimum, cover:

- Missing email, password, or course map.
- Malformed course JSON and invalid key/value types.
- Course ID outside the allowlist.
- Configured course missing from the authenticated account.
- Boolean, negative, zero, excessive, and wrong-type numeric inputs.
- Empty, whitespace-only, and oversized search queries.
- Initial authentication failure.
- Recognized session expiry followed by successful reauthentication.
- Failed reauthentication and retry limited to one.
- Timeout, connection failure, invalid JSON, and upstream error response.
- Empty feed and empty search results.
- Empty full-thread response treated as an error.
- Missing history and multiple revisions.
- Text stored in `subject`, `content`, and history records.
- Student answer, instructor answer, follow-up, feedback, and nested replies.
- Anonymous content and absence of internal author identifiers.
- HTML, scripts, styles, links, entities, and embedded LaTeX.
- Per-field, per-array, nesting, and total-response truncation.
- Cache hit, expiry, stale fallback, and separation by course/query/post.
- No network call for an invalid or disallowed request.
- No Piazza initialization while using unrelated MCP tools.
- Strict output-schema validation and JSON text fallback.
- No secrets or private content in errors and captured logs.

## Definition of Done

The first Piazza release is complete when:

1. The access-route decision is documented.
2. Only the four read-only tools are exposed.
3. Every course-scoped request is restricted to the configured allowlist.
4. No operation uses `iter_all_posts()` or downloads all full threads.
5. All network requests have timeouts and bounded retry behavior.
6. The MCP event loop is not blocked by the synchronous dependency.
7. Raw Piazza dictionaries never cross the client/service boundary into tool
   responses.
8. User-generated content is normalized, bounded, and marked untrusted.
9. Anonymous identities remain anonymous and internal user IDs are omitted.
10. Credentials, cookies, queries, and course content never enter stdout,
    errors, committed fixtures, or logs.
11. Existing filesystem and calendar tools work without Piazza configuration.
12. Unit and dispatch tests pass without live credentials.
13. A bounded opt-in live smoke test matches the Piazza UI.

## Explicitly Deferred

- Creating posts or notes.
- Answering or editing questions.
- Posting follow-ups or feedback.
- Marking threads resolved, pinned, followed, or read.
- Instructor statistics, rosters, enrollment, and moderation.
- Downloading attachments or course resources.
- Persisting or indexing Piazza content locally.
- Cross-course semantic search or embeddings.
- Automatic joins between Piazza courses and local course directories beyond
  the explicit configured display-name mapping.
- Browser automation, cookie extraction, SSO-token reuse, or authentication
  workarounds.

These capabilities require separate evidence, privacy review, and—especially
for writes—explicit user-confirmation semantics. They should not be smuggled
into the read-only milestone.
