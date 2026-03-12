#!/usr/bin/env python3
"""
Evaluates and optimizes agent description fields for better auto-invocation triggering.

In OpenCode, subagents auto-trigger based on their `description` frontmatter field.
This script runs a set of trigger/no-trigger test prompts against a description,
scores it, proposes improvements, and iterates.

Usage:
    python optimize_descriptions.py --agent <name> --workflow <path> [--iterations 5]
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

AGENTS_DIR = Path.home() / ".config" / "opencode" / "agents"


def read_agent(agent_name: str) -> tuple[dict, str]:
    """Read agent file, return (frontmatter dict, body str)."""
    path = AGENTS_DIR / f"{agent_name}.md"
    if not path.exists():
        print(f"Agent not found: {path}", file=sys.stderr)
        sys.exit(1)
    content = path.read_text(encoding="utf-8")
    # Split frontmatter
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}, content
    fm = yaml.safe_load(parts[1])
    body = parts[2]
    return fm, body


def write_agent_description(agent_name: str, new_description: str):
    """Update the description field in an agent's frontmatter."""
    path = AGENTS_DIR / f"{agent_name}.md"
    content = path.read_text(encoding="utf-8")
    content = re.sub(
        r'^(description:\s*).*$',
        f'description: {new_description}',
        content,
        flags=re.MULTILINE,
        count=1
    )
    path.write_text(content, encoding="utf-8")


def load_trigger_evals(eval_path: str) -> list[dict]:
    """Load trigger eval set from JSON file."""
    with open(eval_path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("evals", [])


def score_description(description: str, evals: list[dict], model: str) -> dict:
    """
    Ask the model to judge whether each prompt would trigger an agent with this description.
    Returns {score: float, results: [{prompt, should_trigger, triggered, correct}]}
    """
    batch = []
    for ev in evals:
        prompt = ev["prompt"]
        should = ev["should_trigger"]
        # Ask model: given this agent description, would you invoke it for this user prompt?
        judge_prompt = f"""You are deciding whether to invoke a specialized agent.

Agent description: "{description}"

User prompt: "{prompt}"

Would you invoke this agent for this user prompt? Answer with just YES or NO."""

        result = subprocess.run(
            ["opencode", "run", "-m", model, judge_prompt],
            capture_output=True, text=True, timeout=30
        )
        answer = result.stdout.strip().upper()
        triggered = "YES" in answer
        batch.append({
            "prompt": prompt,
            "should_trigger": should,
            "triggered": triggered,
            "correct": triggered == should
        })

    correct = sum(1 for r in batch if r["correct"])
    score = correct / len(batch) if batch else 0
    return {"score": score, "correct": correct, "total": len(batch), "results": batch}


def propose_improvement(description: str, score_result: dict, agent_name: str, model: str) -> str:
    """Ask the model to propose a better description based on failures."""
    failures = [r for r in score_result["results"] if not r["correct"]]
    failure_text = "\n".join(
        f"- {'Should trigger' if r['should_trigger'] else 'Should NOT trigger'} but {'did' if r['triggered'] else 'did not'}: \"{r['prompt']}\""
        for r in failures
    )

    prompt = f"""You are optimizing an agent description for auto-invocation accuracy.

Agent name: {agent_name}
Current description: "{description}"

Failing cases:
{failure_text}

Write an improved description that fixes these failures without breaking the passing cases.
The description should be 1-2 sentences, specific about when to invoke this agent, and clear about what it does.
Return ONLY the new description text, nothing else."""

    result = subprocess.run(
        ["opencode", "run", "-m", model, prompt],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip().strip('"')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, help="Agent name to optimize")
    parser.add_argument("--evals", required=True, help="Path to trigger eval JSON file")
    parser.add_argument("--model", default="ollama/qwen3.5:9b", help="Model to use for judging")
    parser.add_argument("--iterations", type=int, default=3, help="Max optimization iterations")
    args = parser.parse_args()

    fm, _ = read_agent(args.agent)
    current_description = fm.get("description", "")
    evals = load_trigger_evals(args.evals)

    print(f"Optimizing description for: {args.agent}")
    print(f"Eval set: {len(evals)} prompts ({sum(1 for e in evals if e['should_trigger'])} trigger, {sum(1 for e in evals if not e['should_trigger'])} no-trigger)")
    print(f"Starting description: {current_description}\n")

    best_description = current_description
    best_score = 0.0

    for i in range(1, args.iterations + 1):
        print(f"--- Iteration {i} ---")
        print(f"Description: {current_description}")

        result = score_description(current_description, evals, args.model)
        print(f"Score: {result['correct']}/{result['total']} ({result['score']:.0%})")

        for r in result["results"]:
            status = "✓" if r["correct"] else "✗"
            trigger_label = "trigger" if r["should_trigger"] else "no-trigger"
            print(f"  {status} [{trigger_label}] {r['prompt'][:60]!r}")

        if result["score"] > best_score:
            best_score = result["score"]
            best_description = current_description

        if result["score"] == 1.0:
            print("\nPerfect score — stopping early.")
            break

        if i < args.iterations:
            print("\nProposing improvement...")
            new_description = propose_improvement(current_description, result, args.agent, args.model)
            if new_description and new_description != current_description:
                current_description = new_description
            else:
                print("No improvement proposed — stopping.")
                break

    print(f"\n{'='*50}")
    print(f"Best description (score {best_score:.0%}):")
    print(f"  {best_description}")

    if best_description != fm.get("description", ""):
        apply = input("\nApply this description? [y/N] ").strip().lower()
        if apply == "y":
            write_agent_description(args.agent, best_description)
            print(f"Updated {args.agent}.md")
    else:
        print("No improvement found.")


if __name__ == "__main__":
    main()
