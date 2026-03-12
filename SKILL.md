---
name: workflow-creator
description: Create, test, and optimize multi-agent workflows for OpenCode. Use this skill whenever the user wants to build a team of AI agents, design an agent pipeline, create an orchestrator with specialists, set up coordinated agents, or optimize an existing OpenCode workflow. Also triggers when the user says things like "I want agents that work together", "build me a workflow", "create a DEV agent", or "optimize my agents".
---

# Workflow Creator

A skill for designing, testing, and iterating on multi-agent workflows in OpenCode.

A "workflow" is a team of coordinated OpenCode agents: one **orchestrator** (primary mode) that breaks tasks down and delegates to **specialist subagents**. Subagents can call the orchestrator recursively up to a configured depth limit.

The full loop:
1. Understand what the user wants the workflow to accomplish
2. Design the agent team and write `workflow.yml`
3. Write each agent's `.md` file to `~/.config/opencode/agents/`
4. Test each agent in isolation using the `DEV_` pattern + Mock MCP
5. Evaluate from OpenCode session logs
6. Optimize: rewrite agent, save to both `DEV_` and real file
7. Repeat per agent, then analyze the workflow as a whole

Jump into whatever stage the user is at. If a `workflow.yml` already exists, read it first. If agents exist but no `workflow.yml`, analyze the agent files and confirm your understanding with the user before proceeding.

---

## Stage 1 — Capture Intent

Ask the user:
1. What should this workflow accomplish end-to-end?
2. What are the main subtasks? (these become your specialist agents)
3. Should any agent be able to call another recursively? If so, what's the max depth? (default: 2)
4. Which models do you want to use?

For question 4: ask the user to list the models they have in mind. Then run `opencode models` to get the full list of available models, and verify each one the user mentioned is present. If a model isn't found, suggest the closest available alternative (same provider or similar capability tier). Once confirmed, classify each model as **thinking** (strong reasoning, orchestration) or **tooling** (fast, instruction-following, tool calls) and propose an assignment across agents. The user can override any assignment.

Don't over-interview — if the workflow is clear from context, propose a design and ask for confirmation.

---

## Stage 2 — Design the Workflow

Design the agent team:
- **One orchestrator** (mode: primary) — receives the user's task, breaks it down, delegates via `@agentname` Task calls, synthesizes results
- **N specialists** (mode: subagent) — each focused on one domain
- For recursive topologies: a specialist can call `@orchestrator` but must be bounded by `max_depth`

Write or update `workflow.yml` in `.opencode/` (project-scoped context) or confirm with user if they want it elsewhere. See `references/workflow_schema.md` for the full schema.

Example minimal design:
```yaml
name: code-review-workflow
description: Automated code review with specialized agents
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
```

---

## Stage 3 — Write Agent Files

Write each agent's `.md` file to `~/.config/opencode/agents/<name>.md`.

### Orchestrator template
```markdown
---
description: <one-line purpose — this drives auto-invocation triggering>
mode: primary
model: <optional>
steps: 20
---

You are the orchestrator for <workflow name>.

Your job: receive a task, break it into subtasks, delegate to specialists, synthesize results.

## Specialists available
- @<specialist1>: <what it handles>
- @<specialist2>: <what it handles>

## Depth limit
You may be called recursively. Current depth is tracked by the calling agent. Do not delegate further if depth >= <max_depth>.

## Workflow
1. Analyze the task
2. Identify which specialists to invoke and in what order
3. Call each with a clear, scoped subtask prompt
4. Collect results and synthesize a final answer
```

### Specialist template
```markdown
---
description: <specific domain this agent handles>
mode: subagent
model: <optional>
tools:
  write: <true/false>
  bash: <true/false>
---

You are the <name> specialist in the <workflow> workflow.

Focus only on: <domain>.

## Inputs
You receive: <what the orchestrator sends>

## Outputs
Return: <what the orchestrator expects back>

## Guidelines
<domain-specific instructions>
```

After writing, confirm all files exist:
```bash
ls ~/.config/opencode/agents/
```

---

## Stage 4 — Test an Agent in Isolation

Testing one agent means: run it with realistic inputs, while mocking all its subagent dependencies.

### 4.1 Setup the DEV agent

Run the setup script:
```bash
python ~/.config/opencode/workflow-creator/scripts/setup_dev_agent.py \
  --agent <name> \
  --workflow <path-to-workflow.yml>
```

