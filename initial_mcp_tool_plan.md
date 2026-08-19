# Initial Canvas MCP Tool Implementation Plan

## Outcome

Implement one read-only MCP tool, `get-upcoming-work`, that reads the user's private Canvas iCalendar feed and returns a bounded, structured list of upcoming assignments and calendar events.

The first release is successful when this question works reliably:

> What work is coming up in the next seven days?

This tool will provide dates, titles, optional course hints, and direct Canvas item links when present. It will not report completion, submission, missing-work, grade, rubric, module, announcement, or Canvas To Do data.

## Preconditions and Assumptions

Before implementation, obtain either:

- A private Canvas Calendar Feed URL for live use; or
- A downloaded `.ics` file for local validation and testing.

The real feed and its URL must remain outside the repository. Inspect a private sample to confirm:

- The feed hostname.
- Which fields identify the course.
- Whether assignment and non-assignment events can be distinguished reliably.
- Whether event `URL` values point to usable Canvas pages.
- Which time zones and recurrence fields occur.

Until that inspection is complete, course filtering and assignment/event classification are provisional. The core tool does not depend on either feature.

## Version 1 Tool Contract

### Tool name

`get-upcoming-work`

### Input

```json
{
  "start_date": "2026-08-19",
  "end_date": "2026-08-25",
  "query": "project",
  "max_results": 50
}
```

| Field | Required | Default | Validation |
| --- | --- | --- | --- |
| `start_date` | No | Today in the configured calendar time zone | ISO `YYYY-MM-DD` |
| `end_date` | No | Six days after `start_date` | ISO `YYYY-MM-DD`; on or after `start_date`; maximum 366-day range |
| `query` | No | No text filter | Non-empty after trimming when supplied; case-insensitive literal match |
| `max_results` | No | `50` | Integer from `1` through `100` |

Both date boundaries are inclusive. The default therefore represents exactly seven calendar dates, including today.

Do not include `course` or `include_events` in the first schema unless sample validation proves that UMD's feed exposes stable course and item-type fields. Adding an unreliable filter would create false negatives, which is worse than returning a few extra events.

### Output

```json
{
  "source": "canvas_ical",
  "fetched_at": "2026-08-19T17:30:00Z",
  "stale": false,
  "returned_count": 1,
  "truncated": false,
  "limitations": [
    "completion_status_unavailable",
    "canvas_todo_items_unavailable"
  ],
  "items": [
    {
      "uid": "opaque-event-id",
      "title": "Project 1",
      "starts_at": "2026-08-21T23:59:00-04:00",
      "ends_at": null,
      "all_day": false,
      "description": null,
      "location": null,
      "item_url": "https://umd.instructure.com/courses/...",
      "course_hint": "CMSC430",
      "item_kind": "assignment"
    }
  ]
}
```

Contract decisions:

- `starts_at` and `ends_at` are ISO 8601 strings. Date-only events use `YYYY-MM-DD` and set `all_day` to `true`.
- `item_kind` is `assignment`, `event`, or `unknown`; uncertain items remain `unknown`.
- `course_hint` is nullable and must not be guessed when the feed is ambiguous.
- Descriptions are plain text and bounded in length.
- `returned_count` describes the returned array. `truncated` indicates that more matching items existed than `max_results` allowed.
- The feed URL is never part of the response.

## Request Semantics

The service should:

1. Load and parse the configured feed.
2. Normalize each `VEVENT` into a `CalendarItem`.
3. Include an item when its time interval overlaps the requested inclusive date range.
4. Apply `query`, when present, to the title, description, location, and reliable course hint.
5. Deduplicate using `UID` plus `RECURRENCE-ID` when present.
6. Sort by start time, then title, then UID for deterministic output.
7. Apply `max_results` only after filtering and sorting.

All-day dates must retain date semantics. Do not turn an all-day due date into midnight UTC, because that can shift it to the previous calendar date for the user.

## Repository Changes

### 1. Dependencies

Update `pyproject.toml` and the lockfile with direct dependencies for:

- `icalendar` for RFC 5545 parsing.
- `httpx` for asynchronous, bounded HTTPS requests.

