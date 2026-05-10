"""Sumo Logic search job lifecycle: create, poll, fetch, delete."""

import time
from typing import Any, Optional

from cli_anything.sumologic.utils.sumologic_backend import SumoLogicClient


DEFAULT_POLL_INTERVAL = 1.0  # seconds between status checks
DEFAULT_TIMEOUT = 300.0      # 5 minute hard timeout
DEFAULT_PAGE_LIMIT = 100     # results per page


def create_job(
    client: SumoLogicClient,
    query: str,
    from_time: str,
    to_time: str,
    timezone: str = "UTC",
) -> str:
    """Create a search job and return its ID."""
    job = client.create_job(query, from_time, to_time, timezone)
    return job["id"]


def wait_for_job(
    client: SumoLogicClient,
    job_id: str,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Poll job status until done or timed out. Returns final status dict."""
    deadline = time.monotonic() + timeout
    while True:
        status = client.get_status(job_id)
        state = status.get("state", "")
        if state == "DONE GATHERING RESULTS":
            return status
        if state in ("CANCELLED", "FORCE PAUSED"):
            raise RuntimeError(f"Search job {job_id} ended with state: {state}")
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Search job {job_id} timed out after {timeout:.0f}s "
                f"(last state: {state})"
            )
        time.sleep(poll_interval)


def fetch_messages(
    client: SumoLogicClient,
    job_id: str,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Fetch a page of raw log messages from a completed job."""
    return client.get_messages(job_id, limit=limit, offset=offset)


def fetch_records(
    client: SumoLogicClient,
    job_id: str,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Fetch a page of aggregate records from a completed job."""
    return client.get_records(job_id, limit=limit, offset=offset)


def fetch_all_messages(
    client: SumoLogicClient,
    job_id: str,
    status: dict[str, Any],
    limit: int = DEFAULT_PAGE_LIMIT,
    max_messages: Optional[int] = None,
) -> list[dict]:
    """Fetch all messages across pages, up to max_messages."""
    total = status.get("messageCount", 0)
    if max_messages is not None:
        total = min(total, max_messages)
    messages: list[dict] = []
    offset = 0
    while offset < total:
        page_limit = min(limit, total - offset)
        result = fetch_messages(client, job_id, limit=page_limit, offset=offset)
        page = result.get("messages", [])
        messages.extend(page)
        offset += len(page)
        if not page:
            break
    return messages


def fetch_all_records(
    client: SumoLogicClient,
    job_id: str,
    status: dict[str, Any],
    limit: int = DEFAULT_PAGE_LIMIT,
    max_records: Optional[int] = None,
) -> tuple[list[dict], list[dict]]:
    """Fetch all records across pages. Returns (fields, records)."""
    total = status.get("recordCount", 0)
    if max_records is not None:
        total = min(total, max_records)
    all_records: list[dict] = []
    fields: list[dict] = []
    offset = 0
    while offset < total:
        page_limit = min(limit, total - offset)
        result = fetch_records(client, job_id, limit=page_limit, offset=offset)
        if not fields:
            fields = result.get("fields", [])
        page = result.get("records", [])
        all_records.extend(page)
        offset += len(page)
        if not page:
            break
    return fields, all_records


def delete_job(client: SumoLogicClient, job_id: str) -> None:
    """Delete/cancel a search job."""
    client.delete_job(job_id)


def run_search(
    client: SumoLogicClient,
    query: str,
    from_time: str,
    to_time: str,
    timezone: str = "UTC",
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    timeout: float = DEFAULT_TIMEOUT,
    max_results: Optional[int] = None,
    cleanup: bool = True,
) -> dict[str, Any]:
    """End-to-end search: create → poll → fetch → delete.

    Returns a result dict with keys:
        job_id, status, fields, messages, records, is_aggregate
    """
    job_id = create_job(client, query, from_time, to_time, timezone)
    try:
        status = wait_for_job(client, job_id, poll_interval, timeout)
        is_aggregate = status.get("recordCount", 0) > 0

        fields: list[dict] = []
        messages: list[dict] = []
        records: list[dict] = []

        if is_aggregate:
            fields, records = fetch_all_records(
                client, job_id, status, max_records=max_results
            )
        else:
            raw = fetch_messages(
                client, job_id,
                limit=max_results or DEFAULT_PAGE_LIMIT,
                offset=0,
            )
            fields = raw.get("fields", [])
            messages = raw.get("messages", [])

        return {
            "job_id": job_id,
            "status": status,
            "fields": fields,
            "messages": messages,
            "records": records,
            "is_aggregate": is_aggregate,
        }
    finally:
        if cleanup:
            try:
                delete_job(client, job_id)
            except Exception:
                pass
