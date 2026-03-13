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
3. Write each agent's `.md` file to `~/.config/opencode/agents/<workflow-name>/`
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

Write or update `workflow.yml` in `.opencode/<workflow-name>/` (project-scoped, one subfolder per workflow). Use the `name` field from the workflow as the subfolder. See `references/workflow_schema.md` for the full schema.

After writing, validate it:
```bash
python ~/.config/opencode/workflow-creator/scripts/validate_workflow.py --workflow .opencode/<workflow-name>/workflow.yml
```

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

Write each agent's `.md` file to `~/.config/opencode/agents/<workflow-name>/<name>.md`. The subfolder must match the workflow `name` field so scripts can resolve it automatically.

> **Cross-agent references must use the full path**: whenever an agent calls another agent, write it as `@<workflow-name>/<agent_name>` — never bare `@<agent_name>`. OpenCode resolves agents relative to the agents root, so the folder prefix is required for agents stored in subfolders.

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
- @<workflow-name>/<specialist1>: <what it handles>
- @<workflow-name>/<specialist2>: <what it handles>

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
ls ~/.config/opencode/agents/<workflow-name>/
```

---

## Stage 4 — Test Agents in Isolation

Test agents bottom-up: leaf agents first (no subagents), then capture their real responses to use as mocks for agents higher in the topology.

### 4.1 Identify the test order

From `workflow.yml`, build the order: agents with no `calls` go first (leaves), then agents that call only leaves, and so on up to the orchestrator last.

Example for a 3-level workflow:
```
1. leaf agents    (calls: [])         → test directly, no mock needed
2. mid agents     (calls: [leaf])     → test with captured leaf responses as mocks
3. orchestrator   (calls: [mid, ...]) → test with captured mid responses as mocks
```

### 4.2 Test leaf agents (no mock needed)

For each leaf agent, ask the user to run 2–3 realistic prompts in their terminal:
```bash
opencode run --agent <workflow-name>/<leaf-agent-name> "realistic prompt"
```

After each run, verify the output looks correct with:
```bash
python ~/.config/opencode/workflow-creator/scripts/read_logs.py --agent <leaf-agent-name> --last 1
```

### 4.3 Capture real responses as mocks

Once a leaf agent has been tested and its outputs look good, capture them into `workflow.yml`:
```bash
python ~/.config/opencode/workflow-creator/scripts/capture_responses.py \
  --agent <leaf-agent-name> \
  --workflow .opencode/<workflow-name>/workflow.yml \
  --last 3
```

This reads the last 3 sessions for that agent from the SQLite DB and writes them as `mock_responses` entries, with auto-generated triggers based on the prompts used. Review the result in `workflow.yml` and adjust triggers if needed — always ensure there is a catch-all `".*"` entry.

Use `--dry-run` to preview before writing.

### 4.4 Setup the DEV agent for the next level

Once mocks are populated for all subagents an agent calls, run setup:
```bash
python ~/.config/opencode/workflow-creator/scripts/setup_dev_agent.py \
  --agent <name> \
  --workflow .opencode/<workflow-name>/workflow.yml
```

This script:
- Copies `~/.config/opencode/agents/<workflow-name>/<name>.md` to `~/.config/opencode/agents/<workflow-name>/DEV_<name>.md`
- **Overrides `mode:` to `all`** in the DEV copy (see note below)
- Rewrites `@subagent` mentions to `[use mock_<subagent> tool]`
- Writes `.opencode/mock_responses.yml` from `workflow.yml` mock_responses
- Adds the Mock MCP to `~/.config/opencode/opencode.json` if not already present

> **Mode override — why this matters**: Subagent files carry `mode: subagent` in their frontmatter, which prevents direct invocation via `opencode run`. Testing a `subagent`-mode agent would either fail or produce results that don't reflect real behavior. The setup script automatically patches the DEV copy to `mode: all` so it can be invoked standalone and evaluated normally. The real agent file is **never modified** — the mode change is scoped to the DEV copy only.

### 4.5 Run the DEV agent

`opencode run` requires a real terminal (TTY). Use this pattern to launch it in a new Windows Terminal tab and detect when it finishes:

**Step 1** — Write a launcher script:
```bash
cat > /c/tmp/oc_run.ps1 <<'EOF'
Remove-Item -Force C:\tmp\oc_done.txt -ErrorAction SilentlyContinue
opencode run --agent <workflow-name>/DEV_<name> "your test prompt here"
"done" | Out-File C:\tmp\oc_done.txt
EOF
```

**Step 2** — Launch it in a new terminal tab:
```bash
powershell -Command "Start-Process wt -ArgumentList 'new-tab -- powershell.exe -File C:\tmp\oc_run.ps1'"
```

**Step 3** — Poll for completion:
```bash
for i in $(seq 1 60); do [ -f /c/tmp/oc_done.txt ] && echo "done after $((i*5))s" && break || echo "waiting... ($((i*5))s)"; sleep 5; done
```

OpenCode always reads the latest config on startup, so no restart is needed after `setup_dev_agent.py` runs. Prepare 2–3 realistic test prompts and run them one at a time.

### 4.6 Read session logs

```bash
python ~/.config/opencode/workflow-creator/scripts/read_logs.py --agent <workflow-name>/DEV_<name> --last 1
```

This outputs a structured summary: tool calls made, mock tools invoked, final response, any errors or loops.

---

## Stage 5 — Evaluate

Before running the evaluator for the first time in a workflow, create a `TMP_agent` in `~/.config/opencode/agents/<workflow-name>/`. This is a real OpenCode agent used as the evaluation/optimization workhorse for the entire test cycle. It is deleted after Stage 7.

### 5.1 Create TMP_agent

Write `~/.config/opencode/agents/<workflow-name>/TMP_agent.md`:

```markdown
---
description: Temporary evaluation and optimization agent for <workflow-name> testing
mode: primary
model: <model chosen by user in Stage 1 — use the thinking/reasoning model>
tools:
  read: true
  write: true
