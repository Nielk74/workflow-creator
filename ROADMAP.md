# workflow-creator Roadmap

## Phase 1 — Core scaffold ✓
- [x] SKILL.md with full create/test/optimize loop
- [x] workflow.yml schema (references/workflow_schema.md)
- [x] OpenCode agent format reference
- [x] evaluator.md and optimizer.md subagents
- [x] setup_dev_agent.py — DEV_ copy + @mention rewriting + mock config
- [x] teardown_dev_agent.py — cleanup
- [x] mock_mcp_server.py — dynamic MCP server from mock_responses.yml
- [x] read_logs.py — OpenCode session log parser

## Phase 2 — Validate & harden (in progress)
- [x] Confirm CLI: non-interactive run is `opencode run --agent DEV_xxx "<prompt>"`
- [x] Confirm config file is `opencode.json` (not `config.json`), global at `~/.config/opencode/opencode.json`
- [x] Confirm MCP command format: `"command": ["python", "path", "--arg", "val"]` (array, not string+args)
- [x] Session data: use `opencode session list` + `opencode export <id>` (not raw file parsing)
- [x] Fixed setup_dev_agent.py, teardown_dev_agent.py, read_logs.py, SKILL.md accordingly
- [x] Confirmed: `opencode run` requires a real TTY — cannot be driven as a subprocess from Claude Code bash (winpty doesn't bridge the gap either). SKILL.md updated: skill instructs the user to run tests in a separate terminal, then comes back for log evaluation.
- [x] Confirmed session export format via `opencode export <id>` — messages have `info.role`, `info.tokens`, `parts[]` with `type/text` fields. read_logs.py updated accordingly.
- [x] Validated DEV_sum-specialist with ollama/qwen3.5:9b — model responded correctly
- [x] Confirmed storage: ~/.local/share/opencode/opencode.db (SQLite). Tables: session, message, part — all data in JSON `data` column. `opencode export` only works with a running server; DB direct access works always. read_logs.py rewritten to query SQLite directly.
- [ ] Test mock_mcp_server.py against a real OpenCode agent session (MCP tool schema validation)
- [ ] Test setup_dev_agent.py end-to-end with a 2-agent workflow where subagents use mock tools

## Phase 3 — Workflow analysis agent
- [ ] Add `workflow-analyzer.md` subagent
  - Reads all agent .md files + workflow.yml
  - Detects: overlap, gaps, excessive depth, over-privileged tools
  - Proposes topology changes
- [ ] Add workflow-level eval: run a full end-to-end prompt through the real workflow,
  compare against baseline (no agents, just Build)

## Phase 4 — Description optimizer (port from skill-creator)
- [ ] Port the trigger eval concept to agent descriptions
  - Agents auto-trigger based on their description field
  - Especially relevant for subagents invoked implicitly
- [ ] Write a lightweight eval loop: generate trigger/no-trigger prompts, score, iterate

## Phase 5 — Polish
- [ ] `workflow-creator install` script: copies scripts to ~/.config/opencode/workflow-creator/
- [ ] Add workflow.yml validation (check: all `calls` references exist as agent names, etc.)
- [ ] Add example workflows in examples/ directory
- [ ] Consider a `--dry-run` mode for setup_dev_agent.py

## Known unknowns to resolve
- Exact OpenCode CLI flags for specifying agent (`--agent`? `--mode`?)
- Session log format (JSONL field names, tool call schema)
- Whether OpenCode reloads config.json on each `opencode` invocation or only once at install
- MCP tool invocation format in OpenCode (does it auto-expose mock-agents_* tools?)
