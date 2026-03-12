#!/usr/bin/env python3
"""
Sets up a DEV_ agent for isolated testing.

Steps:
1. Copy ~/.config/opencode/agents/<name>.md to DEV_<name>.md
2. Rewrite @subagent mentions to "use the mock_<subagent> tool"
3. Write .opencode/mock_responses.yml from workflow.yml
4. Add Mock MCP to ~/.config/opencode/config.json if not present

Usage:
    python setup_dev_agent.py --agent <name> --workflow <path-to-workflow.yml>
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

AGENTS_DIR = Path.home() / ".config" / "opencode" / "agents"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
MOCK_SERVER_PATH = Path(__file__).parent / "mock_mcp_server.py"


def load_workflow(workflow_path: str) -> dict:
    path = Path(workflow_path)
    if not path.exists():
        print(f"workflow.yml not found: {workflow_path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def get_agent_spec(workflow: dict, agent_name: str) -> dict:
    for agent in workflow.get("agents", []):
        if agent["name"] == agent_name:
            return agent
    print(f"Agent '{agent_name}' not found in workflow.yml", file=sys.stderr)
    sys.exit(1)


def rewrite_agent_prompt(content: str, calls: list) -> str:
    """Replace @subagent mentions with mock tool instructions and force mode: all."""
    # Force mode to "all" so the DEV agent can be invoked directly with opencode run
    content = re.sub(r'^(mode:\s*)subagent\s*$', r'\1all', content, flags=re.MULTILINE)
    content = re.sub(r'^(mode:\s*)primary\s*$', r'\1all', content, flags=re.MULTILINE)
    # If no mode field exists in frontmatter, inject one
    if not re.search(r'^mode:', content, re.MULTILINE):
        content = re.sub(r'^(---\n)', r'\1mode: all\n', content, count=1)

    for called_agent in calls:
        # Replace @agentname with instruction to use mock tool
        content = re.sub(
            rf"@{re.escape(called_agent)}\b",
            f"[use mock_{called_agent} tool]",
            content
        )

    # Add mock tool usage note after the frontmatter
    frontmatter_end = content.find("\n---\n", 4)  # skip opening ---
    if frontmatter_end == -1:
        frontmatter_end = content.find("---\n", 4)

    if frontmatter_end != -1 and calls:
        mock_note = "\n\n> **DEV MODE**: You are running in isolation testing mode.\n"
        mock_note += "> Instead of calling subagents directly, use these MCP mock tools:\n"
        for a in calls:
            mock_note += f"> - `mock_{a}(prompt)` — simulates @{a}\n"
        mock_note += "> These tools return pre-configured test responses.\n"
        insert_at = frontmatter_end + 4  # after closing ---\n
        content = content[:insert_at] + mock_note + content[insert_at:]

    return content


def write_mock_responses(workflow: dict, agent_name: str, agent_spec: dict):
    """Write mock_responses.yml for the subagents this agent calls."""
    calls = agent_spec.get("calls", [])
    all_mock_responses = workflow.get("mock_responses", {})

    # Only include mock responses for agents this agent calls
    relevant = {k: v for k, v in all_mock_responses.items() if k in calls}

    # Add default catch-all for any called agent without explicit mocks
    for called in calls:
        if called not in relevant:
            relevant[called] = [{"trigger": ".*", "response": f"(default mock response for {called})"}]

    mock_config_path = Path(".opencode") / "mock_responses.yml"
    mock_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mock_config_path, "w") as f:
        yaml.dump({"mock_responses": relevant}, f, default_flow_style=False)

    print(f"Wrote mock responses to {mock_config_path}")
    return mock_config_path


def add_mock_mcp_to_config(mock_config_path: Path):
    """Add Mock MCP server to ~/.config/opencode/config.json."""
    config = {}
    if OPENCODE_CONFIG.exists():
        with open(OPENCODE_CONFIG) as f:
            config = json.load(f)

    mcp_section = config.setdefault("mcp", {})

    if "mock-agents" in mcp_section:
        print("Mock MCP already in config — updating config path.")

    mcp_section["mock-agents"] = {
        "type": "local",
        "command": ["python", str(MOCK_SERVER_PATH), "--config", str(mock_config_path.resolve())],
        "timeout": 15000
    }

    OPENCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENCODE_CONFIG, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Updated {OPENCODE_CONFIG} with mock-agents MCP")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="Agent name (without DEV_ prefix)")
    parser.add_argument("--workflow", required=True, help="Path to workflow.yml")
    args = parser.parse_args()

    workflow = load_workflow(args.workflow)
    agent_spec = get_agent_spec(workflow, args.agent)
    calls = agent_spec.get("calls", [])

    source = AGENTS_DIR / f"{args.agent}.md"
    dest = AGENTS_DIR / f"DEV_{args.agent}.md"

    if not source.exists():
        print(f"Agent file not found: {source}", file=sys.stderr)
        sys.exit(1)

    # Copy and rewrite
    content = source.read_text(encoding="utf-8")
    content = rewrite_agent_prompt(content, calls)
    dest.write_text(content, encoding="utf-8")
    print(f"Created DEV agent: {dest}")

    if calls:
        mock_config_path = write_mock_responses(workflow, args.agent, agent_spec)
        add_mock_mcp_to_config(mock_config_path)
    else:
        print(f"Agent '{args.agent}' calls no subagents — no mock setup needed.")

    print(f"\nReady. Run: opencode --agent DEV_{args.agent} \"<test prompt>\"")


if __name__ == "__main__":
    main()
