#!/usr/bin/env python3
"""
Validates a workflow.yml file for structural correctness.

Checks:
- All `calls` references resolve to defined agents
- No orphaned agents (defined but never called and not the orchestrator)
- All agents with calls have mock_responses entries
- Every mock_responses entry has a catch-all ".*" trigger
- max_depth is set if any recursive calls exist

Usage:
    python validate_workflow.py --workflow <path-to-workflow.yml>
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def validate(workflow_path: str) -> list[str]:
    errors = []
    warnings = []

    with open(workflow_path) as f:
        wf = yaml.safe_load(f)

    agents = {a["name"]: a for a in wf.get("agents", [])}
    mock_responses = wf.get("mock_responses", {})
    max_depth = wf.get("max_depth", 2)

    primary_agents = [a for a in agents.values() if a.get("mode") == "primary"]
    if len(primary_agents) == 0:
        errors.append("No primary-mode agent (orchestrator) defined.")
    elif len(primary_agents) > 1:
        warnings.append(f"Multiple primary agents: {[a['name'] for a in primary_agents]}. Only one orchestrator is recommended.")

    all_called = set()
    for name, agent in agents.items():
        calls = agent.get("calls", [])
        for called in calls:
            if called not in agents:
                errors.append(f"Agent '{name}' calls '{called}' which is not defined in workflow.yml")
            all_called.add(called)

    orchestrator_names = {a["name"] for a in primary_agents}
    for name in agents:
        if name not in all_called and name not in orchestrator_names:
            warnings.append(f"Agent '{name}' is never called by any other agent (orphan).")

    # Check for recursive calls without depth check
    for name, agent in agents.items():
        calls = agent.get("calls", [])
        for called in calls:
            if called in agents and name in agents[called].get("calls", []):
                if "max_recursive_depth" not in agent and "max_recursive_depth" not in agents[called]:
                    warnings.append(f"Recursive cycle detected: {name} ↔ {called}. Consider setting max_recursive_depth.")

    # Mock responses coverage
    for name, agent in agents.items():
        calls = agent.get("calls", [])
        if calls:
            for called in calls:
                if called not in mock_responses:
                    warnings.append(f"No mock_responses for '{called}' (called by '{name}'). Testing will use default fallback.")
                else:
                    triggers = [r.get("trigger", "") for r in mock_responses[called]]
                    if ".*" not in triggers:
                        errors.append(f"mock_responses['{called}'] has no catch-all '.*' trigger. Add one to avoid silent failures.")

    return errors, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True, help="Path to workflow.yml")
    args = parser.parse_args()

    errors, warnings = validate(args.workflow)

    if not errors and not warnings:
        print("OK workflow.yml is valid.")
        return

    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  WARNING {w}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  ERROR {e}")
        sys.exit(1)
    else:
        print("\nOK No errors.")


if __name__ == "__main__":
    main()
