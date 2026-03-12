#!/usr/bin/env python3
"""
Mock MCP Server for workflow-creator DEV testing.

Reads mock_responses.yml and registers one tool per mocked agent.
Each tool accepts a `prompt` argument and returns the first matching response.

Usage:
    python mock_mcp_server.py --config .opencode/mock_responses.yml
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
except ImportError:
    print("MCP SDK required: pip install mcp", file=sys.stderr)
    sys.exit(1)


def load_mock_responses(config_path: str) -> dict:
    """Load mock_responses from YAML config."""
    path = Path(config_path)
    if not path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        data = yaml.safe_load(f)
    # Accepts either a full workflow.yml or a standalone mock_responses.yml
    return data.get("mock_responses", data)


def match_response(responses: list, prompt: str) -> str:
    """Return first matching response for the given prompt."""
    for entry in responses:
        trigger = entry.get("trigger", ".*")
        if re.search(trigger, prompt, re.IGNORECASE | re.DOTALL):
            return entry["response"]
    return "(no mock response matched)"


def build_server(mock_responses: dict) -> Server:
    server = Server("mock-agents")

    # Register list_tools handler
    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        tools = []
        for agent_name in mock_responses:
            tools.append(types.Tool(
                name=f"mock_{agent_name}",
                description=f"Mock response for @{agent_name} subagent during DEV testing",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": f"The prompt you would send to @{agent_name}"
                        }
                    },
                    "required": ["prompt"]
                }
            ))
        return tools

    # Register call_tool handler
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        if not name.startswith("mock_"):
            raise ValueError(f"Unknown tool: {name}")

        agent_name = name[5:]  # strip "mock_"
        if agent_name not in mock_responses:
            return [types.TextContent(type="text", text=f"(no mock configured for {agent_name})")]

        prompt = arguments.get("prompt", "")
        response = match_response(mock_responses[agent_name], prompt)
        return [types.TextContent(type="text", text=response)]

    return server


async def main(config_path: str):
    mock_responses = load_mock_responses(config_path)
    if not mock_responses:
        print("No mock_responses found in config.", file=sys.stderr)
        sys.exit(1)

    print(f"Mock MCP: loaded {len(mock_responses)} agent mock(s): {list(mock_responses.keys())}", file=sys.stderr)
    server = build_server(mock_responses)
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to mock_responses.yml or workflow.yml")
    args = parser.parse_args()

    asyncio.run(main(args.config))
