# workflow.yml Schema

The `workflow.yml` file is the single source of truth for a multi-agent workflow. Place it in `.opencode/workflow.yml` (project-scoped) or alongside your agent files.

## Full Schema

```yaml
# Required
name: string                    # Workflow identifier (kebab-case)
description: string             # What this workflow does end-to-end
version: integer                # Schema version (currently 1)

# Optional — default 2
max_depth: integer              # Global max recursive call depth across all agents

agents:
  - name: string                # Agent identifier — must match the .md filename (without .md)
    file: string                # Relative or absolute path to the .md file
    mode: primary | subagent    # primary = user-facing; subagent = invoked by other agents
    model: string               # Optional: override model (e.g. anthropic/claude-opus-4-5)
    calls: [string]             # List of agent names this agent may invoke via @name
    max_recursive_depth: integer  # Optional: per-agent override of max_depth

# Mock responses used during DEV_ testing
# Keys are agent names. Each entry is a list of trigger-response pairs.
# Triggers are regex patterns matched against the incoming prompt.
# First match wins. Always include a ".*" catch-all.
mock_responses:
  <agent_name>:
    - trigger: string           # Regex pattern (matched against the prompt sent to this agent)
      response: string          # Mock response returned by the MCP tool
    - trigger: ".*"             # Catch-all (required)
      response: string
```

## Example

```yaml
name: code-review-workflow
description: Automated code review — analyzes code, identifies issues, proposes fixes
version: 1
max_depth: 2

agents:
  - name: orchestrator
    file: orchestrator.md
    mode: primary
    calls: [analyzer, reviewer, fixer]

  - name: analyzer
    file: analyzer.md
    mode: subagent
    calls: []

  - name: reviewer
    file: reviewer.md
    mode: subagent
    calls: []

  - name: fixer
    file: fixer.md
    mode: subagent
    calls: [orchestrator]
    max_recursive_depth: 1

mock_responses:
  analyzer:
    - trigger: ".*"
      response: |
        Analysis complete.
        - 2 potential null dereferences (lines 14, 42)
        - 1 missing error handler (line 67)
        - Complexity score: 12 (high)

  reviewer:
    - trigger: "style.*"
      response: "Style looks clean. One suggestion: rename `tmp` to `tempBuffer` for clarity."
    - trigger: ".*"
      response: "Review complete. No blocking issues. 2 minor suggestions attached."

  fixer:
    - trigger: "null.*"
      response: "Fixed null dereferences using optional chaining at lines 14 and 42."
    - trigger: ".*"
      response: "Fix applied. Please re-run analyzer to confirm."
```

## Trigger evals (optional)

For each agent, you can define trigger evals to optimize its `description` field. Save as `<agent-name>-trigger-evals.json` alongside `workflow.yml`:

```json
[
  {"prompt": "realistic user prompt that should invoke this agent", "should_trigger": true},
  {"prompt": "similar-looking prompt that should NOT invoke this agent", "should_trigger": false}
]
```

Good trigger evals:
- **Should-trigger**: varied phrasings, some casual, some with typos, edge cases where the agent competes with another
- **Should-not-trigger**: near-misses that share keywords but need a different agent — avoid obviously unrelated prompts

Run optimization:
```bash
python ~/.config/opencode/workflow-creator/scripts/optimize_descriptions.py \
  --agent <name> \
  --evals .opencode/<name>-trigger-evals.json \
  --model ollama/qwen3.5:9b \
  --iterations 3
```

## Notes

- `calls` controls what the Mock MCP exposes when testing this agent — only agents listed in `calls` will have mock tools generated.
- `max_recursive_depth` overrides `max_depth` for a specific agent. Use when one path in the topology needs deeper recursion than others.
- `mock_responses` is only used during `DEV_` testing — it has no effect on the real agents.
- If you add a new agent or change the `calls` list, re-run `setup_dev_agent.py` to regenerate the mock config.
