"""Output formatting for Sumo Logic search results."""

import json
import os
import re
from typing import Any

# ── Field truncation (independent of output format) ───────────────────
# Applied before serialization to keep payloads manageable.
# All three limits can be overridden via environment variables.

MAX_STR_LEN = int(os.environ.get("SUMO_TRUNCATE_STR", 2000))
# SUMO_TRUNCATE_STR  — max string length in chars before truncation (default 2000)

MAX_LIST_LEN = int(os.environ.get("SUMO_TRUNCATE_LIST", 20))
# SUMO_TRUNCATE_LIST — max items kept from any list (default 20)

MAX_DICT_KEYS = int(os.environ.get("SUMO_TRUNCATE_DICT", 30))
# SUMO_TRUNCATE_DICT — max keys kept from any dict (default 30)


def _truncate(value: str, max_len: int = 120) -> str:
    if len(value) > max_len:
        return value[:max_len] + "…"
    return value


def deep_truncate(
    value: Any,
    max_str: int = MAX_STR_LEN,
    max_list: int = MAX_LIST_LEN,
    max_dict: int = MAX_DICT_KEYS,
) -> Any:
    """Recursively truncate large strings, lists, and dicts.

    Strings longer than max_str get a trailing marker showing chars cut.
    Lists with more than max_list items get a sentinel as the last element.
    Dicts with more than max_dict keys get a __more__ sentinel key.
    """
    if isinstance(value, str):
        if len(value) > max_str:
            return value[:max_str] + f" ...[{len(value) - max_str} chars truncated]"
        return value
    if isinstance(value, list):
        result = [deep_truncate(v, max_str, max_list, max_dict) for v in value[:max_list]]
        if len(value) > max_list:
            result.append(f"[{len(value) - max_list} more items]")
        return result
    if isinstance(value, dict):
        keys = list(value.keys())[:max_dict]
        result = {k: deep_truncate(value[k], max_str, max_list, max_dict) for k in keys}
        if len(value) > max_dict:
            result["__more__"] = f"{len(value) - max_dict} fields omitted"
        return result
    return value


# ── TOON encoder (Token-Oriented Object Notation) ─────────────────────
# Spec: https://github.com/toon-format/spec  (v3.0, 2025-11-24)
#
# Key rules implemented:
#   - Objects: key: value pairs, one per line, indented for nesting
#   - Scalars: unquoted unless ambiguous (empty, numeric-looking, bool/null
#     literals, or contains delimiter / structural chars)
#   - Inline primitive array: key[N]: v1,v2,...
#   - Tabular array: key[N]{f1,f2,...}:\n  v1,v2\n  v3,v4
#     (only when all items are dicts with identical, all-primitive-valued keys)
#   - Non-uniform / nested arrays: key[N]: with indented "- " list items
#   - Indent: 2 spaces per level
#   - Delimiter: comma (default)

_INDENT = "  "
_DELIM = ","

# Patterns for mandatory quoting
_NEEDS_QUOTE_RE = re.compile(
    r'^$'                        # empty string
    r'|^[\s]|[\s]$'             # leading/trailing whitespace
    r'|^(true|false|null)$'     # boolean/null literals
    r'|^-?\d'                   # looks numeric
    r'|[:\[\]{}",\\]'           # structural chars
    r'|^- '                     # list marker prefix
)


def _is_primitive(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, str))


def _is_uniform_tabular(lst: list) -> bool:
    """True if list is non-empty, all items are dicts, same keys, all primitive values."""
    if not lst or not isinstance(lst[0], dict):
        return False
    keys = list(lst[0].keys())
    if not keys:
        return False
    for item in lst:
        if not isinstance(item, dict):
            return False
        if list(item.keys()) != keys:
            return False
        if not all(_is_primitive(v) for v in item.values()):
            return False
    return True


def _quote_scalar(v: Any) -> str:
    """Render a scalar as a TOON string value, quoting only when required."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        # Canonical number: no exponent, no leading zeros, no trailing frac zeros
        if isinstance(v, float):
            s = f"{v:.15g}"
        else:
            s = str(v)
        return s
    # String
    s = str(v)
    if _NEEDS_QUOTE_RE.search(s) or _DELIM in s:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{escaped}"'
    return s


def _encode_value(value: Any, depth: int, lines: list[str], prefix: str) -> None:
    """Recursively encode value, appending to lines. prefix is the key: part."""
    pad = _INDENT * depth

    if _is_primitive(value):
        lines.append(f"{pad}{prefix}{_quote_scalar(value)}")

    elif isinstance(value, dict):
        if prefix:
            lines.append(f"{pad}{prefix}")
        for k, v in value.items():
            _encode_value(v, depth + (1 if prefix else 0), lines, f"{k}: ")

    elif isinstance(value, list):
        n = len(value)
        if n == 0:
            lines.append(f"{pad}{prefix}[0]:")
        elif all(_is_primitive(item) for item in value):
            # Inline primitive array
            vals = _DELIM.join(_quote_scalar(item) for item in value)
            lines.append(f"{pad}{prefix}[{n}]: {vals}")
        elif _is_uniform_tabular(value):
            # Tabular array: one header, one CSV row per item
            keys = list(value[0].keys())
            header_fields = _DELIM.join(keys)
            lines.append(f"{pad}{prefix}[{n}]{{{header_fields}}}:")
            row_pad = _INDENT * (depth + 1)
            for item in value:
                row = _DELIM.join(_quote_scalar(item[k]) for k in keys)
                lines.append(f"{row_pad}{row}")
        else:
            # Non-uniform or nested items: list marker format
            lines.append(f"{pad}{prefix}[{n}]:")
            item_pad = _INDENT * (depth + 1)
            for item in value:
                if _is_primitive(item):
                    lines.append(f"{item_pad}- {_quote_scalar(item)}")
                elif isinstance(item, dict):
                    first = True
                    for k, v in item.items():
                        if first:
                            _encode_value(v, depth + 1, lines, f"- {k}: ")
                            first = False
                        else:
                            _encode_value(v, depth + 1, lines, f"{k}: ")
                else:
                    # Nested list as list item
                    lines.append(f"{item_pad}- ")
                    _encode_value(item, depth + 2, lines, "")


def to_toon(data: Any) -> str:
    """Encode data to TOON (Token-Oriented Object Notation) string.

    TOON uses YAML-like indentation for objects and CSV-style tabular rows
    for uniform arrays, eliminating repeated key names and most quoting.
    See https://toonformat.dev for the spec.
    """
    lines: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            _encode_value(v, 0, lines, f"{k}: ")
    elif isinstance(data, list):
        _encode_value(data, 0, lines, "")
    else:
        return _quote_scalar(data)
    return "\n".join(lines)


# ── JSON helpers ──────────────────────────────────────────────────────


def to_json(data: Any) -> str:
    """Serialize data to indented JSON string."""
    return json.dumps(data, indent=2, default=str)


# ── Human-readable formatters ─────────────────────────────────────────


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


def message_to_dict(msg: dict) -> dict:
    """Normalize a Sumo Logic message object to a flat dict."""
    return msg.get("map", msg)


def record_to_dict(rec: dict) -> dict:
    """Normalize a Sumo Logic record object to a flat dict."""
    return rec.get("map", rec)
