# Canvas Calendar Integration: High-Level Plan Without a PAT

## Decision

Build the first integration around the user's private Canvas iCalendar feed and the course files already available locally.

This changes the product goal from “a complete Canvas client” to “a deadline-aware local course assistant.” The application should be able to answer questions such as:

- What assignments and course events are coming up this week?
- Which deadlines belong to CMSC 430?
- What local notes or files are relevant to this upcoming assignment?
- Where is the Canvas page linked from this calendar item?

It should not claim that it can determine submission status, missing work, grades, rubrics, modules, or announcements. Those require authenticated Canvas APIs or manually supplied content.

The reason for this direction is practical: manual personal access-token creation is currently unavailable in the user's Canvas account. We do not yet know whether that is a university-wide policy, a role-specific restriction, or an account configuration issue. Canvas OAuth is still a valid future route, but it requires an institution-issued and enabled developer key, so it is not an immediate self-service solution.

## Why the Calendar Feed Is the Best Available Alternative

Canvas officially exposes a Calendar Feed from **Global Navigation → Calendar → Calendar Feed**. The feed contains assignments and events from all of the user's Canvas calendars and can be consumed directly as iCalendar data without automating the browser or reusing an authenticated Canvas session.

This is preferable to the other workarounds considered:

| Alternative | Decision | Reason |
| --- | --- | --- |
| Canvas iCalendar feed | Build now | Supported by Canvas, read-only, useful for deadline questions, and does not require a PAT |
| Manually downloaded course files | Use as a complement | Preserves rich assignment/course context, but requires user action |
| Institution-approved Canvas OAuth | Defer | Best long-term capability, but requires UMD approval and a developer key |
| Google/Outlook calendar as an intermediary | Avoid initially | Adds another synchronization layer when the application can read the Canvas feed directly |
| Scraping Canvas after SSO login | Do not pursue | Brittle, hard to test, and likely to mishandle sessions or MFA |
| Browser cookies or mobile-app tokens | Do not pursue | Unsupported credential reuse with unnecessary security risk |
| Email notification parsing | Do not pursue initially | Incomplete, user-configurable, and less authoritative than the calendar feed |

### Known upstream limits

The official Canvas guide documents several important limitations:

- The feed includes events and assignments, but not Canvas To Do items.
- It is bounded to 366 days in the future and 30 days in the past.
- It contains at most 1,000 items.
- It covers all Canvas calendars rather than serving as an authoritative course roster.
- Canvas advises re-importing the feed after enrolling in a new course.

The application therefore must not use the feed for historical reporting or treat the absence of an item as proof that no work exists.

## Proposed Architecture

Keep the MCP protocol boundary thin and put fetching, parsing, and filtering in services.

```text
MCP handlers
├── CourseService ─────── FileService ───────── local course folders
└── CalendarService
    ├── CalendarFeedClient ──────────────────── private Canvas iCalendar URL
    ├── ICalendarParser ─────────────────────── normalized CalendarItem models
    └── CourseContextMatcher ────────────────── optional local-course matching
```

Suggested package layout:

```text
src/course_mcp/
├── config/
│   └── config.py
├── models/
│   └── calendar_item.py
├── services/
│   ├── calendar_feed_client.py
│   ├── icalendar_parser.py
│   ├── calendar_service.py
│   └── course_context_matcher.py       # add only when matching is implemented
├── mcp_schemas/
│   └── calendar.py
└── server.py
```

The transport and parser should be separate. That lets unit tests parse synthetic `.ics` fixtures without making network calls and lets the same service support both a live subscription URL and a downloaded snapshot.

## Data Flow

```text
Private feed URL
      │
      ▼
validate URL and fetch over HTTPS
      │
      ▼
parse RFC 5545 calendar data
      │
      ▼
normalize dates, identifiers, links, and optional course hints
      │
      ▼
filter and sort within the requested date range
      │
      ├── return upcoming items
      └── optionally match them to local course files
```

## Configuration and Secret Handling

Support two mutually exclusive inputs:

- `CANVAS_ICAL_URL`: preferred for a live, updating subscription.
- `CANVAS_ICAL_PATH`: a local `.ics` snapshot for tests, offline use, or users unwilling to store the URL.

The feed URL must be treated as a bearer secret: anyone who obtains it may be able to read the calendar it exposes. Consequently:

- Never return the feed URL from an MCP tool.
- Never place it in logs, exceptions, fixtures, telemetry, or screenshots.
- Redact URL paths and query strings in client errors.
- Store it in the operating-system keychain when practical, or inject it through an environment variable.
- If a local environment file is used, keep it out of version control and restrict its permissions.
- Never send Canvas cookies, an SSO session, or unrelated credentials with the request.

The client should normalize a `webcal://` link to `https://`, then require HTTPS. During the validation phase, determine the actual hostname used by UMD's feed and restrict requests and redirects to that expected host or a narrowly configured allowlist. This prevents a configuration mistake from turning the client into a general URL fetcher.

