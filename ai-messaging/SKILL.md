---
name: ai-messaging
description: >
  Communicate with the local stateful agent system via the GitHub relay.
  Use this skill when the user wants to interact with their local machine
  remotely — reading memory files, running shell commands, or delegating
  tasks to the local Claude Desktop agent. Triggers include phrases like:
  "on my local machine", "check my local files", "run this on my home
  computer", "ask my local Claude", "read my memory files", "what's in
  my core memory", "what's on my home machine", "run this locally".
  Requires the github skill for relay transport scripts.
---

# AI Messaging Skill

This skill enables Claude.ai (web or mobile) to communicate with the local
stateful agent system running on Fran's home machine. It uses the GitHub relay
transport protocol (provided by the github skill) to send signed requests to
the local MCP bridge and receive signed responses.

## Prerequisites

- The **github skill** must be installed (provides `relay_send.py`,
  `relay_receive.py`, and `relay_common.py` in its `scripts/` directory).
- Environment variables `GITHUB_TOKEN` and `RELAY_HMAC_SECRET` must be set
  (available via personal instructions).
- The relay repository is `fpl9000/claude-relay`.

## When to Use This Skill

Use this skill when the user wants to do something that requires their local
machine — a Windows 11 system running the MCP bridge server. Common triggers:

- "Read my core memory" / "What's in my memory files?"
- "Run this on my local machine" / "Check something on my home computer"
- "Ask my local Claude to..." / "Have Claude Desktop do..."
- "What's the status of [project] locally?"
- "Run `git status` on my mcp-bridge repo"
- Any reference to the local machine, local files, or the stateful agent system

Do NOT use this skill for operations that can be performed directly from
Claude.ai (e.g., reading GitHub repos via the github skill's existing scripts,
web searches, or general knowledge questions).

## Operations

The relay supports three operations. Choose the simplest one that can
accomplish the task.

### memory_query

