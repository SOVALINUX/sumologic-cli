"""cli-anything-sumologic — CLI harness for Sumo Logic log search API."""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

from cli_anything.sumologic.core import session as sess_mod
from cli_anything.sumologic.core import search as search_mod
from cli_anything.sumologic.core import formatter as fmt
from cli_anything.sumologic.core.timeutil import parse_time
from cli_anything.sumologic.utils.sumologic_backend import make_client
from cli_anything.sumologic.utils.repl_skin import ReplSkin

VERSION = "1.0.0"

_skin = ReplSkin("sumologic", version=VERSION)

# ── Shared context helpers ────────────────────────────────────────────


def _load_session(ctx: click.Context) -> dict:
    return ctx.obj.get("session", {})


def _save(ctx: click.Context, session: dict) -> None:
    sess_mod.save_session(session)
    ctx.obj["session"] = session


def _get_client(session: dict):
    endpoint, access_id, access_key = sess_mod.get_credentials(session)
    return make_client(endpoint, access_id, access_key)


def _out(output_format: str, data, human_text: str):
    if output_format == "json":
        click.echo(fmt.to_json(data))
    elif output_format == "toon":
        click.echo(fmt.to_toon(data))
    else:
        click.echo(human_text)


# ── Root group ────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--format", "output_format",
              type=click.Choice(["text", "json", "toon"], case_sensitive=False),
              default="toon", show_default=True,
              help="Output format. toon = compact JSON with truncation (token-efficient).")
@click.option("--json", "force_json", is_flag=True, default=False, hidden=True,
              help="Alias for --format=json (backward compat).")
@click.pass_context
def cli(ctx: click.Context, output_format: str, force_json: bool):
    """cli-anything-sumologic — Sumo Logic log search CLI.

    Run without subcommands to enter the interactive REPL.
    Set SUMO_ACCESS_ID, SUMO_ACCESS_KEY, SUMO_ENDPOINT to configure credentials.
    """
    ctx.ensure_object(dict)
    if force_json:
        output_format = "json"
    ctx.obj["output_format"] = output_format
    ctx.obj["session"] = sess_mod.load_session()

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ── auth group ────────────────────────────────────────────────────────


@cli.group()
@click.pass_context
def auth(ctx: click.Context):
    """Configure Sumo Logic credentials."""


@auth.command("configure")
@click.option("--endpoint", prompt="Sumo Logic endpoint",
              help="e.g. https://api.us2.sumologic.com/api/v1")
@click.option("--access-id", prompt="Access ID", help="Sumo Logic Access ID")
@click.option("--access-key", prompt="Access Key", hide_input=True,
              help="Sumo Logic Access Key")
@click.option("--timezone", default="UTC", show_default=True,
              help="Default timezone for searches")
@click.pass_context
def auth_configure(ctx: click.Context, endpoint: str, access_id: str,
                   access_key: str, timezone: str):
    """Save credentials to the local session file."""
    session = _load_session(ctx)
    session["endpoint"] = endpoint.rstrip("/")
    session["access_id"] = access_id
    session["access_key"] = access_key
    session["timezone"] = timezone
    _save(ctx, session)

    output_format = ctx.obj.get("output_format", "toon")
    _out(output_format, {"status": "ok", "endpoint": endpoint}, "")
    if output_format == "text":
        _skin.success("Credentials saved.")
        _skin.info(f"Endpoint: {endpoint}")


@auth.command("status")
@click.pass_context
def auth_status(ctx: click.Context):
    """Show current credential configuration."""
    session = _load_session(ctx)
    info = sess_mod.get_session_info(session)
    output_format = ctx.obj.get("output_format", "toon")
    if output_format == "text":
        for k, v in info.items():
            _skin.status(k, str(v))
    else:
        _out(output_format, info, "")


