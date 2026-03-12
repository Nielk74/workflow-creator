# OpenCode Agent Format Reference

Agents live in `~/.config/opencode/agents/<name>.md` (global) or `.opencode/agents/<name>.md` (project-scoped).
The filename (without `.md`) becomes the agent's identifier and the `@name` handle.

## Frontmatter Fields

```yaml
---
# Required
description: string         # Purpose of this agent — drives auto-invocation by OpenCode

# Mode
mode: primary | subagent | all
# primary  = appears in Tab cycling, user-facing
# subagent = invoked by other agents via Task tool or @mention
# all      = both (rarely used)

# Model override (optional)
model: provider/model-id    # e.g. anthropic/claude-opus-4-5, openai/gpt-4o

# Iteration limit
steps: integer              # Max agentic steps before fallback to text-only response

# Tool availability (optional — omit to inherit defaults)
tools:
  read: true | false
  write: true | false
  edit: true | false
  bash: true | false
  webfetch: true | false
  todoread: true | false
  todowrite: true | false
  task: true | false        # ability to invoke subagents
  <mcp_name>_*: true|false  # wildcard for MCP tools

# Permissions (optional)
permission:
  edit: ask | allow | deny
  bash:
    "*": ask                 # default
    "git diff": allow        # specific commands
    "git log*": allow
    "rm -rf*": deny
  webfetch: deny

# Misc
temperature: float          # 0.0–1.0
top_p: float
hidden: true | false        # hide from @ autocomplete (doesn't prevent programmatic use)
disable: true | false
---
```

## Body

The body is the system prompt. Written in markdown. No length limit.

## How agents call each other

Agents invoke subagents via the `task` tool with `@agentname` syntax in the prompt, or by referencing the agent name directly when the task tool is available.

Example orchestrator instruction:
```
Delegate the analysis step to @analyzer with the following prompt:
"Analyze the function at line 42 for null safety issues."
```

The called agent receives the prompt as its task and returns a text result.

## Recursive calls

If agent A calls @orchestrator which calls @A again, depth increases by 1 each time.
The orchestrator is responsible for enforcing depth limits — include a depth check in the orchestrator's system prompt when recursion is possible.

## Config via opencode.json

Agents can also be defined inline in `opencode.json`:
```json
{
  "agent": {
    "my-agent": {
      "description": "...",
      "mode": "subagent",
      "model": "anthropic/claude-haiku-4-5",
      "tools": { "bash": false }
    }
  }
}
```
But `.md` files are preferred for complex system prompts.

## MCP integration

Add MCPs to `~/.config/opencode/config.json`:
```json
{
  "mcp": {
    "my-mcp": {
      "type": "local",
      "command": "python",
      "args": ["/path/to/server.py", "--arg", "value"]
    }
  }
}
```
MCP tools are then available to agents with `tools: { "my-mcp_*": true }`.