Read a file from the local Layer 2 memory directory
(`C:\franl\.claude-agent-memory\`). The MCP bridge handles this directly
with no LLM inference — it simply reads the file and returns its contents.

**When to use:** The user wants to see the contents of a specific memory
file (core.md, index.md, or a block).

**Arguments:**
```json
{"path": "core.md"}
```

The `path` is relative to the memory directory. Valid paths include:
- `core.md` — Identity and active project summary
- `index.md` — Block index table
- `blocks/project-mcp-bridge.md` — A specific content block
- `blocks/episodic-2026-03.md` — A specific episodic log

**Example invocation:**
```bash
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction request \
    --operation memory_query \
    --arguments '{"path":"core.md"}'
```

**Response format:** `result.content` contains the full UTF-8 text of the file.
If the file does not exist, `result.success` is `false` and `result.error`
describes the problem.

### shell_command

Execute a shell command on the local machine via Cygwin bash. The MCP bridge
handles this directly with no LLM inference — it runs the command and returns
stdout/stderr. This is equivalent to the bridge's `run_command` tool.

**When to use:** The task can be expressed as a single shell command or short
pipeline and requires no LLM reasoning. Examples: `git status`, `ls -la`,
`grep -r 'TODO' src/`, `cat some-file.txt`, `wc -l *.go`.

**Arguments:**
```json
{
  "command": "cd /c/franl/git/mcp-bridge && git log --oneline -5",
  "timeout_seconds": 60
}
```

- `command` (required) — The shell command to execute.
- `timeout_seconds` (optional, default: 120) — Maximum runtime before the
  command is killed.

**Example invocation:**
```bash
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction request \
    --operation shell_command \
    --arguments '{"command":"cd /c/franl/git/mcp-bridge && git log --oneline -5"}'
```

**Response format:** `result.content` contains the combined stdout+stderr.
`result.exit_code` contains the process exit code (0 = success).
`result.timed_out` is `true` if the command exceeded its timeout.

### claude_prompt

Forward a prompt to Claude Desktop for full agent-loop processing. Claude
Desktop receives the prompt, performs whatever tool calls it deems appropriate
(reading memory, running commands, spawning sub-agents, writing memory
updates), and returns its final response.

**When to use:** The task requires LLM reasoning, multi-step tool use, or
memory writes. Examples:
- "Summarize today's episodic log and update core.md"
- "Read the mcp-bridge project block and tell me what the open issues are"
- "Refactor the error handling in server.go"
- "Create a new memory block for the dashboard-v2 project"

**Arguments:**
```json
{
  "prompt": "Read the mcp-bridge project block and summarize the current open issues."
}
```

- `prompt` (required) — The task prompt for Claude Desktop. Write it as if
  you were typing directly into Claude Desktop's input field. Be specific
  and self-contained — Claude Desktop does not have context from the
  current Claude.ai conversation.

**Example invocation:**
```bash
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction request \
    --operation claude_prompt \
    --arguments '{"prompt":"Read the mcp-bridge project block and summarize the current open issues."}'
```

**Response format:** `result.content` contains Claude Desktop's final text
response. This may be lengthy if the task involved analysis or summarization.

## Decision Tree

When the user asks you to do something on their local machine, choose the
operation using this decision tree:

1. **Is the user asking to read a specific memory file?**
   → Use `memory_query`. This is instant (no inference) and costs nothing.

2. **Can the task be expressed as a single shell command?**
   → Use `shell_command`. Fast, cheap, no inference involved.

3. **Does the task require LLM reasoning, multi-step actions, or memory writes?**
   → Use `claude_prompt`. This is the most capable but slowest option.

When in doubt, prefer the simpler operation. You can always escalate — for
example, if a `memory_query` reveals that you need to read multiple files
and synthesize them, follow up with a `claude_prompt`.

## End-to-End Workflow

Here is the complete sequence for a typical relay interaction:

1. **User asks:** "What are my active projects on my local machine?"

2. **Choose operation:** This is a memory file read → `memory_query` for `core.md`.

3. **Send the request:**
   ```bash
   export GITHUB_TOKEN="..."
   export RELAY_HMAC_SECRET="..."
   ID=$(uv run scripts/relay_send.py fpl9000/claude-relay \
       --direction request \
       --operation memory_query \
       --arguments '{"path":"core.md"}')
   ```

4. **Inform the user:** "I've sent a request to your local machine to read
   your core memory file. I'll check for a response in about 2 minutes."

5. **Poll for the response** (after minimum interval):
   ```bash
   uv run scripts/relay_receive.py fpl9000/claude-relay \
       --direction response \
       --id "$ID"
   ```

6. **Handle the result:**
   - If exit code 0: Parse the verified response and present the content
     to the user naturally.
   - If exit code 1 (not found): Wait longer, then poll again (with backoff).
   - If exit code 2 (HMAC failed): Alert the user to a potential security issue.
   - If max attempts reached: Inform the user their machine may be offline.

7. **Present the answer:** Summarize the core.md contents in response to
   the user's question.

## Important Notes

- **The local machine must be running.** The MCP bridge polls the relay repo
  periodically (default: every 15 seconds). If the machine is off, sleeping,
  or the bridge is not running, requests will go unanswered.

- **Latency is inherent.** Round-trip times of 1–5 minutes are normal for
  bridge-local operations; `claude_prompt` may take 5–15 minutes depending
  on task complexity. Set expectations with the user.

- **Prompts for `claude_prompt` must be self-contained.** Claude Desktop
  does not have access to the current Claude.ai conversation. Include all
  necessary context in the prompt itself.

- **HMAC failures are serious.** If `relay_receive.py` reports an HMAC
  verification failure, do not use the response content. Report the issue
  to the user.

- **One request at a time.** Do not send multiple relay requests
  simultaneously. Wait for each response (or timeout) before sending
  the next request. This simplifies the interaction and avoids overwhelming
  the bridge's polling loop.
