# sumologic-cli

CLI tool for searching Sumo Logic logs via the Search Job API. Designed for use from the terminal and by AI agents.

## Features

- Execute Sumo Logic queries from the command line
- Relative time ranges: `-3h`, `-30m`, `-1d`, etc.
- **TOON output mode** (default) — compact JSON with automatic truncation of long strings, large arrays, and large objects, minimising token consumption for AI agents
- Full JSON output mode (`--format json`) for untruncated machine-readable results
- Save and replay named queries
- Interactive REPL with command history
- Credentials via environment variables or interactive setup

## Prerequisites

- Python 3.10+
- A Sumo Logic account with an Access ID and Access Key
  (Preferences → Access Keys in the Sumo Logic UI)

## Installation

```bash
cd agent-harness
pip install -e .
```

Verify:

```bash
cli-anything-sumologic --help
```

## Configuration

### Option 1: Environment variables (recommended)

```bash
export SUMO_ENDPOINT="https://api.de.sumologic.com/api/v1"
export SUMO_ACCESS_ID="your-access-id"
export SUMO_ACCESS_KEY="your-access-key"
```

You can put these in a `.env` file at the project root and load them:

```bash
source .env && export SUMO_ENDPOINT SUMO_ACCESS_ID SUMO_ACCESS_KEY
```

### Option 2: Interactive configure

```bash
cli-anything-sumologic auth configure
```

Credentials are saved to `~/.cli-anything-sumologic/session.json`.

### Endpoint by deployment