---

You are a temporary evaluation and optimization agent for the <workflow-name> workflow.

You will be asked to either:
- **Evaluate** an agent run: read the agent file and log summary provided, score (1–5), and return specific improvement notes
- **Optimize** an agent file: rewrite the system prompt based on evaluation notes, return the full new file content

Always read the files referenced in the prompt before responding.
```

### 5.2 Run the evaluator

Launch TMP_agent with the evaluation task:

```bash
cat > /c/tmp/oc_run.ps1 <<'EOF'
Remove-Item -Force C:\tmp\oc_done.txt -ErrorAction SilentlyContinue
opencode run --agent <workflow-name>/TMP_agent "Evaluate this agent run. Read ~/.config/opencode/workflow-creator/agents/evaluator.md for instructions. Log summary: <paste read_logs.py output> | Agent file: ~/.config/opencode/agents/<workflow-name>/DEV_<name>.md | Test prompt: \"<prompt used>\" | Expected behavior: <what the orchestrator expects>"
"done" | Out-File C:\tmp\oc_done.txt
EOF
powershell -Command "Start-Process wt -ArgumentList 'new-tab -- powershell.exe -File C:\tmp\oc_run.ps1'"
for i in $(seq 1 60); do [ -f /c/tmp/oc_done.txt ] && echo "done after $((i*5))s" && break || echo "waiting... ($((i*5))s)"; sleep 5; done
```

Then read the session log:
```bash
python ~/.config/opencode/workflow-creator/scripts/read_logs.py --agent TMP_agent --last 1
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

If the score is < 4 or the user wants improvements, run the optimizer via TMP_agent:

```bash
cat > /c/tmp/oc_run.ps1 <<'EOF'
Remove-Item -Force C:\tmp\oc_done.txt -ErrorAction SilentlyContinue
opencode run --agent <workflow-name>/TMP_agent "Optimize this agent. Read ~/.config/opencode/workflow-creator/agents/optimizer.md for instructions. Current agent: ~/.config/opencode/agents/<workflow-name>/DEV_<name>.md | Evaluation notes: <evaluator output> | workflow.yml context: <relevant agent spec>"
"done" | Out-File C:\tmp\oc_done.txt
EOF
powershell -Command "Start-Process wt -ArgumentList 'new-tab -- powershell.exe -File C:\tmp\oc_run.ps1'"
for i in $(seq 1 60); do [ -f /c/tmp/oc_done.txt ] && echo "done after $((i*5))s" && break || echo "waiting... ($((i*5))s)"; sleep 5; done
```

Then read the session log to get the rewritten agent content:
```bash
python ~/.config/opencode/workflow-creator/scripts/read_logs.py --agent TMP_agent --last 1
```

After TMP_agent returns the new content:

1. Save to `~/.config/opencode/agents/<workflow-name>/DEV_<name>.md`
2. Also save to the real `~/.config/opencode/agents/<workflow-name>/<name>.md` (they stay in sync — DEV is just the test harness wrapping)
3. Re-run the test (go back to Stage 4.3)

Repeat until score >= 4 or the user is satisfied.

### Teardown

When done testing an agent:
```bash
python ~/.config/opencode/workflow-creator/scripts/teardown_dev_agent.py \
  --agent <name> \
  --workflow .opencode/<workflow-name>/workflow.yml
```
This removes `DEV_<name>.md` from the agents folder and cleans up mock config.

Delete `TMP_agent` only after **all** agents in the workflow have been tested and optimized (after Stage 7):
```bash
rm ~/.config/opencode/agents/<workflow-name>/TMP_agent.md
```

---

## Stage 7 — Workflow-level Analysis

After all agents are individually tested, run the workflow analyzer via TMP_agent:

