"""Session management for Sumo Logic CLI — credentials, history, saved queries."""

import json
import os
from pathlib import Path
from typing import Any, Optional


DEFAULT_SESSION_DIR = Path.home() / ".cli-anything-sumologic"
DEFAULT_SESSION_FILE = DEFAULT_SESSION_DIR / "session.json"

_EMPTY_SESSION: dict[str, Any] = {
    "endpoint": "",
    "access_id": "",
    "access_key": "",
    "timezone": "UTC",
    "current_job_id": None,
    "query_history": [],
    "saved_queries": {},
}


def _locked_save_json(path: Path, data: dict, **dump_kwargs) -> None:
    """Atomically write JSON with exclusive file locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        f = open(path, "r+")
    except FileNotFoundError:
        f = open(path, "w")
    with f:
        _locked = False
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            _locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2, **dump_kwargs)
            f.flush()
        finally:
            if _locked:
                import fcntl as _fcntl
                _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)


def load_session(path: Optional[Path] = None) -> dict[str, Any]:
    """Load session from disk, returning defaults if not found."""
    session_path = path or DEFAULT_SESSION_FILE
    if not session_path.exists():
        return dict(_EMPTY_SESSION)
    with open(session_path) as f:
        data = json.load(f)
    merged = dict(_EMPTY_SESSION)
    merged.update(data)
    return merged


def save_session(session: dict[str, Any], path: Optional[Path] = None) -> None:
    """Persist session to disk with file locking."""
    session_path = path or DEFAULT_SESSION_FILE
    _locked_save_json(session_path, session)


def get_credentials(session: dict[str, Any]) -> tuple[str, str, str]:
    """Return (endpoint, access_id, access_key) from session or env vars."""
    endpoint = (
        os.environ.get("SUMO_ENDPOINT")
        or session.get("endpoint")
        or ""
    )
    access_id = (
        os.environ.get("SUMO_ACCESS_ID")
        or session.get("access_id")
        or ""
    )
    access_key = (
        os.environ.get("SUMO_ACCESS_KEY")
        or session.get("access_key")
        or ""
    )
    return endpoint, access_id, access_key


def validate_credentials(session: dict[str, Any]) -> None:
    """Raise RuntimeError if credentials are missing."""
    endpoint, access_id, access_key = get_credentials(session)
    missing = []
    if not endpoint:
        missing.append("endpoint (set SUMO_ENDPOINT or run: auth configure)")
    if not access_id:
        missing.append("access_id (set SUMO_ACCESS_ID or run: auth configure)")
    if not access_key:
        missing.append("access_key (set SUMO_ACCESS_KEY or run: auth configure)")
    if missing:
        raise RuntimeError(
            "Missing Sumo Logic credentials:\n  " + "\n  ".join(missing)
        )


def add_to_history(session: dict[str, Any], query: str, time_range: dict) -> None:
    """Append a query to the session history (max 50 entries)."""
    entry = {"query": query, "time_range": time_range}
    history: list = session.setdefault("query_history", [])
    history.append(entry)
    if len(history) > 50:
        session["query_history"] = history[-50:]


def save_query(session: dict[str, Any], name: str, query: str, time_range: dict) -> None:
    """Save a named query to the session."""
    session.setdefault("saved_queries", {})[name] = {
        "query": query,
        "time_range": time_range,
    }


def delete_saved_query(session: dict[str, Any], name: str) -> bool:
    """Remove a named query. Returns True if it existed."""
    queries = session.get("saved_queries", {})
    if name in queries:
        del queries[name]
        return True
    return False


def get_session_info(session: dict[str, Any]) -> dict[str, Any]:
    """Return a summary of session state suitable for display."""
    endpoint, access_id, _ = get_credentials(session)
    return {
        "endpoint": endpoint or "(not configured)",
        "access_id": access_id or "(not configured)",
        "timezone": session.get("timezone", "UTC"),
        "current_job_id": session.get("current_job_id"),
        "history_count": len(session.get("query_history", [])),
        "saved_queries_count": len(session.get("saved_queries", {})),
    }