@auth.command("test")
@click.pass_context
def auth_test(ctx: click.Context):
    """Test credentials by making a minimal API call."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    try:
        sess_mod.validate_credentials(session)
        client = _get_client(session)
        job_id = search_mod.create_job(
            client, "* | limit 1",
            from_time=parse_time("-5m"), to_time=parse_time("now"),
            timezone=session.get("timezone", "UTC"),
        )
        search_mod.delete_job(client, job_id)
        _out(output_format, {"status": "ok"}, "")
        if output_format == "text":
            _skin.success("Credentials are valid.")
    except Exception as e:
        _out(output_format, {"status": "error", "message": str(e)}, "")
        if output_format == "text":
            _skin.error(str(e))
        sys.exit(1)


# ── search group ──────────────────────────────────────────────────────


@cli.group()
@click.pass_context
def search(ctx: click.Context):
    """Run log searches against Sumo Logic."""


@search.command("run")
@click.argument("query")
@click.option("--from", "from_time", default="-15m", show_default=True,
              help="Start time. ISO8601 or relative like -1h, -24h.")
@click.option("--to", "to_time", default="now", show_default=True,
              help="End time. ISO8601 or 'now'.")
@click.option("--timezone", default=None, help="Override session timezone.")
@click.option("--limit", default=100, show_default=True,
              help="Max results to return.")
@click.option("--timeout", default=300.0, show_default=True,
              help="Job timeout in seconds.")
@click.option("--save-as", default=None, metavar="NAME",
              help="Save this query under NAME for reuse.")
@click.option("--dry-run", is_flag=True, help="Show query params; don't execute.")
@click.pass_context
def search_run(ctx: click.Context, query: str, from_time: str, to_time: str,
               timezone: Optional[str], limit: int, timeout: float,
               save_as: Optional[str], dry_run: bool):
    """Execute a Sumo Logic search query and display results.

    QUERY is a Sumo Logic query string, e.g. 'error | count by _sourceCategory'
    """
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    tz = timezone or session.get("timezone", "UTC")
    from_iso = parse_time(from_time)
    to_iso = parse_time(to_time)
    time_range = {"from": from_time, "to": to_time}

    if dry_run:
        params = {
            "query": query,
            "from": from_iso,
            "to": to_iso,
            "timezone": tz,
            "limit": limit,
            "timeout": timeout,
        }
        _out(output_format, params, fmt.to_json(params))
        return

    try:
        sess_mod.validate_credentials(session)
    except RuntimeError as e:
        _skin.error(str(e))
        sys.exit(1)

    if output_format == "text":
        _skin.info(f"Running search: {query[:80]}")

    try:
        client = _get_client(session)
        result = search_mod.run_search(
            client, query, from_iso, to_iso,
            timezone=tz,
            timeout=timeout,
            max_results=limit,
        )
    except Exception as e:
        _out(output_format, {"error": str(e)}, "")
        if output_format == "text":
            _skin.error(str(e))
        sys.exit(1)

    sess_mod.add_to_history(session, query, time_range)
    if save_as:
        sess_mod.save_query(session, save_as, query, time_range)
    _save(ctx, session)

    if output_format != "text":
        output = {
            "job_id": result["job_id"],
            "is_aggregate": result["is_aggregate"],
            "message_count": result["status"].get("messageCount", 0),
            "record_count": result["status"].get("recordCount", 0),
            "fields": result["fields"],
        }
        if result["is_aggregate"]:
            output["records"] = [fmt.record_to_dict(r) for r in result["records"]]
        else:
            output["messages"] = [fmt.message_to_dict(m) for m in result["messages"]]
        _out(output_format, output, "")
    else:
        status = result["status"]
        if result["is_aggregate"]:
            _skin.info(
                f"Aggregate query — {status.get('recordCount', 0)} records"
            )
            click.echo(fmt.format_records_table(result["fields"], result["records"]))
        else:
            _skin.info(
                f"Log query — {status.get('messageCount', 0)} messages "
                f"(showing up to {limit})"
            )
            click.echo(fmt.format_messages_table(result["fields"], result["messages"]))


@search.command("history")
@click.option("--limit", default=10, show_default=True)
@click.pass_context
def search_history(ctx: click.Context, limit: int):
    """Show recent query history."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    history = session.get("query_history", [])[-limit:]
    if output_format != "text":
        _out(output_format, {"history": history}, "")
    else:
        if not history:
            _skin.info("No query history.")
        else:
            _skin.table(
                ["#", "Query", "From", "To"],
                [[str(i + 1), h["query"][:60],
                  h["time_range"].get("from", ""),
                  h["time_range"].get("to", "")]
                 for i, h in enumerate(history)],
            )