## Normalized Model

Use a small model that reflects what iCalendar can reliably represent:

```text
CalendarItem
├── uid: str
├── title: str
├── starts_at: timezone-aware datetime or date
├── ends_at: timezone-aware datetime or date | None
├── all_day: bool
├── description: str | None
├── location: str | None
├── item_url: str | None
├── course_hint: str | None
├── item_kind: "assignment" | "event" | "unknown"
├── last_modified: datetime | None
└── recurrence_id: str | None
```

Preserve unknown values rather than inventing meaning. For example, if the feed does not distinguish assignments from events reliably, return `unknown` instead of guessing from the title alone.

Use an RFC 5545-aware library such as Python's `icalendar` package. A hand-written parser is not appropriate because folded lines, escaped text, time zones, date-only values, and recurrence rules have subtle semantics.

## Initial MCP Tool

Start with one user-facing tool instead of recreating the original REST API tool surface.

### `get-upcoming-work`

Suggested arguments:

```text
start_date: ISO date, optional, defaults to today
end_date: ISO date, optional, defaults to seven days after start_date
course: string, optional
query: string, optional
include_events: bool, optional, defaults to true
max_results: integer, optional, bounded, defaults to 50
```

Suggested response metadata:

```text
source: "canvas_ical" | "local_ical_snapshot"
fetched_at: timestamp
stale: bool
limitations:
  - completion_status_unavailable
  - canvas_todo_items_unavailable
items: CalendarItem[]
```

Sort items chronologically. Return the event's own Canvas URL when the feed provides one, but never confuse that URL with the private feed URL.

Do not initially expose `list-canvas-courses`. The iCalendar feed is not an authoritative course-enrollment endpoint. Continue using the existing local `list-courses` behavior, and add calendar-derived course hints only after inspecting the fields present in a real UMD feed.

## Course Matching and Local Context

The feed becomes more valuable when calendar items can be connected to files already stored for a course. Implement this only after examining a redacted sample because Canvas installations may encode course information differently.

The matching sequence should be conservative:

1. Inspect `SUMMARY`, `DESCRIPTION`, `CATEGORIES`, `LOCATION`, and event `URL` fields in the UMD sample.
2. Prefer exact course-code matches against known local courses, such as `CMSC430` or `CMSC 430`.
3. Allow a small user-maintained mapping only when feed labels and folder names differ.
4. Return `course_hint: null` when confidence is low.
5. Never silently assign an ambiguous item to a course.

Once reliable matching exists, a later tool can combine the schedule item with local search results—for example, finding notes whose filename or contents match an assignment title. It should still direct the user to Canvas for current submission state and official instructions.

For richer context without OAuth, document a simple manual workflow: save assignment PDFs, HTML exports, or downloaded course files under the corresponding local course directory. The existing file services can then search them; the calendar feed supplies timing and links.

## Fetching, Freshness, and Failure Behavior

`CalendarFeedClient` should use the project's async HTTP approach and enforce:

- A short connection and response timeout.
- A conservative maximum response size, initially 5 MB.
- A narrowly validated hostname and same-origin redirects.
- No cookies and no bearer-authentication header.
- Tolerant content-type handling because calendar servers may use either `text/calendar` or a generic text type.

Use a small in-memory cache, initially five minutes. If the server provides `ETag` or `Last-Modified`, use conditional requests. On a temporary fetch failure, the service may return the last successful in-memory result with `stale: true` and its fetch timestamp. If no cached result exists, return a clear, redacted error.

Do not persist the raw feed in the first version. Avoiding persistence reduces the chance of leaking course titles and deadlines. Snapshot mode is explicit: the user supplies a local file and is responsible for refreshing it.

Calendar failures must not break the existing local-course tools.

## Implementation Phases

### Phase 0: Validate the UMD feed

Before writing production code:

1. In Canvas, open **Calendar → Calendar Feed**.
2. Copy the subscription URL or download the `.ics` file.
3. Keep the URL and sample outside the repository, preferably in a temporary protected location.
4. Inspect only the field names, hostname, event shapes, time zones, and course-label conventions needed for implementation.
5. Verify a representative week against the Canvas Calendar UI.
6. Confirm whether recurring events, canceled events, all-day dates, and direct Canvas item URLs appear.

This phase resolves the largest implementation unknowns without committing private calendar data.

### Phase 1: Secure feed client and configuration

- Add mutually exclusive URL/path configuration.
- Validate and redact the live URL.
- Implement bounded HTTPS fetching, conditional requests, and in-memory caching.
- Add explicit errors for missing configuration, invalid host, timeout, oversized response, and malformed response.

### Phase 2: Parser and normalized models

- Add the `icalendar` dependency.
- Parse `VEVENT` components into `CalendarItem` models.
- Normalize timed and date-only events without losing all-day semantics.
- Preserve `UID` and `RECURRENCE-ID` for stable identity and deduplication.
- Sanitize descriptions for bounded MCP output.
- Add recurrence support based on what is actually observed in the UMD feed.

