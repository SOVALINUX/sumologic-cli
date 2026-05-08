---
name: "cli-anything-sumologic"
description: "CLI harness for the Sumo Logic Search Job API — run log searches, manage jobs, save queries, and get token-efficient TOON or full JSON output for agent consumption"
---

# cli-anything-sumologic

CLI harness for the Sumo Logic Search Job API. Enables AI agents and scripts to
execute log searches, fetch results, and manage search jobs without a browser.

## Prerequisites

- Python 3.10+
- A Sumo Logic account with API Access ID and Access Key
- No additional software required — communicates via REST API over HTTPS

## Installation

```bash
cd agent-harness
pip install -e .
```

## Configuration

Set credentials as environment variables (recommended for agents):

```bash
export SUMO_ENDPOINT="https://api.us2.sumologic.com/api/v1"
export SUMO_ACCESS_ID="your-access-id"
export SUMO_ACCESS_KEY="your-access-key"
```

Or configure interactively:

```bash
cli-anything-sumologic auth configure
```

Credentials are saved to `~/.cli-anything-sumologic/session.json`.

## Usage

```bash
# Interactive REPL (default — no subcommand; always text mode)
cli-anything-sumologic

# One-shot commands — TOON output by default (Token-Oriented Object Notation)
cli-anything-sumologic <command-group> <command> [OPTIONS]

# Full indented JSON, no truncation
cli-anything-sumologic --format json <command-group> <command> [OPTIONS]

# Human-readable text
cli-anything-sumologic --format text <command-group> <command> [OPTIONS]
```

## Output Formats

| `--format` | Description |
|------------|-------------|
| `toon` *(default)* | Token-Oriented Object Notation. YAML-like key-value pairs for objects; tabular CSV rows for uniform arrays (field names declared once, not per row). Field truncation applied before encoding. Best for agent consumption. |
| `json` | Full indented JSON. Field truncation still applied unless `--no-truncation` is set. |
| `text` | Human-readable tables. Automatically used in the interactive REPL. |

**Field truncation** is applied before both TOON and JSON encoding. Trimmed fields include a marker showing what was cut.

| Limit | Default | Env var to override |
|-------|---------|---------------------|
| String length | 2000 chars | `SUMO_TRUNCATE_STR` |
| List items | 20 | `SUMO_TRUNCATE_LIST` |
| Dict keys | 30 | `SUMO_TRUNCATE_DICT` |

