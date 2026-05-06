# Sumo Logic CLI — Analysis and SOP

## Phase 1: Architecture Analysis

### Backend Engine

Sumo Logic exposes a REST Search Job API at `https://api.<deployment>.sumologic.com/api/v1/`.
Authentication is HTTP Basic Auth using Access ID + Access Key.

The Search Job API is an **asynchronous polling** workflow:
1. POST `/search/jobs` — create a job, get back `{ id }`
2. GET `/search/jobs/{id}` — poll status until `state == "DONE GATHERING RESULTS"`
3. GET `/search/jobs/{id}/messages` — fetch raw log messages (paginated)
4. GET `/search/jobs/{id}/records` — fetch aggregate records for queries with `| count` etc.
5. DELETE `/search/jobs/{id}` — clean up

### Data Model

| Resource | Description |
|----------|-------------|
| Search Job | Async query job: query string + time range |
| Status | `state`, `messageCount`, `recordCount`, `histogramBuckets` |
| Message | Raw log event: `{ map: { _raw, _messagetime, ... } }` |
| Record | Aggregate result row: `{ map: { _count, field1, ... } }` |
| Field | Schema descriptor: `{ name, fieldType, keyField }` |

### Sumo Logic Deployments

Endpoint format: `https://api.<deployment>.sumologic.com/api/v1/`

Common deployments: `us1`, `us2`, `eu`, `au`, `in`, `jp`, `ca`, `fed`

### Session State

Because each search is stateless (create → poll → fetch → delete), the CLI manages:
- **Session config**: credentials + endpoint (in-memory or env vars)
- **Job state**: current job id, status, result cache
- **History**: recent queries (in local session file)

No project file concept — Sumo Logic is a SaaS API. The "project" here is the
saved query + time range for repeat searches.

## Phase 2: CLI Architecture

### Command Groups

1. **auth** — Configure credentials (access-id, access-key, endpoint)
2. **search** — Execute log searches (main operation)
3. **job** — Manage search jobs (status, messages, records, delete)
4. **session** — Session management (history, saved queries, status)

### Interaction Models

- **One-shot**: `cli-anything-sumologic search run "error" --from -1h --to now`
- **REPL**: `cli-anything-sumologic` → interactive session

### Output Format

- Human: pretty tables for records, plain text for messages
- Machine: `--json` flag for all commands

### State Storage

Session state stored in `~/.cli-anything-sumologic/session.json`:
```json
{
  "endpoint": "https://api.us2.sumologic.com/api/v1",
  "access_id": "...",
  "current_job_id": null,
  "query_history": [...],
  "saved_queries": {...}
}
```

## Phase 3: Implementation Plan

### Core Modules

- `core/session.py` — credentials, session state, locking
- `core/search.py` — search job creation, polling, result fetching
- `core/formatter.py` — table/JSON output formatting

### Utils

- `utils/sumologic_backend.py` — HTTP client wrapping the Sumo Logic REST API
- `utils/repl_skin.py` — unified REPL skin (copied from plugin)

### CLI Entry Point

- `sumologic_cli.py` — Click CLI with REPL, `invoke_without_command=True`

## Notes

- Sumo Logic is the backend — the CLI calls the real API, not a simulation
- Credentials via env vars: `SUMO_ACCESS_ID`, `SUMO_ACCESS_KEY`, `SUMO_ENDPOINT`
- Polling loop with configurable timeout (default 5 minutes)
- Large result sets use pagination (offset + limit)