See the [Sumo Logic API endpoints by deployment](https://www.sumologic.com/help/docs/api/about-apis/getting-started/#sumo-logic-endpoints-by-deployment-and-firewall-security) for the full list of regional API base URLs.

## Usage

### Interactive REPL

```bash
cli-anything-sumologic
```

### One-shot commands

```bash
cli-anything-sumologic <command-group> <command> [OPTIONS]
```

### Global flags

| Flag | Description |
|------|-------------|
| `--format [text\|json\|toon]` | Output format (default: `toon`) |
| `--help` | Show help for any command |

**Formats:**
- `toon` *(default)* — Token-Oriented Object Notation. YAML-like key-value pairs for objects, tabular CSV rows for uniform arrays (keys declared once per array, not per row). Field truncation applied before encoding. Optimised for AI agent consumption.
- `json` — full indented JSON. Field truncation still applied unless `--no-truncation` is set.
- `text` — human-readable formatted tables. Always used in the interactive REPL.

| Flag | Description |
|------|-------------|
| `--no-truncation` | Disable field truncation entirely. Returns the full payload. |

`--json` is kept as a hidden alias for `--format json` for backward compatibility.

---

## Commands

### `auth` — Credentials

```bash
# Configure endpoint + credentials interactively
cli-anything-sumologic auth configure

# Show current credential status
cli-anything-sumologic auth status

# Verify credentials against the live API
cli-anything-sumologic auth test
```

### `search` — Log search

```bash
# Run a query (last 15 minutes by default)
cli-anything-sumologic search run "error"

# Relative time ranges
cli-anything-sumologic search run "error | count by _sourceCategory" --from -1h
cli-anything-sumologic search run "exception" --from -3h --to -1h

# Limit results
cli-anything-sumologic search run "* | limit 5" --from -30m --limit 5

# Save a query while running it
cli-anything-sumologic search run "error | count" --from -1h --save-as my-errors

# Dry-run: show resolved parameters without executing
cli-anything-sumologic search run "error" --from -3h --dry-run

# List saved queries
cli-anything-sumologic search saved

# Save a named query
cli-anything-sumologic search save daily-errors "error | count by _sourceCategory" --from -24h

# Re-run a saved query
cli-anything-sumologic search replay daily-errors

# Delete a saved query
cli-anything-sumologic search delete-saved daily-errors

# View recent query history
cli-anything-sumologic search history --limit 10
```

### `job` — Direct job management

```bash
# Check job status
cli-anything-sumologic job status <job-id>

# Fetch messages from a completed job
cli-anything-sumologic job messages <job-id> --limit 50 --offset 0

# Fetch aggregate records from a completed job
cli-anything-sumologic job records <job-id>

# Cancel / delete a job
cli-anything-sumologic job delete <job-id>
```

### `session` — Session state

```bash
# Show session details (endpoint, history count, etc.)
cli-anything-sumologic session info

# Clear query history
cli-anything-sumologic session clear-history
```

---

## Time Range Formats

The `--from` and `--to` flags accept:

| Format | Example | Meaning |
|--------|---------|---------|
| Relative | `-3h` | 3 hours ago |
| Relative | `-30m` | 30 minutes ago |
| Relative | `-1d` | 1 day ago |
| Relative | `-2w` | 2 weeks ago |
| Special | `now` | Current time |
| ISO8601 | `2026-01-15T10:00:00+00:00` | Exact timestamp |

---

## Output Formats (for scripts and agents)

Pass `--format` before the command group. The default is `toon`.

```bash
# TOON — compact, truncated JSON (default, token-efficient)
cli-anything-sumologic search run "error" --from -1h --limit 10

# Full JSON — indented, no truncation
cli-anything-sumologic --format json search run "error" --from -1h --limit 10

# Human-readable text
cli-anything-sumologic --format text search run "error" --from -1h
```

### TOON output (default)

TOON (Token-Oriented Object Notation) is a compact, human-readable format designed to minimise LLM token consumption. See [toonformat.dev](https://toonformat.dev) for the full spec.

Key syntax:
- **Objects** use `key: value` pairs with indentation (no `{` `}`)
- **Uniform arrays** use a tabular header declaring field names once, then one CSV row per item — the big win for log records
- **Primitive arrays** are inlined: `tags[3]: admin,ops,dev`
- **Strings** are unquoted unless they contain structural characters or look like booleans/numbers

Example output for an aggregate query:
```
job_id: ABC123
is_aggregate: true
record_count: 3
records[3]{_sourceCategory,_count}:
  prod/app,842
  prod/db,310
  prod/web,95
```

Notice `_sourceCategory` and `_count` appear only once in the header, not on every row — this is where TOON saves the most tokens vs JSON.

TOON truncation is applied separately before encoding (see below).

### Field truncation

Before serialization, large fields are truncated to keep payloads manageable. Truncation applies to both `toon` and `json` formats.

| What | Default limit | Marker added |
|------|--------------|--------------|
| Strings | **2000 chars** | `...[N chars truncated]` appended |
| Lists | **20 items** | `"[N more items]"` appended as last element |
| Dicts | **30 keys** | `"__more__": "N fields omitted"` added |

**Disable truncation entirely:**

```bash
cli-anything-sumologic --no-truncation search run "error" --from -1h
```

**Override limits via environment variables:**

```bash
export SUMO_TRUNCATE_STR=5000   # raise string limit to 5000 chars
export SUMO_TRUNCATE_LIST=50    # keep up to 50 list items
export SUMO_TRUNCATE_DICT=60    # keep up to 60 dict keys
```

These can be set per-invocation or in your shell profile / `.env` file. `--no-truncation` takes precedence and ignores the env vars.

### Full JSON output

```bash
cli-anything-sumologic --format json search run "error" --from -1h --limit 10
```

```json
{
  "job_id": "3C967AD8DD28BFAB",
  "is_aggregate": false,
  "message_count": 70,
  "record_count": 0,
  "fields": [...],
  "messages": [
    {"_raw": "2026-05-06T15:10:18Z ERROR ...", "_messagetime": "1778080218141"},
    ...
  ]
}
```

For an aggregate query (`| count by ...`):
```json
{
  "job_id": "ABC123",
  "is_aggregate": true,
  "message_count": 0,
  "record_count": 5,
  "fields": [...],
  "records": [
    {"_sourceCategory": "prod/app", "_count": "842"},
    ...
  ]
}
```

Use `is_aggregate` to decide whether to read `messages` or `records`.

---

## Examples

### Find recent Lambda logs for a specific agent (TOON, token-efficient)

```bash
cli-anything-sumologic search run \
  '(_sourceHost=/aws/lambda/myapp-*) AND "my_agent_name"' \
  --from -3h --limit 50
```

### Save full untruncated results to a file

```bash
cli-anything-sumologic --no-truncation --format json search run "error | limit 100" --from -6h \
  > results.json
```

---

## Running Tests

### Unit tests (no credentials needed)

```bash
cd agent-harness
python -m pytest cli_anything/sumologic/tests/test_core.py -v
```

### E2E tests (requires live Sumo Logic credentials)

```bash
export SUMO_ENDPOINT="https://api.de.sumologic.com/api/v1"
export SUMO_ACCESS_ID="your-id"
export SUMO_ACCESS_KEY="your-key"

CLI_ANYTHING_FORCE_INSTALLED=1 python -m pytest \
  cli_anything/sumologic/tests/test_full_e2e.py -v -s
```

---

## Project Structure

```
sumologic-cli/
├── .env                          # Credentials (gitignored)
├── README.md
└── agent-harness/
    ├── setup.py                  # pip install -e .
    └── cli_anything/sumologic/
        ├── sumologic_cli.py      # CLI entry point
        ├── core/
        │   ├── session.py        # Credentials + saved queries
        │   ├── search.py         # Job lifecycle
        │   ├── formatter.py      # Output formatting
        │   └── timeutil.py       # Relative time parsing
        ├── utils/
        │   └── sumologic_backend.py  # HTTP client
        └── tests/
            ├── test_core.py      # Unit tests (52 tests)
            └── test_full_e2e.py  # E2E tests (requires credentials)
```
