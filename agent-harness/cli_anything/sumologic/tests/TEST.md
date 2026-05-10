# Test Plan — cli-anything-sumologic

## Test Inventory Plan

| File | Type | Planned tests |
|------|------|---------------|
| `test_core.py` | Unit tests | 28 |
| `test_full_e2e.py` | E2E + subprocess tests | 16 |

---

## Unit Test Plan (`test_core.py`)

### `core/session.py`

Functions: `load_session`, `save_session`, `get_credentials`, `validate_credentials`,
`add_to_history`, `save_query`, `delete_saved_query`, `get_session_info`, `_locked_save_json`

| Test | Coverage |
|------|----------|
| `test_load_session_defaults` | Missing file → empty session with all default keys |
| `test_save_load_roundtrip` | Save then load returns same data |
| `test_get_credentials_from_session` | Returns values from session dict |
| `test_get_credentials_from_env` | Env vars override session values |
| `test_validate_credentials_ok` | No exception when all present |
| `test_validate_credentials_missing_all` | RuntimeError with helpful message |
| `test_validate_credentials_missing_partial` | RuntimeError lists only missing fields |
| `test_add_to_history_appends` | Entry added to list |
| `test_add_to_history_cap_at_50` | History capped at 50 entries |
| `test_save_query_creates` | Named query stored in dict |
| `test_delete_saved_query_exists` | Removes entry, returns True |
| `test_delete_saved_query_missing` | Returns False, no error |
| `test_get_session_info_keys` | All expected keys present |
| `test_locked_save_concurrent_safe` | Multiple writes don't corrupt |

### `core/search.py` (unit — with mocked client)

| Test | Coverage |
|------|----------|
| `test_create_job_calls_client` | create_job calls client.create_job correctly |
| `test_wait_for_job_polls_until_done` | Loops until state == DONE |
| `test_wait_for_job_cancelled_raises` | RuntimeError on CANCELLED state |
| `test_wait_for_job_timeout_raises` | TimeoutError after deadline |
| `test_fetch_messages_paginates` | Multiple pages assembled correctly |
| `test_fetch_records_paginates` | Multiple pages assembled correctly |
| `test_run_search_aggregate_path` | Routes to records when recordCount > 0 |
| `test_run_search_message_path` | Routes to messages when recordCount == 0 |
| `test_run_search_cleanup_on_error` | delete_job called even when fetch fails |

### `core/formatter.py`

| Test | Coverage |
|------|----------|
| `test_format_messages_table_empty` | Returns "(no messages)" |
| `test_format_messages_table_rows` | One line per message with timestamp |
| `test_format_records_table_empty` | Returns "(no records)" |
| `test_format_records_table_columns` | Column headers + values aligned |
| `test_format_status_fields` | State, counts, errors shown |
| `test_to_json_roundtrip` | Output is valid JSON |
| `test_message_to_dict` | Extracts .map correctly |
| `test_record_to_dict` | Extracts .map correctly |

---

## E2E Test Plan (`test_full_e2e.py`)

### Precondition

All E2E tests require a live Sumo Logic account. Credentials are read from
env vars: `SUMO_ACCESS_ID`, `SUMO_ACCESS_KEY`, `SUMO_ENDPOINT`.
Tests will fail (not skip) when credentials are missing — Sumo Logic is a
hard dependency.

### Test Classes

#### `TestSumoLogicBackend` — direct HTTP client

| Test | Workflow |
|------|----------|
| `test_create_poll_delete_job` | Create job → poll until DONE → delete |
| `test_fetch_messages` | Create job → wait → fetch first page of messages |
| `test_fetch_records_aggregate` | Run `* | count by _sourceCategory` → fetch records |
| `test_pagination` | Verify offset/limit works across 2+ pages |

#### `TestCLISubprocess` — installed CLI via subprocess