```bash
cat > /c/tmp/oc_run.ps1 <<'EOF'
Remove-Item -Force C:\tmp\oc_done.txt -ErrorAction SilentlyContinue
opencode run --agent <workflow-name>/TMP_agent "Analyze this workflow. Read ~/.config/opencode/workflow-creator/agents/workflow-analyzer.md for instructions. workflow.yml: .opencode/<workflow-name>/workflow.yml | Agents directory: ~/.config/opencode/agents/<workflow-name>/ | Recent test log summaries: <paste any read_logs.py output worth including>"
"done" | Out-File C:\tmp\oc_done.txt
EOF
powershell -Command "Start-Process wt -ArgumentList 'new-tab -- powershell.exe -File C:\tmp\oc_run.ps1'"
for i in $(seq 1 60); do [ -f /c/tmp/oc_done.txt ] && echo "done after $((i*5))s" && break || echo "waiting... ($((i*5))s)"; sleep 5; done
```

Then read the session log:
```bash
python ~/.config/opencode/workflow-creator/scripts/read_logs.py --agent TMP_agent --last 1
```

The analyzer checks topology, agent boundaries, tool permissions, model assignments, depth/recursion, and mock coverage. It returns a structured report with a topology diagram.

Present the findings to the user. Ask if they want to apply any of the suggested restructuring before considering the workflow done.

After this stage, delete TMP_agent:
```bash
rm ~/.config/opencode/agents/<workflow-name>/TMP_agent.md
```

---

## Stage 8 — Workflow-level Eval

Once individual agents pass and the topology is clean, run a full end-to-end test:

1. Launch the **real** workflow (not DEV_) in a new terminal tab and wait for completion:
   ```bash
   cat > /c/tmp/oc_run.ps1 <<'EOF'
   Remove-Item -Force C:\tmp\oc_done.txt -ErrorAction SilentlyContinue
   opencode run --agent <orchestrator-name> "<realistic end-to-end prompt>"
   "done" | Out-File C:\tmp\oc_done.txt
   EOF
   powershell -Command "Start-Process wt -ArgumentList 'new-tab -- powershell.exe -File C:\tmp\oc_run.ps1'"
   for i in $(seq 1 60); do [ -f /c/tmp/oc_done.txt ] && echo "done after $((i*5))s" && break || echo "waiting... ($((i*5))s)"; sleep 5; done
   ```

2. Read the session logs:
   ```bash
   python ~/.config/opencode/workflow-creator/scripts/read_logs.py --agent <orchestrator-name> --last 1
   ```

3. Compare against baseline — run the same prompt with the default Build agent:
   ```bash
   cat > /c/tmp/oc_run.ps1 <<'EOF'
   Remove-Item -Force C:\tmp\oc_done.txt -ErrorAction SilentlyContinue
   opencode run "same prompt"
   "done" | Out-File C:\tmp\oc_done.txt
   EOF
   powershell -Command "Start-Process wt -ArgumentList 'new-tab -- powershell.exe -File C:\tmp\oc_run.ps1'"
   for i in $(seq 1 60); do [ -f /c/tmp/oc_done.txt ] && echo "done" && break || sleep 5; done
   ```
   Then read that session too.

4. Evaluate the difference: did the workflow produce a better, more structured result than Build alone? Were the right specialists invoked? Was the output well-organized?

If the workflow isn't clearly better than baseline for this prompt, go back to Stage 6 and improve the orchestrator's delegation strategy.

---

## Stage 9 — Description Optimization (optional)

Subagents auto-trigger based on their `description` field. If an agent is being missed or over-invoked, optimize its description.

### 9.1 Create trigger evals

Write 8–10 prompts per agent: half that should trigger it, half that shouldn't. Near-misses are more valuable than obvious cases. Save to `.opencode/<workflow-name>/<agent-name>-trigger-evals.json`:

```json
[
  {"prompt": "...", "should_trigger": true},
  {"prompt": "...", "should_trigger": false}
]
```

### 9.2 Run the optimizer

```bash
python ~/.config/opencode/workflow-creator/scripts/optimize_descriptions.py \
  --agent <name> \
  --evals .opencode/<workflow-name>/<name>-trigger-evals.json \
  --model ollama/qwen3.5:9b \
  --iterations 3
```

The script scores the current description, proposes improvements based on failures, and iterates. At the end it asks you to confirm before writing the new description.

Only run this after the agent's behavior is stable — description optimization is the last step.

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
- `agents/workflow-analyzer.md` — Holistic workflow topology and boundary analysis
- `scripts/setup_dev_agent.py` — DEV agent setup
- `scripts/teardown_dev_agent.py` — DEV agent cleanup
- `scripts/mock_mcp_server.py` — Mock MCP server
- `scripts/read_logs.py` — OpenCode session log parser
- `scripts/optimize_descriptions.py` — Agent description trigger optimizer
- `scripts/capture_responses.py` — Captures real agent responses from SQLite DB into workflow.yml mock_responses
- `scripts/validate_workflow.py` — Validates workflow.yml structure before testing
- `scripts/install.py` — Copies skill assets to ~/.config/opencode/workflow-creator/