### Phase 3: Calendar service and MCP tool

- Filter by date range, query, optional course hint, and event inclusion.
- Sort and bound results.
- Expose `get-upcoming-work` through a thin handler in `server.py`.
- Include freshness and capability limitations in the response.

### Phase 4: Join calendar items to local course context

- Implement exact course-code matching first.
- Add a minimal explicit mapping only if sample data requires it.
- Search local course files for a selected calendar item's title or identifiers.
- Keep unmatched and ambiguous items visible.

### Phase 5: Reassess after real use

Measure which unanswered questions matter. Likely candidates are assignment details, submission status, announcements, and modules. Use that evidence when requesting an institution-approved OAuth integration rather than requesting broad Canvas access speculatively.

### Deferred Phase: Institution-approved OAuth

If UMD approves a Canvas developer key, add OAuth authorization and a REST-backed `CanvasClient` as a separate adapter. The richer service can then provide course enrollment, assignments, modules, announcements, and submission status according to the approved scopes.

The calendar-backed interface should remain useful and testable independently. Do not design Phase 1 around an assumption that OAuth approval will arrive.

## Test Strategy

### Parser unit tests

Use synthetic fixtures only; never commit a real feed.

- Timed events with UTC and named time zones.
- All-day events using date values.
- Folded lines and escaped commas, semicolons, and newlines.
- Missing optional fields.
- Duplicate `UID` values and updated instances.
- `RECURRENCE-ID`, `RRULE`, `RDATE`, and `EXDATE` if observed during validation.
- Malformed and unexpectedly large calendars.

### Client unit tests

- `webcal://` normalization and HTTPS enforcement.
- Host allowlisting and redirect rejection.
- Timeout and HTTP-error handling.
- Response-size bounds.
- `ETag`/`Last-Modified` conditional requests.
- Stale-cache fallback.
- Feed-URL redaction from every error path.

### Service and MCP tests

- Inclusive date-range boundaries.
- Chronological sorting.
- Course and text filtering.
- Stable deduplication.
- Bounded descriptions and result counts.
- Explicit `stale` and limitation metadata.
- No feed URL in serialized results.
- Existing file tools still work with calendar configuration absent or unavailable.

### Opt-in integration test

Provide a locally run integration test that reads a user-supplied URL, asserts that the response is parseable, and reports only aggregate counts and field availability. It must never print the URL or raw calendar content.

## Definition of Done

The first integration is complete when:

- The user can ask what is due in the next seven days and get results that match a manually checked week in the Canvas Calendar.
- Dates and times are correct for both timed and all-day items.
- Results can be filtered by a reliably derived course hint when one is available.
- Canvas item links are returned when present.
- Changed events appear after the cache window or a conditional refresh.
- Temporary network failures are clearly marked as stale rather than silently presented as current.
- The private feed URL cannot appear in tool output, logs, exceptions, or committed fixtures.
- The application clearly states that submission status, To Do items, grades, modules, rubrics, and announcements are unavailable.
- All pre-existing local course/file behavior continues to work without calendar access.

## Explicit Non-Goals for the First Version

- Creating, editing, or submitting Canvas assignments.
- Claiming that an assignment is submitted, missing, or complete.
- Reading grades, rubrics, modules, announcements, or discussions.
- Treating calendar data as a complete course roster or archive.
- Scraping Canvas pages or automating Duo/SSO.
- Storing or redistributing the raw private feed.

## Research Basis

- [Canvas: view and subscribe to the Calendar iCal feed](https://community.instructure.com/en/kb/articles/662804-unknown) — feed contents, setup path, 366-day/30-day/1,000-item limits, exclusion of To Do items, and new-enrollment caveat.
- [Canvas: using the Calendar](https://community.instructure.com/en/kb/articles/662787-how-do-i-use-the-calendar) — how assignments and events from enrolled courses appear in the Canvas Calendar.
- [UMD: Use the Calendar in ELMS-Canvas](https://itsupport.umd.edu/itsupport/?id=kb_article_view&sysparm_article=KB0010305) — UMD-specific Calendar guidance.
- [RFC 5545: Internet Calendaring and Scheduling Core Object Specification](https://www.rfc-editor.org/info/rfc5545/) — the iCalendar data model and event fields.
- [Python `icalendar` documentation](https://icalendar.readthedocs.io/en/stable/) — RFC-aware parsing and generation library.
- [Canvas OAuth2 documentation](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth) and [Canvas developer-key documentation](https://developerdocs.instructure.com/services/canvas/oauth2/file.developer_keys) — requirements for a future institution-approved OAuth integration.
- [UMD: Learning Technology Tool Integration Process](https://itsupport.umd.edu/itsupport/?id=kb_article_view&sysparm_article=KB0015030) — institutional review and approval path for learning-technology integrations.
