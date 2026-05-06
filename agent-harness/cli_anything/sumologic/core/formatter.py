"""Output formatting for Sumo Logic search results."""

import json
from typing import Any

# TOON truncation limits — tune via constants to balance detail vs token cost.
_TOON_MAX_STR = 500
_TOON_MAX_LIST = 20
_TOON_MAX_DICT = 30


def _truncate(value: str, max_len: int = 120) -> str:
    if len(value) > max_len:
        return value[:max_len] + "…"
    return value


def _deep_truncate(
    value: Any,
    max_str: int = _TOON_MAX_STR,
    max_list: int = _TOON_MAX_LIST,
    max_dict: int = _TOON_MAX_DICT,
) -> Any:
    """Recursively truncate large strings, lists, and dicts for token efficiency."""
    if isinstance(value, str):
        if len(value) > max_str:
            return value[:max_str] + f" ...[{len(value) - max_str} chars truncated]"
        return value
    if isinstance(value, list):
        result = [_deep_truncate(v, max_str, max_list, max_dict) for v in value[:max_list]]
        if len(value) > max_list:
            result.append(f"[{len(value) - max_list} more items]")
        return result
    if isinstance(value, dict):
        keys = list(value.keys())[:max_dict]
        result = {k: _deep_truncate(value[k], max_str, max_list, max_dict) for k in keys}
        if len(value) > max_dict:
            result["__more__"] = f"{len(value) - max_dict} fields omitted"
        return result
    return value


def to_toon(data: Any) -> str:
    """Serialize to TOON (Token-Optimized Output Notation): compact JSON with truncation."""
    return json.dumps(_deep_truncate(data), separators=(",", ":"), default=str)


def format_messages_table(fields: list[dict], messages: list[dict]) -> str:
    """Format raw log messages as a plain-text table."""
    if not messages:
        return "(no messages)"
    lines = []
    for msg in messages:
        raw = msg.get("map", {}).get("_raw", "")
        ts = msg.get("map", {}).get("_messagetime", "")
        if ts:
            lines.append(f"[{ts}] {_truncate(raw)}")
        else:
            lines.append(_truncate(raw))
    return "\n".join(lines)


def format_records_table(fields: list[dict], records: list[dict]) -> str:
    """Format aggregate records as an ASCII table."""
    if not records:
        return "(no records)"

    field_names = [f["name"] for f in fields] if fields else []
    if not field_names and records:
        field_names = list(records[0].get("map", {}).keys())

    rows = []
    for rec in records:
        m = rec.get("map", {})
        rows.append([m.get(fn, "") for fn in field_names])

    col_widths = [max(len(fn), max((len(str(r[i])) for r in rows), default=0))
                  for i, fn in enumerate(field_names)]

    sep = "  ".join("-" * w for w in col_widths)
    header = "  ".join(fn.ljust(col_widths[i]) for i, fn in enumerate(field_names))

    lines = [header, sep]
    for row in rows:
        lines.append("  ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row)))
    return "\n".join(lines)


def format_status(status: dict[str, Any]) -> str:
    """Format a job status dict for display."""
    state = status.get("state", "unknown")
    msg_count = status.get("messageCount", 0)
    rec_count = status.get("recordCount", 0)
    errors = status.get("pendingErrors", [])
    warnings = status.get("pendingWarnings", [])
    lines = [
        f"State:    {state}",
        f"Messages: {msg_count}",
        f"Records:  {rec_count}",
    ]
    if errors:
        lines.append(f"Errors:   {len(errors)}")
    if warnings:
        lines.append(f"Warnings: {len(warnings)}")
    return "\n".join(lines)


def format_histogram(status: dict[str, Any]) -> str:
    """Render a mini histogram of message distribution over time."""
    buckets = status.get("histogramBuckets", [])
    if not buckets:
        return "(no histogram data)"
    max_count = max(b.get("count", 0) for b in buckets) or 1
    bar_width = 30
    lines = []
    for b in buckets:
        count = b.get("count", 0)
        filled = int(bar_width * count / max_count)
        bar = "█" * filled + "░" * (bar_width - filled)
        lines.append(f"  {bar}  {count:6d}")
    return "\n".join(lines)


def to_json(data: Any) -> str:
    """Serialize data to JSON string."""
    return json.dumps(data, indent=2, default=str)


def message_to_dict(msg: dict) -> dict:
    """Normalize a Sumo Logic message object to a flat dict."""
    return msg.get("map", msg)


def record_to_dict(rec: dict) -> dict:
    """Normalize a Sumo Logic record object to a flat dict."""
    return rec.get("map", rec)