@search.command("saved")
@click.pass_context
def search_saved(ctx: click.Context):
    """List saved queries."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    saved = session.get("saved_queries", {})
    if output_format != "text":
        _out(output_format, {"saved_queries": saved}, "")
    else:
        if not saved:
            _skin.info("No saved queries.")
        else:
            _skin.table(
                ["Name", "Query", "From", "To"],
                [[name, q["query"][:60],
                  q["time_range"].get("from", ""),
                  q["time_range"].get("to", "")]
                 for name, q in saved.items()],
            )


@search.command("save")
@click.argument("name")
@click.argument("query")
@click.option("--from", "from_time", default="-15m", show_default=True)
@click.option("--to", "to_time", default="now", show_default=True)
@click.pass_context
def search_save(ctx: click.Context, name: str, query: str,
                from_time: str, to_time: str):
    """Save a named query for reuse."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    sess_mod.save_query(session, name, query, {"from": parse_time(from_time), "to": parse_time(to_time)})
    _save(ctx, session)
    _out(output_format, {"status": "ok", "name": name}, f"Saved query '{name}'.")
    if output_format == "text":
        _skin.success(f"Saved query '{name}'.")


@search.command("delete-saved")
@click.argument("name")
@click.pass_context
def search_delete_saved(ctx: click.Context, name: str):
    """Delete a saved query by name."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    removed = sess_mod.delete_saved_query(session, name)
    _save(ctx, session)
    if removed:
        _out(output_format, {"status": "ok", "name": name}, "")
        if output_format == "text":
            _skin.success(f"Deleted saved query '{name}'.")
    else:
        msg = f"No saved query named '{name}'."
        _out(output_format, {"status": "not_found", "name": name}, "")
        if output_format == "text":
            _skin.warning(msg)


@search.command("replay")
@click.argument("name")
@click.option("--limit", default=100, show_default=True)
@click.option("--timeout", default=300.0, show_default=True)
@click.pass_context
def search_replay(ctx: click.Context, name: str, limit: int, timeout: float):
    """Run a previously saved query by name."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    saved = session.get("saved_queries", {})
    if name not in saved:
        msg = f"No saved query named '{name}'. Run 'search saved' to list them."
        _out(output_format, {"error": msg}, "")
        if output_format == "text":
            _skin.error(msg)
        sys.exit(1)
    entry = saved[name]
    ctx.invoke(
        search_run,
        query=entry["query"],
        from_time=entry["time_range"].get("from", "-15m"),
        to_time=entry["time_range"].get("to", "now"),
        timezone=None,
        limit=limit,
        timeout=timeout,
        save_as=None,
        dry_run=False,
    )


# ── job group ─────────────────────────────────────────────────────────


@cli.group()
@click.pass_context
def job(ctx: click.Context):
    """Manage Sumo Logic search jobs directly."""


@job.command("status")
@click.argument("job_id")
@click.pass_context
def job_status(ctx: click.Context, job_id: str):
    """Get status of a search job by ID."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    try:
        client = _get_client(session)
        status = client.get_status(job_id)
        _out(output_format, status, fmt.format_status(status))
    except Exception as e:
        _skin.error(str(e))
        sys.exit(1)


@job.command("messages")
@click.argument("job_id")
@click.option("--limit", default=100, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.pass_context
def job_messages(ctx: click.Context, job_id: str, limit: int, offset: int):
    """Fetch messages from a completed search job."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    try:
        client = _get_client(session)
        result = client.get_messages(job_id, limit=limit, offset=offset)
        _out(output_format, result,
             fmt.format_messages_table(result.get("fields", []), result.get("messages", [])))
    except Exception as e:
        _skin.error(str(e))
        sys.exit(1)


