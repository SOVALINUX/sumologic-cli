"""End-to-end tests for cli-anything-sumologic.

Requires a live Sumo Logic account. Set env vars:
    SUMO_ACCESS_ID, SUMO_ACCESS_KEY, SUMO_ENDPOINT

All tests fail (not skip) when credentials are missing — Sumo Logic is a
hard dependency of this CLI.

Run with:
    CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/sumologic/tests/test_full_e2e.py -v -s
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from cli_anything.sumologic.core import search as search_mod
from cli_anything.sumologic.utils.sumologic_backend import SumoLogicClient, make_client


# ── Credential helpers ────────────────────────────────────────────────


def _require_credentials() -> tuple[str, str, str]:
    """Return (endpoint, access_id, access_key) or raise."""
    endpoint = os.environ.get("SUMO_ENDPOINT", "")
    access_id = os.environ.get("SUMO_ACCESS_ID", "")
    access_key = os.environ.get("SUMO_ACCESS_KEY", "")
    missing = [k for k, v in [
        ("SUMO_ENDPOINT", endpoint),
        ("SUMO_ACCESS_ID", access_id),
        ("SUMO_ACCESS_KEY", access_key),
    ] if not v]
    if missing:
        raise RuntimeError(
            f"E2E tests require Sumo Logic credentials. Missing env vars: "
            f"{', '.join(missing)}\n"
            f"These tests MUST run against the real Sumo Logic API."
        )
    return endpoint, access_id, access_key


def _make_client() -> SumoLogicClient:
    endpoint, access_id, access_key = _require_credentials()
    return make_client(endpoint, access_id, access_key)


# ── CLI subprocess resolver ───────────────────────────────────────────


def _resolve_cli(name: str) -> list[str]:
    """Resolve installed CLI command; falls back to python -m for dev.

    Set env CLI_ANYTHING_FORCE_INSTALLED=1 to require the installed command.
    """
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"\n[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(
            f"{name} not found in PATH. Install with: pip install -e ."
        )
    module = "cli_anything.sumologic.sumologic_cli"
    print(f"\n[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


# ── E2E: direct API backend tests ────────────────────────────────────


class TestSumoLogicBackend:
    """Test the HTTP client directly against the live Sumo Logic API."""

    @pytest.fixture(autouse=True)
    def _client(self):
        self.client = _make_client()

    def test_create_poll_delete_job(self):
        """Create a search job, poll for completion, delete it."""
        endpoint, _, _ = _require_credentials()
        job_id = search_mod.create_job(
            self.client,
            query="* | limit 1",
            from_time="-5m",
            to_time="now",
            timezone="UTC",
        )
        assert job_id, "Expected a non-empty job ID"
        print(f"\n  Created job: {job_id}")

        status = search_mod.wait_for_job(self.client, job_id, poll_interval=1.0, timeout=60.0)
        assert status["state"] == "DONE GATHERING RESULTS"
        print(f"  Status: {status['state']}, messages: {status.get('messageCount', 0)}")

        search_mod.delete_job(self.client, job_id)
        print(f"  Deleted job: {job_id}")

    def test_fetch_messages(self):
        """Create a job and fetch messages from it."""
        job_id = search_mod.create_job(
            self.client, "* | limit 5", "-5m", "now", "UTC"
        )
        try:
            status = search_mod.wait_for_job(
                self.client, job_id, poll_interval=1.0, timeout=60.0
            )
            result = search_mod.fetch_messages(self.client, job_id, limit=5)
            messages = result.get("messages", [])
            print(f"\n  Fetched {len(messages)} messages from job {job_id}")
            # Messages may be 0 if no data exists in the time range — just verify structure
            assert isinstance(messages, list)
            if messages:
                assert "map" in messages[0]
        finally:
            try:
                search_mod.delete_job(self.client, job_id)
            except Exception:
                pass

    def test_fetch_records_aggregate(self):
        """Run an aggregate query and fetch records."""
        result = search_mod.run_search(
            self.client,
            query="* | count by _sourceCategory | sort by _count desc | limit 5",
            from_time="-1h",
            to_time="now",
            timezone="UTC",
            timeout=90.0,
            cleanup=True,
        )
        print(f"\n  is_aggregate: {result['is_aggregate']}")
        print(f"  record_count: {result['status'].get('recordCount', 0)}")
        if result["is_aggregate"]:
            assert isinstance(result["records"], list)
            if result["records"]:
                assert "map" in result["records"][0]
                print(f"  First record: {result['records'][0]['map']}")

    def test_pagination(self):
        """Verify offset/limit pagination works."""
        job_id = search_mod.create_job(
            self.client, "* | limit 10", "-15m", "now", "UTC"
        )
        try:
            status = search_mod.wait_for_job(
                self.client, job_id, poll_interval=1.0, timeout=60.0
            )
            count = status.get("messageCount", 0)
            print(f"\n  Total messages available: {count}")
            if count >= 2:
                page1 = search_mod.fetch_messages(self.client, job_id, limit=1, offset=0)
                page2 = search_mod.fetch_messages(self.client, job_id, limit=1, offset=1)
                msgs1 = page1.get("messages", [])
                msgs2 = page2.get("messages", [])
                assert len(msgs1) <= 1
                assert len(msgs2) <= 1
                if msgs1 and msgs2:
                    assert msgs1[0] != msgs2[0], "Pages should return different messages"
        finally:
            try:
                search_mod.delete_job(self.client, job_id)
            except Exception:
                pass


# ── E2E: CLI subprocess tests ─────────────────────────────────────────


class TestCLISubprocess:
    """Test the installed CLI via subprocess — simulates real agent usage."""

    CLI_BASE = _resolve_cli("cli-anything-sumologic")

    @pytest.fixture(autouse=True)
    def _verify_credentials(self):
        _require_credentials()  # fail fast if not configured

    @pytest.fixture
    def tmp_session(self, tmp_path):
        """Set up a temp session dir with credentials."""
        session_file = tmp_path / "session.json"
        endpoint, access_id, access_key = _require_credentials()
        session_data = {
            "endpoint": endpoint,
            "access_id": access_id,
            "access_key": access_key,
            "timezone": "UTC",
            "current_job_id": None,
            "query_history": [],
            "saved_queries": {},
        }
        session_file.write_text(json.dumps(session_data, indent=2))
        env = dict(os.environ)
        env["SUMO_ENDPOINT"] = endpoint
        env["SUMO_ACCESS_ID"] = access_id
        env["SUMO_ACCESS_KEY"] = access_key
        return {"path": session_file, "env": env}

    def _run(self, args: list[str], env: dict = None, check: bool = True):
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True, text=True,
            check=check,
            env=env or dict(os.environ),
        )

    def test_help(self):
        """CLI exits 0 and shows usage."""
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "sumologic" in result.stdout.lower() or "Usage" in result.stdout

    def test_auth_status_json(self, tmp_session):
        """auth status --json returns valid JSON with expected keys."""
        result = self._run(["--json", "auth", "status"], env=tmp_session["env"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "endpoint" in data
        assert "access_id" in data
        print(f"\n  auth status: endpoint={data['endpoint']}")

    def test_search_run_messages_json(self, tmp_session):
        """search run in JSON mode returns parseable output."""
        result = self._run(
            ["--json", "search", "run", "* | limit 3", "--from", "-5m", "--to", "now"],
            env=tmp_session["env"],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "job_id" in data
        assert "is_aggregate" in data
        if not data["is_aggregate"]:
            assert "messages" in data
            print(f"\n  Messages returned: {len(data['messages'])}")
        print(f"  Job ID: {data['job_id']}, is_aggregate: {data['is_aggregate']}")

    def test_search_run_records_json(self, tmp_session):
        """Aggregate query returns records in JSON mode."""
        result = self._run(
            [
                "--json", "search", "run",
                "* | count by _sourceCategory | limit 3",
                "--from", "-1h", "--to", "now",
            ],
            env=tmp_session["env"],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "job_id" in data
        print(f"\n  Aggregate: is_aggregate={data['is_aggregate']}, "
              f"records={len(data.get('records', []))}")

    def test_search_save_and_replay(self, tmp_session):
        """Save a query then replay it — full end-to-end save/replay flow."""
        # Save
        result = self._run(
            ["--json", "search", "save", "test-query",
             "* | limit 2", "--from", "-5m", "--to", "now"],
            env=tmp_session["env"],
        )
        assert result.returncode == 0
        saved = json.loads(result.stdout)
        print(f"\n  Saved query: {saved}")

        # List saved
        result = self._run(["--json", "search", "saved"], env=tmp_session["env"])
        assert result.returncode == 0
        listed = json.loads(result.stdout)
        assert "test-query" in listed.get("saved_queries", {})

        # Replay
        result = self._run(
            ["--json", "search", "replay", "test-query"],
            env=tmp_session["env"],
        )
        assert result.returncode == 0
        replay_data = json.loads(result.stdout)
        assert "job_id" in replay_data
        print(f"  Replay job_id: {replay_data['job_id']}")

    def test_search_history(self, tmp_session):
        """After a search, history shows the query."""
        # Run a search first
        self._run(
            ["--json", "search", "run", "* | limit 1", "--from", "-5m"],
            env=tmp_session["env"],
        )
        # Check history
        result = self._run(
            ["--json", "search", "history", "--limit", "5"],
            env=tmp_session["env"],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "history" in data
        print(f"\n  History entries: {len(data['history'])}")

    def test_session_info_json(self, tmp_session):
        """session info --json returns expected keys."""
        result = self._run(
            ["--json", "session", "info"],
            env=tmp_session["env"],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for key in ("endpoint", "access_id", "timezone", "history_count"):
            assert key in data, f"Missing key: {key}"
        print(f"\n  Session info: {data}")

    def test_search_dry_run(self, tmp_session):
        """--dry-run shows params without executing the search."""
        result = self._run(
            ["--json", "search", "run", "error | count", "--dry-run",
             "--from", "-1h", "--to", "now"],
            env=tmp_session["env"],
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "query" in data
        assert data["query"] == "error | count"
        assert "job_id" not in data  # no actual job created
        print(f"\n  Dry-run params: {data}")
