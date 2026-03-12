#!/usr/bin/env python3
"""
Reads OpenCode session logs for a given agent from the SQLite database.

Storage: ~/.local/share/opencode/opencode.db
  - session table: id, title, directory, time_updated, data (JSON)
  - message table: session_id, time_created, data (JSON with role, tokens, agent)
  - part table: message_id, session_id, data (JSON with type, text)

Usage:
    python read_logs.py --agent DEV_<name> [--last N] [--session-id <id>]
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def open_db() -> sqlite3.Connection:
    # Try both Unix and Windows path styles
    for path in [DB_PATH, Path(str(DB_PATH).replace("/c/Users", "C:/Users"))]:
        if path.exists():
            return sqlite3.connect(str(path))
    # Fallback: try Windows AppData
    alt = Path.home() / "AppData" / "Local" / "opencode" / "opencode.db"
    if alt.exists():
        return sqlite3.connect(str(alt))
    print(f"opencode.db not found. Tried: {DB_PATH}", file=sys.stderr)
    sys.exit(1)


def get_sessions(conn: sqlite3.Connection, agent_name: str, last_n: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, directory, time_updated FROM session ORDER BY time_updated DESC LIMIT 200"
    ).fetchall()

    matched = []
    for sid, title, directory, ts in rows:
        # Check if any message in this session mentions our agent
        msgs = conn.execute(
            "SELECT data FROM message WHERE session_id=?", (sid,)
        ).fetchall()
        for (mdata,) in msgs:
            d = json.loads(mdata)
            if d.get("agent", "").lower() == agent_name.lower() or \
               d.get("mode", "").lower() == agent_name.lower():
                matched.append({"id": sid, "title": title, "directory": directory, "ts": ts})
                break
        if len(matched) >= last_n:
            break

    return matched


def summarize_session(conn: sqlite3.Connection, sid: str, agent_name: str) -> dict:
    msgs = conn.execute(
        "SELECT id, data FROM message WHERE session_id=? ORDER BY time_created", (sid,)
    ).fetchall()

    tool_calls = []
    mock_calls = []
    errors = []
    final_response = None
    step_count = 0
    total_tokens = {"input": 0, "output": 0}

    for msg_id, mdata in msgs:
        msg = json.loads(mdata)
        role = msg.get("role", "")
        tokens = msg.get("tokens") or {}
        total_tokens["input"] += tokens.get("input", 0)
        total_tokens["output"] += tokens.get("output", 0)

        parts = conn.execute(
            "SELECT data FROM part WHERE message_id=? ORDER BY rowid", (msg_id,)
        ).fetchall()

        for (pdata,) in parts:
            p = json.loads(pdata)
            ptype = p.get("type", "")
            text = p.get("text", "")

            if ptype == "tool-input":
                name = p.get("toolName", p.get("name", ""))
                inp = p.get("input", {})
                step_count += 1
                if name.startswith("mock_"):
                    mock_calls.append({"tool": name, "prompt": inp.get("prompt", str(inp))[:300]})
                else:
                    tool_calls.append({"tool": name, "input_summary": str(inp)[:200]})

            elif ptype == "text" and role == "assistant" and text.strip():
                final_response = text.strip()[:1000]

            elif ptype == "error":
                errors.append(text[:300])

    return {
        "agent": agent_name,
        "steps": step_count,
        "total_tokens": total_tokens,
        "tool_calls": tool_calls,
        "mock_calls": mock_calls,
        "errors": errors,
        "final_response": final_response,
    }


def print_summary(summary: dict, session: dict):
    print(f"\n{'='*60}")
    print(f"Session: {session['id']}")
    print(f"Title:   {session['title']}")
    print(f"Agent:   {summary['agent']}")
    print(f"Steps:   {summary['steps']}")
    print(f"Tokens:  input={summary['total_tokens']['input']}  output={summary['total_tokens']['output']}")
    print()

    if summary["mock_calls"]:
        print(f"Mock tool calls ({len(summary['mock_calls'])}):")
        for c in summary["mock_calls"]:
            print(f"  [{c['tool']}] {c['prompt']!r}")
    else:
        print("Mock tool calls: none")

    if summary["tool_calls"]:
        print(f"\nOther tool calls ({len(summary['tool_calls'])}):")
        for c in summary["tool_calls"]:
            print(f"  [{c['tool']}] {c['input_summary']}")

    if summary["errors"]:
        print(f"\nErrors ({len(summary['errors'])}):")
        for e in summary["errors"]:
            print(f"  ! {e}")

    if summary["final_response"]:
        print(f"\nFinal response:")
        print(f"  {summary['final_response']}")
    else:
        print("\nFinal response: (none found)")

    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="Agent name (e.g. DEV_sum-specialist)")
    parser.add_argument("--last", type=int, default=1, help="Number of recent matching sessions")
    parser.add_argument("--session-id", help="Inspect a specific session by ID")
    args = parser.parse_args()

    conn = open_db()

    if args.session_id:
        row = conn.execute(
            "SELECT id, title, directory, time_updated FROM session WHERE id=?", (args.session_id,)
        ).fetchone()
        if not row:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)
        s = {"id": row[0], "title": row[1], "directory": row[2], "ts": row[3]}
        summary = summarize_session(conn, s["id"], args.agent)
        print_summary(summary, s)
        return

    sessions = get_sessions(conn, args.agent, args.last)
    if not sessions:
        print(f"No sessions found for agent '{args.agent}'.", file=sys.stderr)
        print("Run: opencode run --agent DEV_<name> \"<prompt>\" in a terminal first.", file=sys.stderr)
        sys.exit(1)

    for s in sessions:
        summary = summarize_session(conn, s["id"], args.agent)
        print_summary(summary, s)

    conn.close()


if __name__ == "__main__":
    main()