Let the package manager resolve compatible versions instead of coding against transitive dependencies already installed by MCP.

### 2. Configuration

Extend `src/course_mcp/config/config.py` with an optional calendar configuration object containing:

- `CANVAS_ICAL_URL` or `CANVAS_ICAL_PATH`, but not both.
- `CALENDAR_TIMEZONE`, defaulting to `America/New_York` for this UMD-focused application unless feed validation establishes a better source of truth.

Load and validate calendar configuration lazily. `ROOT_DIR` remains required for the existing course tools, but absent calendar configuration must not prevent the MCP server from starting or break any current tool.

Validation rules:

- Convert `webcal://` to `https://` internally.
- Require HTTPS for a live feed.
- Restrict the live source to the hostname confirmed during sample validation.
- Resolve a snapshot path and require a regular file no larger than 5 MB.
- Raise an actionable, redacted configuration error when neither source is configured and the tool is called.

### 3. Models

Add `src/course_mcp/models/calendar_item.py` with immutable dataclasses for:

- `CalendarItem`: normalized event data returned by the parser.
- `CalendarSnapshot`: parsed items plus `source`, `fetched_at`, and `stale` metadata.

Keep serialization out of the model. The calendar service should produce the final dictionary that matches the MCP output schema.

### 4. iCalendar parser

Add `src/course_mcp/services/icalendar_parser.py`.

Responsibilities:

- Parse calendar bytes using `icalendar`.
- Walk `VEVENT` components only.
- Decode `UID`, `SUMMARY`, `DTSTART`, `DTEND`, `DESCRIPTION`, `LOCATION`, `URL`, `LAST-MODIFIED`, and `RECURRENCE-ID` when present.
- Preserve date-only and timezone-aware date-time values.
- Reject events without a usable `UID`, title, or start value, or skip them with an internal count; decide which behavior matches the actual sample.
- Convert rich descriptions to bounded plain text.
- Extract `course_hint` and `item_kind` only from rules verified against the UMD sample.

Do not implement general recurrence expansion speculatively. First determine whether the Canvas feed already emits individual instances. If expansion is required, add it with fixtures representing the observed recurrence patterns.

### 5. Feed loader and cache

Add `src/course_mcp/services/calendar_feed_client.py`.

For a live source:

- Fetch asynchronously over HTTPS without cookies or authorization headers.
- Use short connection and response timeouts.
- Reject cross-host redirects.
- Enforce the 5 MB limit while streaming, not only through `Content-Length`.
- Accept `text/calendar` and known generic text content types.
- Redact the URL path and query string from every error.

For a snapshot source:

- Read the configured file with the same size limit.
- Mark the response source as `local_ical_snapshot`.
- Set `fetched_at` to the time the snapshot was read, not an invented server-update time.

Maintain a five-minute in-memory cache. Store parsed items, not the private URL. When available, retain `ETag` and `Last-Modified` for conditional requests. A failed refresh may return the last successful snapshot with `stale: true`; a first-load failure should return a redacted error.

### 6. Calendar service

Add `src/course_mcp/services/calendar_service.py`.

Responsibilities:

- Receive the feed client and parser through constructor injection.
- Validate and parse tool arguments.
- Calculate the inclusive date window in the configured time zone.
- Filter, deduplicate, sort, and truncate normalized items.
- Serialize the exact response contract.
- Attach the two initial capability limitations.

Keep network and iCalendar parsing details out of this service so its filtering behavior can be tested with in-memory `CalendarItem` values.

### 7. MCP schemas and catalog

Add:

- `src/course_mcp/mcp_schemas/calendar.py`
- `src/course_mcp/mcp_tools/calendar.py`

Export the calendar output schema through `mcp_schemas/__init__.py`. Combine the course and calendar tool definitions in `mcp_tools/__init__.py` so `server.py` can obtain one complete catalog.

The output schema should:

- Require all top-level metadata fields.
- Make nullable item fields explicit.
- Restrict `item_kind` and `source` to documented enum values.
- Set `additionalProperties` to `false` at every object boundary.
- Bound array and string sizes where practical.