This script:
- Copies `~/.config/opencode/agents/<name>.md` to `~/.config/opencode/agents/DEV_<name>.md`
- Replaces all `@subagent` references in the prompt with "use the mock_<subagent> tool"
- Writes `.opencode/mock_responses.yml` from `workflow.yml` mock_responses
- Adds the Mock MCP to `~/.config/opencode/opencode.json` (global) if not already present

### 4.2 Write mock responses

In `workflow.yml`, add `mock_responses` for each subagent this agent calls:
```yaml
mock_responses:
  analyzer:
    - trigger: ".*"
      response: "Analysis complete: found 3 issues — 1 critical, 2 warnings."
  fixer:
    - trigger: "critical.*"
      response: "Fixed: replaced null check with optional chaining."
    - trigger: ".*"
      response: "Fix applied successfully."
```
Triggers are regex patterns matched against the prompt. First match wins. Always include a catch-all `".*"`.

### 4.3 Run the DEV agent

`opencode run` requires a real terminal (TTY) — it cannot be driven as a background subprocess. Ask the user to open a new terminal window and run the test prompt inline:

```bash
opencode run --agent DEV_<name> "your test prompt here"
```

OpenCode always reads the latest config on startup, so no restart is needed after `setup_dev_agent.py` runs.

Prepare 2–3 realistic test prompts. Run them one at a time. After each run, ask the user to come back here — then read the session logs with `opencode session list` + `opencode export <id>`.

### 4.4 Read session logs

```bash
python ~/.config/opencode/workflow-creator/scripts/read_logs.py --agent DEV_<name> --last 1
```

This outputs a structured summary: tool calls made, mock tools invoked, final response, any errors or loops.

---

## Stage 5 — Evaluate

Spawn the evaluator subagent:

```
Read agents/evaluator.md and evaluate this agent run.
Log summary: <paste read_logs.py output>
Agent file: ~/.config/opencode/agents/DEV_<name>.md
Test prompt: "<prompt used>"
Expected behavior: <what the orchestrator expects this agent to return>
```

The evaluator checks:
- Did the agent stay on scope?
- Did it call the right mock tools with sensible prompts?
- Was it confused, stuck, or looping?
- Was the output well-structured for the orchestrator to consume?
- Was it efficient (not wasting steps)?

It returns a score (1–5) and specific improvement notes.

---

## Stage 6 — Optimize

If the score is < 4 or the user wants improvements, spawn the optimizer:

```
Read agents/optimizer.md and rewrite this agent.
Current agent: ~/.config/opencode/agents/DEV_<name>.md
Evaluation notes: <evaluator output>
workflow.yml context: <relevant agent spec>
```

The optimizer rewrites the agent system prompt based on the evaluation. After it returns the new content:

1. Save to `DEV_<name>.md`
2. Also save to the real `<name>.md` (they stay in sync — DEV is just the test harness wrapping)
3. Re-run the test (go back to Stage 4.3)

Repeat until score >= 4 or the user is satisfied.

### Teardown

When done testing an agent:
```bash
python ~/.config/opencode/workflow-creator/scripts/teardown_dev_agent.py --agent <name>
```
This removes `DEV_<name>.md` and cleans up mock config.

---

## Stage 7 — Workflow-level Analysis

After all agents are individually tested, analyze the workflow holistically.

Read all agent files + `workflow.yml`. Then consider:
- Are agent boundaries well-defined? Any overlap or gaps?
- Are orchestrator delegation prompts clear enough for each specialist?
- Are there unnecessary hops? Could two agents be merged?
- Is the depth limit appropriate for the recursion topology?
- Are tool permissions well-scoped? (read-only agents shouldn't have write: true)

Present findings as a structured report. Ask the user if they want to apply any restructuring.

---

## workflow.yml management

Always keep `workflow.yml` up to date. Every change to an agent's role, calls list, or mock responses should be reflected there. The workflow.yml is the single source of truth for:
- Agent topology
- Mock responses for testing
- Depth limits
- Model assignments

See `references/workflow_schema.md` for the full schema.

---

## Reference files

- `references/workflow_schema.md` — Full workflow.yml schema with all fields
- `references/opencode_agents.md` — OpenCode agent frontmatter reference
- `agents/evaluator.md` — Instructions for the evaluator subagent
- `agents/optimizer.md` — Instructions for the optimizer subagent
- `scripts/setup_dev_agent.py` — DEV agent setup
- `scripts/teardown_dev_agent.py` — DEV agent cleanup
- `scripts/mock_mcp_server.py` — Mock MCP server
- `scripts/read_logs.py` — OpenCode session log parser
