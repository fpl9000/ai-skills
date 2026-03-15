# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>

**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Contents

- [8. Testing Strategy](#8-testing-strategy)
  - [8.1 MCP Bridge Server Tests](#81-mcp-bridge-server-tests)
  - [8.2 Memory Skill Tests](#82-memory-skill-tests)
  - [8.3 Sub-Agent Tests](#83-sub-agent-tests)
  - [8.4 Integration Tests](#84-integration-tests)
  - [8.5 Acceptance Criteria](#85-acceptance-criteria)

## 8. Testing Strategy

Testing covers four levels: bridge unit tests, memory skill behavioral tests, sub-agent integration tests, and full system end-to-end tests.

### 8.1 MCP Bridge Server Tests

These are standard Go tests (`go test ./...`) that test the bridge in isolation.

#### 8.1.1 safe_write_file Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Write to new file | Path to non-existent file + content | File created with content, parent dirs created |
| Write to existing file | Path to existing file + new content | File replaced atomically with new content |
| Path outside memory dir | Path under `C:\temp\` | Error: "restricted to memory directory" |
| Path traversal attempt | Path with `..` escaping memory dir | Error: path validation rejects it |
| Empty content | Valid path + empty string | Success (creates/replaces with empty file) |
| Temp file cleanup on failure | Simulate write error (e.g., disk full) | Temp file is cleaned up, error returned |
| Atomic replacement | Write while another thread reads | Reader sees either old or new content, never partial |
| Returns path in response | Any valid write | Response includes the absolute path that was written |

#### 8.1.1a safe_append_file Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Append to new file | Path to non-existent file + text | File created with text content |
| Append to existing file | Path to existing file + text | Text appended after existing content |
| Path outside memory dir | Path under `C:\temp\` | Error: "restricted to memory directory" |
| Path traversal attempt | Path with `..` escaping memory dir | Error: path validation rejects it |
| Empty text | Valid path + empty string | Success (no-op write, 0 bytes) |
| Parent dir creation | Path where parent dir doesn't exist | Parent directories created, file written |

#### 8.1.1b Write Mutex Serialization Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| Concurrent safe_write_file calls | Two goroutines write different content to the same file simultaneously | One write completes fully before the other starts; file contains one version, not a mix |
| safe_write_file + safe_append_file concurrent | One goroutine writes, another appends to a different file | Both operations serialize; both files are correct |
| Mutex does not deadlock | Rapid alternation of safe_write_file and safe_append_file | All operations complete within timeout |

#### 8.1.2 spawn_agent Tests

Testing `spawn_agent` requires mocking the `claude -p` subprocess. The bridge should accept a configurable command path (already in config as `claude_cli.path`), allowing tests to substitute a mock script.

**Mock sub-agent script (for testing):**

```bash
#!/bin/bash
# mock-claude.sh — simulates claude -p behavior for testing
# Reads task from stdin, echoes a response after a configurable delay

DELAY=${MOCK_DELAY:-0}  # seconds to wait before responding
sleep $DELAY
echo "Mock sub-agent received task: $(cat)"
echo "System prompt was: (not captured in this mock)"
echo "Working directory: $(pwd)"
```

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| Sync completion (fast task) | Mock delay = 0s | Returns `status: "complete"`, `job_id: null`, `result` contains output |
| Async handoff (slow task) | Mock delay = 30s | Returns `status: "running"`, `job_id` is non-null, result is null |
| Async completion via check_agent | Mock delay = 30s, then poll | `check_agent` eventually returns `status: "complete"` with output |
| Subprocess timeout | Mock delay = 999s, timeout = 5s | `check_agent` returns `status: "timed_out"` |
| Subprocess crash | Mock script exits with code 1 | Returns `status: "complete"` (or "failed") with error details |
| Concurrent agent cap | Spawn 6 agents (cap = 5) | 6th spawn returns error |
| Output truncation | Mock produces 100KB output, max_output_tokens = 100 | Output truncated with marker |
| Working directory | Set working_directory to specific dir | Mock reports correct CWD |
| Invalid command | claude_cli.path = "/nonexistent" | Returns error: "failed to start" |

#### 8.1.3 check_agent Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| Unknown job_id | Poll with fabricated ID | Error: "Unknown job_id" |
| Running job | Start slow mock, poll immediately | `status: "running"`, `elapsed_seconds` > 0 |
| Completed job | Start fast mock, wait, then poll | `status: "complete"`, result contains output |
| Already collected | Poll same job_id twice after completion | Second poll returns error (job cleaned up) |
| Expired job | Wait past job_expiry_seconds, then poll | Error: "Unknown job_id" (cleaned up) |
| Source field (spawn_agent) | Spawn agent, poll | `source: "spawn_agent"` in response |
| Source field (run_command) | Run command (async), poll | `source: "run_command"` in response |

#### 8.1.4 run_command Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| Simple command (sync) | `run_command("echo hello")` | `status: "complete"`, `stdout` contains "hello", `exit_code: 0` |
| Failing command (sync) | `run_command("false")` | `status: "complete"`, `exit_code: 1` |
| Long-running command (async) | `run_command("sleep 60")` | `status: "running"`, `job_id` is non-null |
| Async completion via check_agent | `run_command("sleep 30")`, then poll | `check_agent` returns `status: "complete"`, `source: "run_command"` |
| Command timeout | `run_command("sleep 999", timeout_seconds=5)` | `check_agent` returns `status: "timed_out"` |
| Output truncation | `run_command("seq 1 1000000")`, max_output_bytes=1024 | Output truncated with middle-truncation marker, `truncated: true` |
| Working directory | `run_command("pwd", working_directory="/tmp")` | stdout contains "/tmp" |
| Shell configuration | Configure custom shell path | Command executed via configured shell |
| Invalid shell | Set run_command.shell to "/nonexistent" | Returns error: "Failed to start process" |
| Empty command | `run_command("")` | Returns error: "command is required" |
| Stderr capture | `run_command("echo error >&2")` | stderr contains "error" |
| Pipeline | `run_command("echo hello \| tr a-z A-Z")` | stdout contains "HELLO" |

#### 8.1.5 Job Lifecycle Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Cleanup goroutine runs | After job_expiry_seconds, uncollected jobs are removed |
| Graceful shutdown | All active subprocesses are killed, bridge exits cleanly |
| Job ID uniqueness | 1000 sequential job IDs are all unique |
| Mixed job sources | Jobs from both spawn_agent and run_command coexist in job manager |

#### 8.1.6 MCP Integration Tests

These tests verify the bridge works correctly as an MCP server. Use the `mcp-go` SDK's test utilities or send raw JSON-RPC messages over a pipe.

| Test Case | Expected Behavior |
|-----------|-------------------|
| MCP initialization handshake | Bridge responds with capabilities and tool list |
| Tool listing | Returns spawn_agent, check_agent, run_command, safe_write_file, safe_append_file |
| Tool call with valid params | Returns well-formed MCP result |
| Tool call with missing required param | Returns MCP error with descriptive message |
| Two concurrent tool calls (via pipe) | Both complete correctly (test serialization) |

### 8.2 Memory Skill Tests

Memory skill testing is behavioral — it verifies that Claude follows the SKILL.md instructions correctly in actual conversations. These are manual tests (or semi-automated via `claude -p` scripting).

#### 8.2.1 Session Start Compliance

**Test procedure:**
1. Ensure memory directory has `core.md` and `index.md` with known content.
2. Start a new Claude Desktop conversation.
3. Send a message: "What do you know about me?"
4. Verify (via bridge log or observation) that Claude read `core.md` and `index.md` before responding.
5. Verify Claude's response incorporates content from the memory files.

**Pass criteria:** Claude reads both files before its first response and integrates the content naturally.

#### 8.2.2 Session Start — Cold Start

**Test procedure:**
1. Delete or rename `core.md` and `index.md`.
2. Start a new conversation.
3. Send a message: "Hi, what are we working on?"
4. Verify Claude detects the missing files and creates initial `core.md` and `index.md`.

**Pass criteria:** Claude creates the files with reasonable initial content derived from Layer 1 memory.

#### 8.2.3 Memory Write — Project Update

**Test procedure:**
1. Start a conversation with seeded memory.
2. Discuss a specific project that has a block (e.g., "The MCP bridge is now feature-complete and passing all tests.")
3. Check whether Claude updates the project block and/or `core.md` during or at the end of the conversation.
4. Verify the update is factually correct and concise.

**Pass criteria:** The project block reflects the new status. The `index.md` Updated column is current.

#### 8.2.4 Episodic Log Entry

**Test procedure:**
1. Have a substantive conversation (at least 10 exchanges).
2. End the conversation with "Thanks, that's all for now."
3. Check `blocks/episodic-YYYY-MM.md` for a new entry.

**Pass criteria:** A dated entry exists summarizing the session's key topics and outcomes.

#### 8.2.5 Block Creation

**Test procedure:**
1. Introduce a new project in conversation: "I'm starting a new project called 'dashboard-v2' to rebuild our analytics dashboard in React."
2. Discuss it for several exchanges (goals, tech stack, timeline).
3. Check whether Claude creates `blocks/project-dashboard-v2.md` and adds a row to `index.md`.

**Pass criteria:** New block file exists with reasonable content. Index row present.

#### 8.2.6 Correct Tool Usage (Mutex-Protected Writes Only)

**Test procedure:**
1. Monitor the bridge log and Claude Desktop's tool usage during a memory-writing session.
2. Verify that all writes to memory files use `Bridge:safe_write_file` or `Bridge:safe_append_file`.
3. Verify that no writes to the memory directory use `Filesystem:write_file`, `Filesystem:edit_file`, `bash_tool`, `create_file`, or `str_replace`.

**Pass criteria:** All memory writes go through the bridge's mutex-protected tools. No Filesystem extension writes or cloud VM tools used for memory files.

#### 8.2.7 Compliance Monitoring Script

A simple post-session check script can verify compliance by examining the bridge log:

```
Pseudo-code for compliance-check.sh:

1. Parse bridge.log for the most recent session (entries since last startup)
2. Check: Were core.md and index.md read? (Look for read_file tool calls)
3. Check: Were any memory files written? (Look for write_file, edit_file, append_file)
4. If session lasted > 5 tool calls but no memory reads at start: FLAG "Skill not loading memory"
5. If session lasted > 10 tool calls but no memory writes at all: FLAG "Skill not persisting"
6. Report summary
```

### 8.3 Sub-Agent Tests

#### 8.3.1 Basic Task Execution

**Test:** Spawn a sub-agent with a simple task using real `claude -p`:
```
spawn_agent(
  task: "List all .go files in the current directory and report the total count.",
  working_directory: "C:\franl\git\mcp-bridge"
)
```
**Pass criteria:** Returns a result listing the Go files with a correct count.

#### 8.3.2 Memory Read Access

**Test:** Spawn a sub-agent with `allow_memory_read: true`:
```
spawn_agent(
  task: "Read core.md from the memory directory and summarize the active projects.",
  allow_memory_read: true
)
```
**Pass criteria:** Sub-agent successfully reads and summarizes `core.md`.

#### 8.3.3 Memory Write Blocked (Sandbox)

**Test:** Spawn a sub-agent without memory access trying to read memory:
```
spawn_agent(
  task: "Read the file C:\franl\.claude-agent-memory\core.md and report its contents.",
  working_directory: "C:\franl\git\mcp-bridge"
)
```
**Pass criteria:** Sub-agent reports it cannot access the file (directory sandbox blocks it).

#### 8.3.4 Async Polling

**Test:** Spawn a sub-agent with a task that takes > 25 seconds:
```
spawn_agent(
  task: "Run the full test suite in this directory. Report all test results 
         including pass/fail counts and any failure details.",
  working_directory: "C:\franl\git\mcp-bridge",
  timeout_seconds: 120
)
```
**Pass criteria:** Returns `status: "running"` with a job_id. Subsequent `check_agent` calls eventually return `status: "complete"` with test results.

#### 8.3.5 Model Selection

**Test:** Spawn sub-agents with different models:
```
spawn_agent(task: "What model are you?", model: "sonnet")
spawn_agent(task: "What model are you?", model: "haiku")
```
**Pass criteria:** Each sub-agent reports the correct model.

### 8.4 Integration Tests

These test the complete system: Claude Desktop + MCP bridge + Filesystem extension + memory files.

#### 8.4.1 Full Session Lifecycle

**Procedure:**
1. Seed memory with known content.
2. Open Claude Desktop and start a conversation.
3. Verify session start protocol (core.md and index.md read).
4. Discuss a topic that triggers a block read.
5. Provide new information that should be persisted.
6. End the conversation.
7. Check all memory files for expected updates.
8. Start a NEW conversation and verify continuity (Claude remembers previous session's updates).

**Pass criteria:** Memory persists across conversations. Second session demonstrates awareness of first session's changes.

#### 8.4.2 Sub-Agent Within Conversation

**Procedure:**
1. Start a conversation about a coding project.
2. Ask Claude to "spawn a sub-agent to find all TODO comments in the project."
3. Verify the sub-agent is spawned, results returned, and Claude integrates them into the conversation.
4. Ask Claude to persist the findings to the project block.
5. Verify the block is updated.

**Pass criteria:** Sub-agent results are seamlessly incorporated into conversation and persisted to memory.

#### 8.4.3 Concurrent Tool Usage

**Procedure:**
1. Start a conversation that requires both bridge tools and filesystem extension tools.
2. Verify Claude uses `Bridge:append_file` for episodic logs and `Filesystem:read_file` for reading blocks.
3. Verify there are no tool name collisions or routing errors.

**Pass criteria:** Both MCP servers work simultaneously without interference.

### 8.5 Acceptance Criteria

The system is considered ready for daily use when:

| # | Criterion | Verified by |
|---|-----------|-------------|
| AC1 | Bridge starts and registers all 5 tools with Claude Desktop | MCP integration test |
| AC2 | spawn_agent completes fast tasks synchronously (< 25s) | Sub-agent test 8.3.1 |
| AC3 | spawn_agent handles slow tasks asynchronously (> 25s) | Sub-agent test 8.3.4 |
| AC4 | check_agent returns correct status and results for both spawn_agent and run_command jobs | check_agent tests 8.1.3 |
| AC5 | run_command executes simple commands and returns stdout/stderr/exit_code | run_command tests 8.1.4 |
| AC6 | run_command uses hybrid sync/async model for long-running commands | run_command tests 8.1.4 |
| AC7 | append_file atomically appends to files within memory dir | append_file tests 8.1.1 |
| AC8 | Memory skill loads core.md + index.md at session start | Skill test 8.2.1 |
| AC9 | Memory skill writes updates during conversation | Skill test 8.2.3 |
| AC10 | Memory skill creates episodic log entries | Skill test 8.2.4 |
| AC11 | Memory persists across conversations | Integration test 8.4.1 |
| AC12 | Sub-agent directory sandbox blocks unauthorized access | Sub-agent test 8.3.3 |
| AC13 | Both MCP servers (bridge + filesystem) work simultaneously | Integration test 8.4.3 |
| AC14 | No memory writes use cloud VM tools | Skill test 8.2.6 |
