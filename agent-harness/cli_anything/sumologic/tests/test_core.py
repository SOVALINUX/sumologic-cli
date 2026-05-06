"""Unit tests for cli-anything-sumologic core modules.

Synthetic data only — no external dependencies, no network calls.
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from cli_anything.sumologic.core import formatter as fmt
from cli_anything.sumologic.core import search as search_mod
from cli_anything.sumologic.core import session as sess_mod
from cli_anything.sumologic.core.timeutil import parse_time


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_session_path(tmp_path):
    return tmp_path / "session.json"


@pytest.fixture
def sample_session():
    return {
        "endpoint": "https://api.us2.sumologic.com/api/v1",
        "access_id": "testid",
        "access_key": "testkey",
        "timezone": "UTC",
        "current_job_id": None,
        "query_history": [],
        "saved_queries": {},
    }


@pytest.fixture
def mock_client():
    c = MagicMock()
    c.create_job.return_value = {"id": "JOB123"}
    c.get_status.return_value = {
        "state": "DONE GATHERING RESULTS",
        "messageCount": 3,
        "recordCount": 0,
        "histogramBuckets": [],
        "pendingErrors": [],
        "pendingWarnings": [],
    }
    c.get_messages.return_value = {
        "fields": [{"name": "_raw", "fieldType": "string", "keyField": False}],
        "messages": [
            {"map": {"_raw": "log line 1", "_messagetime": "1000"}},
            {"map": {"_raw": "log line 2", "_messagetime": "2000"}},
            {"map": {"_raw": "log line 3", "_messagetime": "3000"}},
        ],
    }
    c.get_records.return_value = {
        "fields": [
            {"name": "_sourceCategory", "fieldType": "string", "keyField": False},
            {"name": "_count", "fieldType": "long", "keyField": False},
        ],
        "records": [
            {"map": {"_sourceCategory": "prod/app", "_count": "42"}},
        ],
    }
    c.delete_job.return_value = None
    return c


# ── session.py tests ──────────────────────────────────────────────────


class TestSession:

    def test_load_session_defaults(self, tmp_session_path):
        s = sess_mod.load_session(tmp_session_path)
        assert "endpoint" in s
        assert "access_id" in s
        assert "query_history" in s
        assert s["query_history"] == []

    def test_save_load_roundtrip(self, tmp_session_path, sample_session):
        sample_session["access_id"] = "roundtrip_id"
        sess_mod.save_session(sample_session, tmp_session_path)
        loaded = sess_mod.load_session(tmp_session_path)
        assert loaded["access_id"] == "roundtrip_id"
        assert loaded["endpoint"] == sample_session["endpoint"]

    def test_get_credentials_from_session(self, sample_session):
        endpoint, access_id, access_key = sess_mod.get_credentials(sample_session)
        assert endpoint == "https://api.us2.sumologic.com/api/v1"
        assert access_id == "testid"
        assert access_key == "testkey"

    def test_get_credentials_from_env(self, sample_session, monkeypatch):
        monkeypatch.setenv("SUMO_ENDPOINT", "https://api.eu.sumologic.com/api/v1")
        monkeypatch.setenv("SUMO_ACCESS_ID", "env_id")
        monkeypatch.setenv("SUMO_ACCESS_KEY", "env_key")
        endpoint, access_id, access_key = sess_mod.get_credentials(sample_session)
        assert "eu" in endpoint
        assert access_id == "env_id"
        assert access_key == "env_key"

    def test_validate_credentials_ok(self, sample_session):
        sess_mod.validate_credentials(sample_session)  # no exception

    def test_validate_credentials_missing_all(self):
        with pytest.raises(RuntimeError) as exc_info:
            sess_mod.validate_credentials({})
        msg = str(exc_info.value)
        assert "endpoint" in msg
        assert "access_id" in msg
        assert "access_key" in msg

    def test_validate_credentials_missing_partial(self, sample_session):
        sample_session["access_key"] = ""
        with pytest.raises(RuntimeError) as exc_info:
            sess_mod.validate_credentials(sample_session)
        msg = str(exc_info.value)
        assert "access_key" in msg
        assert "endpoint" not in msg  # endpoint is fine

    def test_add_to_history_appends(self, sample_session):
        sess_mod.add_to_history(sample_session, "error | count", {"from": "-1h", "to": "now"})
        assert len(sample_session["query_history"]) == 1
        assert sample_session["query_history"][0]["query"] == "error | count"

    def test_add_to_history_cap_at_50(self, sample_session):
        for i in range(60):
            sess_mod.add_to_history(sample_session, f"query {i}", {})
        assert len(sample_session["query_history"]) == 50
        assert sample_session["query_history"][-1]["query"] == "query 59"

    def test_save_query_creates(self, sample_session):
        sess_mod.save_query(sample_session, "my-query", "error | count", {"from": "-1h"})
        assert "my-query" in sample_session["saved_queries"]
        assert sample_session["saved_queries"]["my-query"]["query"] == "error | count"

    def test_delete_saved_query_exists(self, sample_session):
        sess_mod.save_query(sample_session, "to-delete", "* | limit 1", {})
        removed = sess_mod.delete_saved_query(sample_session, "to-delete")
        assert removed is True
        assert "to-delete" not in sample_session["saved_queries"]

    def test_delete_saved_query_missing(self, sample_session):
        removed = sess_mod.delete_saved_query(sample_session, "nonexistent")
        assert removed is False

    def test_get_session_info_keys(self, sample_session):
        info = sess_mod.get_session_info(sample_session)
        for key in ("endpoint", "access_id", "timezone", "current_job_id",
                    "history_count", "saved_queries_count"):
            assert key in info

    def test_locked_save_concurrent(self, tmp_session_path):
        errors = []
        data = {"counter": 0}

        def write_loop():
            try:
                for i in range(5):
                    d = {"value": i, "ts": time.time()}
                    sess_mod._locked_save_json(tmp_session_path, d)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_loop) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        with open(tmp_session_path) as f:
            loaded = json.load(f)
        assert "value" in loaded


# ── search.py tests ───────────────────────────────────────────────────


class TestSearch:

    def test_create_job_calls_client(self, mock_client):
        job_id = search_mod.create_job(mock_client, "error", "-1h", "now", "UTC")
        assert job_id == "JOB123"
        mock_client.create_job.assert_called_once_with("error", "-1h", "now", "UTC")

    def test_wait_for_job_polls_until_done(self, mock_client):
        states = ["GATHERING RESULTS", "GATHERING RESULTS", "DONE GATHERING RESULTS"]
        mock_client.get_status.side_effect = [
            {"state": s, "messageCount": 0, "recordCount": 0,
             "histogramBuckets": [], "pendingErrors": [], "pendingWarnings": []}
            for s in states
        ]
        status = search_mod.wait_for_job(mock_client, "JOB123", poll_interval=0.0)
        assert status["state"] == "DONE GATHERING RESULTS"
        assert mock_client.get_status.call_count == 3

    def test_wait_for_job_cancelled_raises(self, mock_client):
        mock_client.get_status.return_value = {
            "state": "CANCELLED",
            "messageCount": 0, "recordCount": 0,
            "histogramBuckets": [], "pendingErrors": [], "pendingWarnings": [],
        }
        with pytest.raises(RuntimeError, match="CANCELLED"):
            search_mod.wait_for_job(mock_client, "JOB123", poll_interval=0.0)

    def test_wait_for_job_timeout_raises(self, mock_client):
        mock_client.get_status.return_value = {
            "state": "GATHERING RESULTS",
            "messageCount": 0, "recordCount": 0,
            "histogramBuckets": [], "pendingErrors": [], "pendingWarnings": [],
        }
        with pytest.raises(TimeoutError):
            search_mod.wait_for_job(
                mock_client, "JOB123", poll_interval=0.0, timeout=-1.0
            )

    def test_fetch_messages_paginates(self, mock_client):
        page1 = {"fields": [], "messages": [{"map": {"_raw": f"line {i}"}} for i in range(3)]}
        page2 = {"fields": [], "messages": [{"map": {"_raw": f"line {i}"}} for i in range(3, 5)]}
        page3 = {"fields": [], "messages": []}
        mock_client.get_messages.side_effect = [page1, page2, page3]

        status = {"messageCount": 5}
        messages = search_mod.fetch_all_messages(mock_client, "JOB123", status, limit=3)
        assert len(messages) == 5

    def test_fetch_records_paginates(self, mock_client):
        page1 = {
            "fields": [{"name": "_count", "fieldType": "long", "keyField": False}],
            "records": [{"map": {"_count": "1"}}, {"map": {"_count": "2"}}],
        }
        page2 = {
            "fields": [{"name": "_count", "fieldType": "long", "keyField": False}],
            "records": [{"map": {"_count": "3"}}],
        }
        page3 = {
            "fields": [],
            "records": [],
        }
        mock_client.get_records.side_effect = [page1, page2, page3]
        status = {"recordCount": 3}
        fields, records = search_mod.fetch_all_records(mock_client, "JOB123", status, limit=2)
        assert len(records) == 3

    def test_run_search_aggregate_path(self, mock_client):
        mock_client.get_status.return_value = {
            "state": "DONE GATHERING RESULTS",
            "messageCount": 0,
            "recordCount": 2,
            "histogramBuckets": [], "pendingErrors": [], "pendingWarnings": [],
        }
        result = search_mod.run_search(
            mock_client, "* | count", "-1h", "now", cleanup=True
        )
        assert result["is_aggregate"] is True
        mock_client.get_records.assert_called()
        mock_client.delete_job.assert_called_once()

    def test_run_search_message_path(self, mock_client):
        result = search_mod.run_search(
            mock_client, "error", "-1h", "now", cleanup=True
        )
        assert result["is_aggregate"] is False
        mock_client.get_messages.assert_called()
        mock_client.delete_job.assert_called_once()

    def test_run_search_cleanup_on_error(self, mock_client):
        mock_client.get_messages.side_effect = RuntimeError("fetch failed")
        with pytest.raises(RuntimeError):
            search_mod.run_search(mock_client, "error", "-1h", "now", cleanup=True)
        mock_client.delete_job.assert_called_once_with("JOB123")


# ── formatter.py tests ────────────────────────────────────────────────


class TestFormatter:

    def test_format_messages_table_empty(self):
        result = fmt.format_messages_table([], [])
        assert result == "(no messages)"

    def test_format_messages_table_rows(self):
        messages = [
            {"map": {"_raw": "hello world", "_messagetime": "12345"}},
            {"map": {"_raw": "another line", "_messagetime": "12346"}},
        ]
        result = fmt.format_messages_table([], messages)
        assert "hello world" in result
        assert "another line" in result
        assert "12345" in result

    def test_format_records_table_empty(self):
        result = fmt.format_records_table([], [])
        assert result == "(no records)"

    def test_format_records_table_columns(self):
        fields = [
            {"name": "_sourceCategory", "fieldType": "string", "keyField": False},
            {"name": "_count", "fieldType": "long", "keyField": False},
        ]
        records = [
            {"map": {"_sourceCategory": "prod/app", "_count": "42"}},
        ]
        result = fmt.format_records_table(fields, records)
        assert "_sourceCategory" in result
        assert "_count" in result
        assert "prod/app" in result
        assert "42" in result

    def test_format_status_fields(self):
        status = {
            "state": "DONE GATHERING RESULTS",
            "messageCount": 100,
            "recordCount": 0,
            "pendingErrors": [],
            "pendingWarnings": [],
        }
        result = fmt.format_status(status)
        assert "DONE" in result
        assert "100" in result

    def test_to_json_roundtrip(self):
        data = {"key": "value", "num": 42, "lst": [1, 2, 3]}
        serialized = fmt.to_json(data)
        parsed = json.loads(serialized)
        assert parsed == data

    def test_message_to_dict(self):
        msg = {"map": {"_raw": "hello", "_messagetime": "999"}}
        d = fmt.message_to_dict(msg)
        assert d["_raw"] == "hello"

    def test_record_to_dict(self):
        rec = {"map": {"_count": "5", "_sourceCategory": "test"}}
        d = fmt.record_to_dict(rec)
        assert d["_count"] == "5"

    # ── deep_truncate tests ───────────────────────────────────────────

    def test_deep_truncate_short_string_unchanged(self):
        assert fmt.deep_truncate("hello", max_str=10) == "hello"

    def test_deep_truncate_long_string(self):
        long_s = "x" * 600
        result = fmt.deep_truncate(long_s, max_str=500)
        assert result.startswith("x" * 500)
        assert "100 chars truncated" in result
        assert len(result) < 600

    def test_deep_truncate_list_within_limit(self):
        lst = [1, 2, 3]
        assert fmt.deep_truncate(lst, max_list=5) == [1, 2, 3]

    def test_deep_truncate_list_over_limit(self):
        lst = list(range(25))
        result = fmt.deep_truncate(lst, max_list=20)
        assert len(result) == 21  # 20 items + sentinel
        assert "5 more items" in result[-1]

    def test_deep_truncate_dict_within_limit(self):
        d = {"a": 1, "b": 2}
        assert fmt.deep_truncate(d, max_dict=5) == {"a": 1, "b": 2}

    def test_deep_truncate_dict_over_limit(self):
        d = {str(i): i for i in range(35)}
        result = fmt.deep_truncate(d, max_dict=30)
        assert "__more__" in result
        assert "5 fields omitted" in result["__more__"]

    def test_deep_truncate_nested(self):
        data = {"logs": ["a" * 600] * 25}
        result = fmt.deep_truncate(data, max_str=500, max_list=20)
        assert len(result["logs"]) == 21
        assert "100 chars truncated" in result["logs"][0]

    # ── to_toon tests (real TOON format) ─────────────────────────────

    def test_to_toon_simple_object(self):
        result = fmt.to_toon({"name": "Alice", "age": 30})
        assert "name: Alice" in result
        assert "age: 30" in result

    def test_to_toon_bool_and_null(self):
        result = fmt.to_toon({"active": True, "deleted": False, "note": None})
        assert "active: true" in result
        assert "deleted: false" in result
        assert "note: null" in result

    def test_to_toon_inline_primitive_array(self):
        result = fmt.to_toon({"tags": ["admin", "ops", "dev"]})
        assert "[3]" in result
        assert "admin" in result
        assert "ops" in result

    def test_to_toon_tabular_array(self):
        data = {"records": [
            {"_sourceCategory": "prod/app", "_count": "42"},
            {"_sourceCategory": "prod/db", "_count": "10"},
        ]}
        result = fmt.to_toon(data)
        # Header declared once, not repeated per row
        assert "{_sourceCategory,_count}" in result
        assert "prod/app" in result
        assert "prod/db" in result
        # Keys should NOT be repeated on data rows
        lines = result.splitlines()
        data_rows = [l for l in lines if "prod/" in l]
        for row in data_rows:
            assert "_sourceCategory" not in row  # key not repeated in data rows

    def test_to_toon_nested_object(self):
        data = {"job_id": "ABC", "status": {"state": "DONE", "count": 5}}
        result = fmt.to_toon(data)
        assert "job_id: ABC" in result
        assert "state: DONE" in result
        assert "count: 5" in result

    def test_to_toon_string_quoting(self):
        # Strings that look like booleans/null must be quoted
        result = fmt.to_toon({"flag": "true", "val": "null"})
        assert '"true"' in result
        assert '"null"' in result

    def test_to_toon_empty_array(self):
        result = fmt.to_toon({"items": []})
        assert "[0]" in result

    def test_to_toon_non_uniform_array(self):
        # Mixed types fall back to list-marker format
        result = fmt.to_toon({"items": [1, {"a": 2}, "text"]})
        assert "- " in result


# ── timeutil.py tests ─────────────────────────────────────────────────


class TestTimeutil:

    def test_now(self):
        result = parse_time("now")
        assert result.endswith("+00:00")
        assert "T" in result

    def test_relative_hours(self):
        result = parse_time("-3h")
        assert result.endswith("+00:00")
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(result)
        delta = datetime.now(timezone.utc) - dt
        assert 10795 < delta.total_seconds() < 10810  # ~3h ± 10s

    def test_relative_minutes(self):
        result = parse_time("-30m")
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(result)
        delta = datetime.now(timezone.utc) - dt
        assert 1790 < delta.total_seconds() < 1810  # ~30m ± 10s

    def test_relative_days(self):
        result = parse_time("-1d")
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(result)
        delta = datetime.now(timezone.utc) - dt
        assert 86390 < delta.total_seconds() < 86410  # ~1d ± 10s

    def test_iso8601_passthrough(self):
        iso = "2026-01-01T00:00:00+00:00"
        assert parse_time(iso) == iso

    def test_unix_ms_timestamp(self):
        result = parse_time("1778080218141")
        assert "2026-05-06" in result
        assert result.endswith("+00:00")
