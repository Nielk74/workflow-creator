#!/usr/bin/env python3
"""
Removes a DEV_ agent and optionally cleans up mock config.

Usage:
    python teardown_dev_agent.py --agent <name> [--remove-mcp]
"""

import argparse
import json
from pathlib import Path

AGENTS_BASE_DIR = Path.home() / ".config" / "opencode" / "agents"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="Agent name (without DEV_ prefix)")
    parser.add_argument("--workflow", required=False, help="Path to workflow.yml (used to resolve subfolder)")
    parser.add_argument("--remove-mcp", action="store_true", help="Also remove mock-agents MCP from config")
    args = parser.parse_args()

    agents_dir = AGENTS_BASE_DIR
    if args.workflow:
        try:
            import yaml
            with open(args.workflow) as f:
                wf = yaml.safe_load(f)
            workflow_name = wf.get("name", "")
            if workflow_name:
                agents_dir = AGENTS_BASE_DIR / workflow_name
        except Exception:
            pass

    dev_path = agents_dir / f"DEV_{args.agent}.md"
    if dev_path.exists():
        dev_path.unlink()
        print(f"Removed {dev_path}")
    else:
        print(f"DEV agent not found (already removed?): {dev_path}")

    mock_responses = Path(".opencode") / "mock_responses.yml"
    if mock_responses.exists():
        mock_responses.unlink()
        print(f"Removed {mock_responses}")

    if args.remove_mcp and OPENCODE_CONFIG.exists():
        with open(OPENCODE_CONFIG) as f:
            config = json.load(f)
        if "mock-agents" in config.get("mcp", {}):
            del config["mcp"]["mock-agents"]
            with open(OPENCODE_CONFIG, "w") as f:
                json.dump(config, f, indent=2)
            print("Removed mock-agents MCP from config")

    print("Done.")


if __name__ == "__main__":
    main()