### 8. Thin server handler

Update `src/course_mcp/server.py` to:

- Include `get-upcoming-work` in `handle_list_tools()`.
- Lazily obtain the configured `CalendarService` only when this tool is called.
- Await `calendar_service.get_upcoming_work(...)`.
- Pass supplied values and defaults without performing domain work in the handler.
- Return the service dictionary so MCP can provide schema-validated `structuredContent` and compatibility `TextContent` in the same way as the current search tools.

Do not initialize or fetch the calendar at module import time.

### 9. Documentation

Update `README.md` with:

- How to obtain the Canvas Calendar Feed.
- Configuration examples that use placeholders rather than a real URL.
- A warning that the URL is private.
- The local snapshot alternative.
- Tool inputs, examples, and limitations.
- A reminder to restart the MCP client after the tool catalog changes.

## Test Plan

### Parser tests

Create only synthetic `.ics` fixtures covering:

- UTC and named-time-zone events.
- All-day dates.
- Missing optional fields.
- Escaped and folded text.
- Duplicate UIDs and recurrence IDs.
- Direct Canvas item URLs.
- Malformed calendar content.
- Course/type extraction rules confirmed during feed validation.

### Client tests

Use `httpx.MockTransport`; never call Canvas from the normal test suite.

- HTTPS and host validation.
- `webcal://` normalization.
- Same-host and cross-host redirects.
- Timeouts and non-success status codes.
- Oversized headers and streamed bodies.
- URL redaction.
- Five-minute cache hits.
- Conditional responses when supported.
- Stale-cache fallback.
- Local snapshot loading.

### Service tests

- Default seven-day window.
- Explicit inclusive boundaries.
- Invalid or reversed dates.
- Maximum date-range rejection.
- Case-insensitive literal query filtering.
- Interval overlap for timed events.
- Date preservation for all-day events.
- Deterministic sorting and deduplication.
- Result truncation and metadata.
- Null course hints and unknown item kinds.

### MCP tests

- The catalog includes `get-upcoming-work` and its schemas.
- The handler passes explicit arguments and documented defaults to a fake async service.
- Structured output validates successfully.
- Invalid input and service errors become MCP errors.
- Missing calendar configuration does not affect existing tools.
- No error or result contains the configured feed URL.

### Manual validation

With the private UMD feed configured locally:

1. Compare the tool with a seven-day view in Canvas Calendar.
2. Check at least one timed deadline and one all-day event.
3. Change or create a harmless personal calendar event, then confirm it appears after the cache window.
4. Temporarily make the feed unavailable and verify stale/error behavior.
5. Search all captured output for any portion of the private feed identifier.

## Implementation Sequence

1. **Validate a private sample** → record only structural observations, never real content.
2. **Add parser and models** → parser unit tests pass with synthetic fixtures.
3. **Add feed configuration and client** → client tests prove URL redaction, bounds, and cache behavior.
4. **Add calendar service** → service tests prove date, filtering, ordering, and truncation semantics.
5. **Expose the MCP contract** → schema and registered-handler tests pass.
6. **Document and manually verify** → results match Canvas for a representative week.
7. **Run the full suite** → existing course and file tools remain unchanged.

## Definition of Done

- `get-upcoming-work` returns schema-valid structured output for URL and snapshot sources.
- The default call returns exactly the current seven-day calendar window.
- Timed and all-day dates match Canvas.
- Results are deterministic, bounded, and honestly classified.
- Live-feed failures use a marked stale cache when possible.
- The feed URL is absent from output, errors, tests, fixtures, and logs.
- Missing calendar configuration produces an actionable tool error without affecting server startup.
- Existing tests pass, and new parser, client, service, schema, and MCP tests cover the behavior above.
- The README explains configuration, security, usage, and limitations.

## Deferred Work

- Searching local files for assignment context.
- Course filtering until a stable UMD course label is verified.
- Hiding non-assignment events until classification is reliable.
- Full recurrence support beyond patterns actually found in the feed.
- Persistent caching or historical calendar storage.
- Canvas submission, grade, module, announcement, or To Do data.
- OAuth and REST API integration.