Disable truncation entirely with `--no-truncation`. See [Log Truncation](#log-truncation) below.

`--json` is a hidden alias for `--format json` (backward compatibility).

## Command Groups

### auth — Credentials management

| Command | Description |
|---------|-------------|
| `auth configure` | Prompt for and save endpoint + credentials |
| `auth status` | Show current credential configuration |
| `auth test` | Verify credentials against the live API |

### search — Log searches

| Command | Description |
|---------|-------------|
| `search run <query>` | Execute a search, poll until done, return results |
| `search history` | Show recent query history |
| `search saved` | List saved named queries |
| `search save <name> <query>` | Save a named query for reuse |
| `search delete-saved <name>` | Delete a saved query |
| `search replay <name>` | Re-execute a saved query |

`search run` options:
- `--from` — start time (default: `-15m`), accepts ISO8601 or relative like `-1h`
- `--to` — end time (default: `now`)
- `--timezone` — override session timezone
- `--limit` — max results (default: 100)
- `--timeout` — job timeout in seconds (default: 300)
- `--save-as NAME` — save query while running it
- `--dry-run` — show parameters without executing

### job — Direct job management

| Command | Description |
|---------|-------------|
| `job status <id>` | Get status of a search job |
| `job messages <id>` | Fetch raw log messages from a completed job |
| `job records <id>` | Fetch aggregate records from a completed job |
| `job delete <id>` | Cancel and delete a job |

### session — Session state

| Command | Description |
|---------|-------------|
| `session info` | Display session metadata |
| `session clear-history` | Clear query history |

## Examples

### Run a log search

```bash
cli-anything-sumologic search run "error | count by _sourceCategory" --from "-1h"
```

### Run an aggregate query (TOON output — default)

```bash
cli-anything-sumologic search run \
  "* | count by _sourceCategory | sort by _count desc | limit 10" \
  --from "-1h" --to "now"
```

TOON output (tabular — field names declared once per array, not per row):
```
job_id: ABC123
is_aggregate: true
message_count: 0
record_count: 10
fields[2]{name,fieldType}:
  _sourceCategory,string
  _count,long
records[10]{_sourceCategory,_count}:
  prod/app,842
  prod/db,310
  prod/web,95
  ...
```

Full JSON when you need it:
```bash
cli-anything-sumologic --format json search run \
  "* | count by _sourceCategory | sort by _count desc | limit 10" \
  --from "-1h" --to "now"
```

### Search raw messages

```bash
cli-anything-sumologic search run "exception" --from "-30m" --limit 20
```

Long `_raw` fields are automatically truncated in TOON mode with a marker like `[8400 chars truncated]`. Use `--format json` to get the full text.

### Save and replay queries

```bash
# Save a useful query
cli-anything-sumologic search save error-spike \
  "error | count by _host | sort by _count desc" \
  --from "-1h"

# Replay it any time
cli-anything-sumologic search replay error-spike
```

### Dry-run to inspect parameters

```bash
cli-anything-sumologic search run "error" --dry-run --from "-1h"
# Returns parameters JSON without creating a job
```

### Check credentials

```bash
cli-anything-sumologic auth status
cli-anything-sumologic auth test
```

## For AI Agents

1. **Default output is TOON** — compact, token-efficient, with field truncation applied automatically. No flag needed.
2. **Use `--no-truncation`** when you need the complete payload — e.g. to read a full stack trace or long log message.
3. **Use `--format json --no-truncation`** to get a full, parseable JSON payload with no content cut.
4. **Check `is_aggregate`** in search results to know whether to read `records` or `messages`.
5. **`search run` is the primary operation** — it handles the full job lifecycle (create → poll → fetch → delete).
6. **Use `--dry-run`** to validate query parameters without consuming API quota.
7. **Use `--save-as`** to save queries while running them.
8. **Use `search replay`** to re-run saved queries without repeating the query string.
9. **`auth test` exits non-zero on failure** — use it as a precondition check.

### Deployment endpoints

| Region | Endpoint |
|--------|----------|
| US1 | `https://api.sumologic.com/api/v1` |
| US2 | `https://api.us2.sumologic.com/api/v1` |
| EU | `https://api.eu.sumologic.com/api/v1` |
| AU | `https://api.au.sumologic.com/api/v1` |
| IN | `https://api.in.sumologic.com/api/v1` |
| JP | `https://api.jp.sumologic.com/api/v1` |
| CA | `https://api.ca.sumologic.com/api/v1` |
| FED | `https://api.fed.sumologic.com/api/v1` |

## Log Truncation

Field truncation is applied by default to both TOON and JSON output to keep payloads token-efficient. It is **not** applied to `--format text`.

### Defaults

| Field type | Default limit | Truncation marker |
|------------|--------------|-------------------|
| Strings | 2000 chars | `...[N chars truncated]` appended to the value |
| List items | 20 items | `"[N more items]"` appended as the last element |
| Dict keys | 30 keys | `"__more__": "N fields omitted"` added to the object |

### Disable truncation

```bash
# No truncation at all — full payload
cli-anything-sumologic --no-truncation search run "error" --from -1h

# Full untruncated JSON saved to file
cli-anything-sumologic --no-truncation --format json search run "error" --from -1h \
  > results.json
```

### Override limits via environment variables

Set these before running the CLI (or export them in your shell profile):

```bash
export SUMO_TRUNCATE_STR=5000   # raise string limit to 5000 chars
export SUMO_TRUNCATE_LIST=50    # keep up to 50 list/array items
export SUMO_TRUNCATE_DICT=60    # keep up to 60 dict keys

cli-anything-sumologic search run "error" --from -1h
```

`--no-truncation` always takes precedence over env vars.

## Version

1.1.0
