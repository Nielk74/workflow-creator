#!/usr/bin/env python3
"""
Parses OpenCode session logs for a given agent and outputs a structured summary.

Uses `opencode session list` and `opencode export <id>` to retrieve session data.

Usage:
    python read_logs.py --agent DEV_<name> [--last N] [--session-id <id>]
"""

import argparse
import json
import re
import subprocess
import sys


def run_cmd(args: list) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout.strip()


def list_sessions() -> list[dict]:
    """Get sessions via `opencode session list` — output is plain text, parse it."""
    raw = run_cmd(["opencode", "session", "list"])
    if not raw or "No sessions" in raw:
        return []

    sessions = []
    # Try JSON first
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Parse plain text lines: look for session IDs (typically UUIDs or short hashes)
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Match lines that contain a session ID pattern
        match = re.search(r'([a-f0-9\-]{8,})', line, re.IGNORECASE)
        if match:
            sessions.append({"id": match.group(1), "raw": line})

    return sessions


def export_session(session_id: str) -> dict | None:
    """Export a session as JSON via `opencode export <id>`."""
    raw = run_cmd(["opencode", "export", session_id])
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Sometimes export writes to a file — check if it printed a path
        path_match = re.search(r'[\w/\\:.-]+\.json', raw)
        if path_match:
            try:
                with open(path_match.group(0)) as f:
                    return json.load(f)
            except Exception:
                pass
        print(f"Warning: could not parse export output for session {session_id}", file=sys.stderr)
        return None


def session_mentions_agent(session: dict, agent_name: str) -> bool:
    """Check if a session involves the given agent."""
    text = json.dumps(session).lower()
    return agent_name.lower() in text


def summarize_session(session: dict, agent_name: str) -> dict:
    """Extract meaningful signal from an exported session."""
    tool_calls = []
    mock_calls = []
    errors = []
    final_response = None
    step_count = 0

    # Session export structure varies — handle common shapes
    messages = session.get("messages", session.get("turns", session.get("events", [])))
    if isinstance(session, list):
        messages = session

    for msg in messages:
        role = msg.get("role", msg.get("type", ""))
        content = msg.get("content", "")

        # Tool use blocks
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    step_count += 1
                    if name.startswith("mock_"):
                        mock_calls.append({
                            "tool": name,
                            "prompt": inp.get("prompt", str(inp))[:300]
                        })
                    else:
                        tool_calls.append({
                            "tool": name,
                            "input_summary": str(inp)[:200]
                        })
                elif btype == "text" and role == "assistant":
                    text = block.get("text", "")
                    if len(text) > 20:
                        final_response = text[:1000]

        # Plain text assistant message
        elif role == "assistant" and isinstance(content, str) and len(content) > 20:
            final_response = content[:1000]

        # Error events
        if role == "error" or "error" in str(msg).lower()[:80]:
            errors.append(str(msg)[:300])

    return {
        "agent": agent_name,
        "steps": step_count,
        "tool_calls": tool_calls,
        "mock_calls": mock_calls,
        "errors": errors,
        "final_response": final_response,
    }


def print_summary(summary: dict, session_id: str):
    print(f"\n{'='*60}")
    print(f"Session: {session_id}")
    print(f"Agent:   {summary['agent']}")
    print(f"Steps:   {summary['steps']}")
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
        print(f"\nFinal response (truncated at 1000 chars):")
        print(f"  {summary['final_response']}")
    else:
        print("\nFinal response: (not found in export)")

    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="Agent name to filter for (e.g. DEV_analyzer)")
    parser.add_argument("--last", type=int, default=1, help="Number of most recent matching sessions to show")
    parser.add_argument("--session-id", help="Export a specific session by ID")
    args = parser.parse_args()

    if args.session_id:
        session = export_session(args.session_id)
        if not session:
            print(f"Could not export session {args.session_id}", file=sys.stderr)
            sys.exit(1)
        summary = summarize_session(session, args.agent)
        print_summary(summary, args.session_id)
        return

    sessions = list_sessions()
    if not sessions:
        print("No sessions found. Run a test first with:", file=sys.stderr)
        print(f"  opencode run --agent DEV_{args.agent} \"<test prompt>\"", file=sys.stderr)
        sys.exit(1)

    matched = 0
    for s in sessions:
        sid = s.get("id", s.get("sessionId", "unknown"))
        session_data = export_session(sid)
        if session_data is None:
            continue
        if not session_mentions_agent(session_data, args.agent):
            continue
        summary = summarize_session(session_data, args.agent)
        print_summary(summary, sid)
        matched += 1
        if matched >= args.last:
            break

    if matched == 0:
        print(f"No sessions found mentioning agent '{args.agent}'.", file=sys.stderr)
        print("Try --session-id <id> to inspect a specific session.", file=sys.stderr)


if __name__ == "__main__":
    main()