| Test | Workflow |
|------|----------|
| `test_help` | `--help` exits 0, shows usage |
| `test_auth_status_json` | `auth status --json` returns valid JSON |
| `test_search_run_messages_json` | `search run "error" --json` returns messages array |
| `test_search_run_records_json` | `search run "* | count by _sourceCategory" --json` |
| `test_search_save_and_replay` | save → replay works end-to-end |
| `test_search_history` | After search, history shows the query |
| `test_job_status_json` | `job status <id> --json` returns valid status |
| `test_session_info_json` | `session info --json` returns info dict |

---

## Realistic Workflow Scenarios

### Scenario 1: Error triage
**Simulates**: On-call engineer debugging a production spike.
**Operations**:
1. `search run "error OR exception | count by _sourceCategory" --from -1h`
2. `search run "error | tail 20" --from -30m`
3. `search save error-spike "error | count by _host" --from -1h`
**Verified**: Record table has _count column; message lines include timestamps.

### Scenario 2: Saved-query workflow
**Simulates**: Recurring daily log audit.
**Operations**:
1. `search save daily-errors "error | count by _sourceCategory"`
2. `search saved` (lists the query)
3. `search replay daily-errors`
4. `search delete-saved daily-errors`
**Verified**: JSON output has `saved_queries` key; replay returns same structure as run.

### Scenario 3: Agent-driven search (JSON mode)
**Simulates**: AI agent running searches programmatically.
**Operations**:
1. `--json auth status` → parse credentials status
2. `--json search run "* | limit 5" --from -5m` → parse messages
3. `--json session info` → verify history incremented
**Verified**: All output is valid JSON parseable by `json.loads`.

---

## Test Results

### Unit tests (`test_core.py`) — Run 2026-05-06

```
============================= test session starts ==============================
platform darwin -- Python 3.13.6, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/Siarhei_Nekhviadovich/code/sumologic-cli/agent-harness

cli_anything/sumologic/tests/test_core.py::TestSession::test_load_session_defaults PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_save_load_roundtrip PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_get_credentials_from_session PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_get_credentials_from_env PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_validate_credentials_ok PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_validate_credentials_missing_all PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_validate_credentials_missing_partial PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_add_to_history_appends PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_add_to_history_cap_at_50 PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_save_query_creates PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_delete_saved_query_exists PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_delete_saved_query_missing PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_get_session_info_keys PASSED
cli_anything/sumologic/tests/test_core.py::TestSession::test_locked_save_concurrent PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_create_job_calls_client PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_wait_for_job_polls_until_done PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_wait_for_job_cancelled_raises PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_wait_for_job_timeout_raises PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_fetch_messages_paginates PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_fetch_records_paginates PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_run_search_aggregate_path PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_run_search_message_path PASSED
cli_anything/sumologic/tests/test_core.py::TestSearch::test_run_search_cleanup_on_error PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_format_messages_table_empty PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_format_messages_table_rows PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_format_records_table_empty PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_format_records_table_columns PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_format_status_fields PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_to_json_roundtrip PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_message_to_dict PASSED
cli_anything/sumologic/tests/test_core.py::TestFormatter::test_record_to_dict PASSED

============================== 31 passed in 0.06s ==============================
```

### Summary

| Suite | Tests | Passed | Failed | Time |
|-------|-------|--------|--------|------|
| `test_core.py` | 31 | 31 | 0 | 0.06s |
| `test_full_e2e.py` | 16 | — | — | requires live credentials |

**Pass rate: 100% (unit tests)**

### Coverage Notes

- All core modules covered: `session.py`, `search.py`, `formatter.py`
- E2E tests (`test_full_e2e.py`) require `SUMO_ACCESS_ID`, `SUMO_ACCESS_KEY`, `SUMO_ENDPOINT`
- E2E tests cover: job lifecycle, message/record fetching, pagination, CLI subprocess
- Run E2E with: `CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/sumologic/tests/test_full_e2e.py -v -s`