@job.command("records")
@click.argument("job_id")
@click.option("--limit", default=100, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.pass_context
def job_records(ctx: click.Context, job_id: str, limit: int, offset: int):
    """Fetch aggregate records from a completed search job."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    try:
        client = _get_client(session)
        result = client.get_records(job_id, limit=limit, offset=offset)
        _out(output_format, result,
             fmt.format_records_table(result.get("fields", []), result.get("records", [])))
    except Exception as e:
        _skin.error(str(e))
        sys.exit(1)


@job.command("delete")
@click.argument("job_id")
@click.pass_context
def job_delete(ctx: click.Context, job_id: str):
    """Cancel and delete a search job."""
    session = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    try:
        client = _get_client(session)
        search_mod.delete_job(client, job_id)
        _out(output_format, {"status": "ok", "job_id": job_id}, "")
        if output_format == "text":
            _skin.success(f"Deleted job {job_id}.")
    except Exception as e:
        _skin.error(str(e))
        sys.exit(1)


# ── session group ─────────────────────────────────────────────────────


@cli.group()
@click.pass_context
def session(ctx: click.Context):
    """View and manage CLI session state."""


@session.command("info")
@click.pass_context
def session_info(ctx: click.Context):
    """Display current session info."""
    s = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    info = sess_mod.get_session_info(s)
    if output_format == "text":
        for k, v in info.items():
            _skin.status(k, str(v))
    else:
        _out(output_format, info, "")


@session.command("clear-history")
@click.pass_context
def session_clear_history(ctx: click.Context):
    """Clear query history."""
    s = _load_session(ctx)
    output_format = ctx.obj.get("output_format", "toon")
    s["query_history"] = []
    _save(ctx, s)
    _out(output_format, {"status": "ok"}, "")
    if output_format == "text":
        _skin.success("Query history cleared.")


# ── REPL ──────────────────────────────────────────────────────────────


@cli.command("repl")
@click.pass_context
def repl(ctx: click.Context):
    """Launch the interactive REPL."""
    _skin.print_banner()
    session = _load_session(ctx)
    endpoint, _, _ = sess_mod.get_credentials(session)

    # REPL is always human-readable regardless of --format flag.
    ctx.obj["output_format"] = "text"

    if not endpoint:
        _skin.warning(
            "No credentials configured. "
            "Run: auth configure  or set SUMO_ACCESS_ID / SUMO_ACCESS_KEY / SUMO_ENDPOINT"
        )

    commands = {
        "search run <query>": "Execute a Sumo Logic search",
        "search history": "Show recent queries",
        "search saved": "List saved queries",
        "search save <name> <query>": "Save a named query",
        "search replay <name>": "Re-run a saved query",
        "auth configure": "Set credentials",
        "auth status": "Show credential info",
        "auth test": "Verify credentials work",
        "job status <id>": "Get job status",
        "job messages <id>": "Fetch job messages",
        "job records <id>": "Fetch job records",
        "job delete <id>": "Delete a job",
        "session info": "Show session details",
        "session clear-history": "Clear query history",
        "help": "Show this help",
        "quit": "Exit",
    }

    pt_session = _skin.create_prompt_session()

    while True:
        try:
            line = _skin.get_input(
                pt_session,
                context="sumologic",
            )
        except (EOFError, KeyboardInterrupt):
            _skin.print_goodbye()
            break

        line = line.strip()
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            _skin.print_goodbye()
            break
        if line in ("help", "?", "h"):
            _skin.help(commands)
            continue

        args = line.split()
        try:
            ctx.obj["session"] = sess_mod.load_session()
            cli.main(
                args=args,
                obj=ctx.obj,
                standalone_mode=False,
            )
        except SystemExit:
            pass
        except click.exceptions.UsageError as e:
            _skin.error(str(e))
        except Exception as e:
            _skin.error(str(e))


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
