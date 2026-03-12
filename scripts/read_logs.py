#!/usr/bin/env python3
"""
Parses OpenCode session logs for a given agent and outputs a structured summary.

OpenCode stores session logs as JSONL files. Common locations:
  - ~/.local/share/opencode/sessions/   (Linux)
  - ~/Library/Application Support/opencode/sessions/  (macOS)
  - %APPDATA%/opencode/sessions/  (Windows → ~/AppData/Roaming/opencode/sessions/)

Usage:
    python read_logs.py --agent DEV_<name> [--last N] [--session-id <id>]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def find_sessions_dir() -> Path:
    candidates = [
        Path.home() / ".local" / "share" / "opencode" / "sessions",
        Path.home() / "Library" / "Application Support" / "opencode" / "sessions",
        Path.home() / "AppData" / "Roaming" / "opencode" / "sessions",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback: search home for opencode sessions
    for c in Path.home().rglob("opencode/sessions"):
        if c.is_dir():
            return c
    return None


def find_session_files(sessions_dir: Path, agent_name: str, last_n: int) -> list[Path]:
    """Find the most recent session files that mention the given agent."""
    all_files = sorted(sessions_dir.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not all_files:
        all_files = sorted(sessions_dir.rglob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

    matching = []
    for f in all_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            if agent_name.lower() in content.lower():
                matching.append(f)
                if len(matching) >= last_n:
                    break
        except Exception:
            continue

    if not matching:
        # Fall back to just the most recent N files
        return all_files[:last_n]
    return matching


def parse_session(file_path: Path) -> list[dict]:
    """Parse a JSONL or JSON session file into a list of events."""
    events = []
    content = file_path.read_text(encoding="utf-8", errors="ignore")

    # Try JSONL first
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    # Fallback: try full JSON array
    if not events:
        try:
            data = json.loads(content)
            if isinstance(data, list):
                events = data
            elif isinstance(data, dict):
                events = [data]
        except json.JSONDecodeError:
            pass

    return events


def summarize_session(events: list[dict], agent_name: str) -> dict:
    """Extract meaningful signal from session events."""
    tool_calls = []
    mock_calls = []
    errors = []
    final_response = None
    step_count = 0

    for event in events:
        event_type = event.get("type", event.get("role", ""))

        # Tool use
        if event_type in ("tool_use", "tool_call") or "tool_use" in event.get("content", [{}])[0].get("type", "") if isinstance(event.get("content"), list) else False:
            content = event.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = block.get("input", {})
                        if name.startswith("mock_"):
                            mock_calls.append({"tool": name, "prompt": inp.get("prompt", "")[:200]})
                        else:
                            tool_calls.append({"tool": name, "input_summary": str(inp)[:200]})
                        step_count += 1

        # Errors
        if event_type == "error" or "error" in str(event).lower()[:50]:
            errors.append(str(event)[:300])

        # Assistant final message
        if event_type in ("assistant", "message") and event.get("role") == "assistant":
            content = event.get("content", "")
            if isinstance(content, str) and len(content) > 20:
                final_response = content[:1000]
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        final_response = block.get("text", "")[:1000]
                        break

    return {
        "agent": agent_name,
        "steps": step_count,
        "tool_calls": tool_calls,
        "mock_calls": mock_calls,
        "errors": errors,
        "final_response": final_response,
    }


def print_summary(summary: dict, session_file: Path):
    print(f"\n{'='*60}")
    print(f"Session: {session_file.name}")
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
        print("\nFinal response: (not found)")

    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="Agent name to filter for (e.g. DEV_analyzer)")
    parser.add_argument("--last", type=int, default=1, help="Number of most recent sessions to show")
    parser.add_argument("--sessions-dir", help="Override sessions directory path")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else find_sessions_dir()
    if not sessions_dir or not sessions_dir.exists():
        print(f"OpenCode sessions directory not found. Try --sessions-dir <path>", file=sys.stderr)
        sys.exit(1)

    print(f"Sessions dir: {sessions_dir}")

    files = find_session_files(sessions_dir, args.agent, args.last)
    if not files:
        print(f"No session files found for agent '{args.agent}'", file=sys.stderr)
        sys.exit(1)

    for f in files:
        events = parse_session(f)
        summary = summarize_session(events, args.agent)
        print_summary(summary, f)


if __name__ == "__main__":
    main()
