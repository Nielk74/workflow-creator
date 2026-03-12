#!/usr/bin/env python3
"""
Captures real agent responses from the SQLite DB and saves them as mock_responses
in workflow.yml, ready for use when testing agents that call this one.

Workflow:
  1. Run a leaf agent several times with realistic prompts (opencode run --agent <name> "...")
  2. Run this script — it reads the last N sessions for that agent
  3. It writes the captured responses into workflow.yml mock_responses

Usage:
    python capture_responses.py --agent <name> --workflow <path> [--last N]

Options:
    --last N    Number of recent sessions to capture from (default: 3)
    --dry-run   Print what would be written without modifying workflow.yml
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def open_db() -> sqlite3.Connection:
    for path in [DB_PATH, Path(str(DB_PATH).replace("/c/Users", "C:/Users"))]:
        if path.exists():
            return sqlite3.connect(str(path))
    print(f"opencode.db not found: {DB_PATH}", file=sys.stderr)
    sys.exit(1)


def get_sessions(conn: sqlite3.Connection, agent_name: str, last_n: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title FROM session ORDER BY time_updated DESC LIMIT 200"
    ).fetchall()

    matched = []
    for sid, title in rows:
        msgs = conn.execute("SELECT data FROM message WHERE session_id=?", (sid,)).fetchall()
        for (mdata,) in msgs:
            d = json.loads(mdata)
            if d.get("agent", "").lower() == agent_name.lower() or \
               d.get("mode", "").lower() == agent_name.lower():
                matched.append({"id": sid, "title": title})
                break
        if len(matched) >= last_n:
            break

    return matched


def extract_response(conn: sqlite3.Connection, sid: str) -> tuple[str, str]:
    """Returns (user_prompt, assistant_response) for a session."""
    msgs = conn.execute(
        "SELECT id, data FROM message WHERE session_id=? ORDER BY time_created", (sid,)
    ).fetchall()

    user_prompt = ""
    assistant_response = ""

    for msg_id, mdata in msgs:
        msg = json.loads(mdata)
        role = msg.get("role", "")

        parts = conn.execute(
            "SELECT data FROM part WHERE message_id=? ORDER BY rowid", (msg_id,)
        ).fetchall()

        for (pdata,) in parts:
            p = json.loads(pdata)
            text = p.get("text", "").strip()
            if not text:
                continue
            if role == "user" and not user_prompt:
                # Strip surrounding quotes added by opencode run
                user_prompt = text.strip('"').strip()
            elif role == "assistant" and p.get("type") == "text":
                assistant_response = text  # take the last text part

    return user_prompt, assistant_response


def update_workflow(workflow_path: str, agent_name: str, captures: list[dict], dry_run: bool):
    """Write captured responses into workflow.yml mock_responses."""
    path = Path(workflow_path)
    with open(path) as f:
        wf = yaml.safe_load(f)

    mock_responses = wf.setdefault("mock_responses", {})
    entries = []

    for cap in captures:
        if not cap["response"]:
            continue
        # Build a trigger from the prompt — use a keyword excerpt (first 4 meaningful words)
        words = re.findall(r'\b\w{4,}\b', cap["prompt"].lower())
        trigger = "|".join(f".*{w}.*" for w in words[:3]) if words else ".*"
        entries.append({
            "trigger": trigger,
            "response": cap["response"]
        })

    # Always add a catch-all using the last captured response
    if entries:
        last_response = entries[-1]["response"]
        # Remove duplicates of catch-all
        entries = [e for e in entries if e["trigger"] != ".*"]
        entries.append({"trigger": ".*", "response": last_response})

    if not entries:
        print(f"No responses captured for '{agent_name}' — nothing to write.")
        return

    mock_responses[agent_name] = entries

    if dry_run:
        print(f"\n[DRY RUN] Would write to mock_responses.{agent_name}:\n")
        for e in entries:
            print(f"  trigger: {e['trigger']}")
            print(f"  response: {e['response'][:120]}...")
            print()
        return

    with open(path, "w") as f:
        yaml.dump(wf, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Written {len(entries)} mock response(s) for '{agent_name}' to {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="Agent name whose responses to capture")
    parser.add_argument("--workflow", required=True, help="Path to workflow.yml")
    parser.add_argument("--last", type=int, default=3, help="Number of recent sessions to capture")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    conn = open_db()
    sessions = get_sessions(conn, args.agent, args.last)

    if not sessions:
        print(f"No sessions found for agent '{args.agent}'.")
        print(f"Run it first: opencode run --agent {args.agent} \"<prompt>\"")
        sys.exit(1)

    captures = []
    for s in sessions:
        prompt, response = extract_response(conn, s["id"])
        if response:
            captures.append({"session": s["id"], "prompt": prompt, "response": response})
            print(f"Captured from '{s['title']}': {response[:80]}...")
        else:
            print(f"Skipped '{s['title']}': no assistant response found")

    conn.close()

    if not captures:
        print("No usable responses found. Make sure the agent sessions completed successfully.")
        sys.exit(1)

    update_workflow(args.workflow, args.agent, captures, args.dry_run)


if __name__ == "__main__":
    main()
