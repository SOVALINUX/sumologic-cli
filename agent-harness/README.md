# cli-anything-sumologic

CLI harness for the Sumo Logic Search Job API. Run Sumo Logic log searches from
the command line or from AI agents.

## Prerequisites

A Sumo Logic account with API access. No additional software installation
required — the CLI calls the Sumo Logic REST API directly over HTTPS.

You will need:
- **Access ID** and **Access Key** from your Sumo Logic account
  (Preferences → Access Keys)
- **API endpoint** for your deployment (e.g. `https://api.us2.sumologic.com/api/v1`)

## Installation

```bash
cd agent-harness
pip install -e .
```

Verify:
```bash
which cli-anything-sumologic
cli-anything-sumologic --help
```

## Configuration

### Option 1: Environment variables (recommended for agents)

```bash
export SUMO_ENDPOINT="https://api.us2.sumologic.com/api/v1"
export SUMO_ACCESS_ID="your-access-id"
export SUMO_ACCESS_KEY="your-access-key"
```

### Option 2: Interactive configure

```bash
cli-anything-sumologic auth configure
```

Credentials are stored in `~/.cli-anything-sumologic/session.json`.

## Usage

### Interactive REPL

```bash
cli-anything-sumologic
```

### One-shot commands

```bash
# Run a search (last 15 minutes) — TOON output by default
cli-anything-sumologic search run "error | count by _sourceCategory"

# Search with explicit time range
cli-anything-sumologic search run "exception" --from "-1h" --to "now"

# Full indented JSON output (no truncation)
cli-anything-sumologic --format json search run "* | limit 10" --from "-5m"

# Human-readable text
cli-anything-sumologic --format text search run "* | limit 10" --from "-5m"

# Save a query for reuse
cli-anything-sumologic search save my-errors "error | count" --from "-1h"

# Replay a saved query
cli-anything-sumologic search replay my-errors

# Show credential status
cli-anything-sumologic auth status

# Test credentials
cli-anything-sumologic auth test
```

## Command Groups

| Group | Commands | Description |
|-------|----------|-------------|
| `auth` | `configure`, `status`, `test` | Manage credentials |
| `search` | `run`, `history`, `saved`, `save`, `delete-saved`, `replay` | Log searches |
| `job` | `status`, `messages`, `records`, `delete` | Manage search jobs |
| `session` | `info`, `clear-history` | Session state |

## Output Formats

| Flag | Description |
|------|-------------|
| *(no flag)* | **TOON** — Token-Oriented Object Notation (default, token-efficient) |
| `--format toon` | Same as default |
| `--format json` | Full indented JSON |
| `--format text` | Human-readable tables (always used inside the REPL) |

TOON uses YAML-like key-value pairs for objects and tabular CSV rows for uniform arrays (field names declared once per array). Field truncation is applied before encoding: strings > 500 chars, lists > 20 items, dicts > 30 fields.  
`--json` is a hidden alias for `--format json` kept for backward compatibility.

## Agent Usage (TOON mode — default)

```bash
# Credentials check
cli-anything-sumologic auth status

# Run search, parse results — output is compact JSON with truncation
cli-anything-sumologic search run "error | count by _host" --from "-1h"
# {"job_id":"...","is_aggregate":true,"record_count":5,"fields":[...],"records":[{"_host":"web-01","_count":"42"},...]}

# Full JSON when you need untruncated data
cli-anything-sumologic --format json search run "error | count by _host" --from "-1h"

# Dry-run to preview query params
cli-anything-sumologic search run "error" --dry-run --from "-1h"
```

## Running Tests

### Unit tests (no credentials needed)

```bash
cd agent-harness
pip install -e .
pytest cli_anything/sumologic/tests/test_core.py -v
```

### E2E tests (requires live Sumo Logic credentials)

```bash
export SUMO_ENDPOINT="https://api.us2.sumologic.com/api/v1"
export SUMO_ACCESS_ID="your-id"
export SUMO_ACCESS_KEY="your-key"

CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/sumologic/tests/test_full_e2e.py -v -s
```

## Deployment Endpoints

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
