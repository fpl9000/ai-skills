# Stateful Agent System: Detailed Design – Chapter 8

**Version:** 2.0 (Draft)  
**Date:** February - June 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)  
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
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

These are standard Go tests (`go test ./...`) that test the bridge in isolation. Memory tool tests use a temporary memory directory per test.

#### 8.1.1 memory_start_conversation Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Basic conversation start | No params | Returns unique 8-char handle, `core` content, derived `index` |
| Handle uniqueness | Create 1,000 handles | All handles are distinct |
| Handle format | Create handle | Matches `[0-9a-z]{8}` (lowercase alphanumeric, opaque) |
| Empty memory store | No core.md, empty blocks dir | Returns empty `core` string and empty `index` array (no error) |
| Handle registered in state | Create handle, inspect handle map | Handle present with empty branch map and empty read baselines |
| Handle survives compaction round-trip | Create handle, simulate fresh tool call with same handle | All memory tools accept the handle (no re-init required after context compaction) |
| State checkpoint on creation | Create handle | `.bridge-state.json` updated (debounced) to include new handle |

#### 8.1.2 memory_get_core and memory_get_block Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Read core | Valid handle | Returns core.md content (no frontmatter handling — core has none), records read baseline |
| Read existing block | Valid handle + block name | Returns block body **without** YAML frontmatter, records read baseline |
| Frontmatter stripped on read | Block with summary/updated_at frontmatter | Returned content contains no `---` frontmatter delimiters |
| Read non-existent block | Valid handle + unknown name | Error `BLOCK_NOT_FOUND` |
| Invalid block name | Name with path separators or `..` | Error `INVALID_BLOCK_NAME` (no path traversal possible — names, not paths) |
| Unknown handle | Well-formed but unregistered handle | Error `INVALID_HANDLE` |
| Malformed handle | Handle not matching format | Error `MALFORMED_HANDLE` |
| changed_since_last_read: first read | Handle reads block for the first time | `changed_since_last_read: false` |
| changed_since_last_read: unchanged | Read, no intervening writes, read again | `changed_since_last_read: false` |
| changed_since_last_read: changed | Handle A reads, handle B writes, handle A reads again | `changed_since_last_read: true` for handle A |
| Read-your-own-writes | Handle writes block, then reads it | Sees its own content; `changed_since_last_read: false` |
| Branched read routing | Handle has a branch of the block | Read returns the **branch** content, not the base; response is indistinguishable from a normal read |
| Handle echo | Any successful or failed call | Response includes the `handle` field |

#### 8.1.3 memory_write_core and memory_write_block Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Write new block | Valid handle + new name + content + summary | Block file created with bridge-generated YAML frontmatter (summary, updated_at) |
| New block without summary | New name + content, no summary | Error `SUMMARY_REQUIRED` |
| Summary too long | Summary > `memory.summary_max_length` (default 200) | Error `SUMMARY_TOO_LONG` |
| Update existing block, no summary | Existing block + new content | Existing frontmatter summary preserved; updated_at refreshed |
| Update existing block, new summary | Existing block + content + summary | Frontmatter summary replaced; updated_at refreshed |
| Write core | Valid handle + content | core.md replaced atomically; **no** frontmatter added |
| Atomic replacement | Write while another goroutine reads | Reader sees either old or new content, never partial (temp file + rename) |
| Temp file cleanup on failure | Simulate write error | Temp file cleaned up, error `INTERNAL_ERROR` returned |
| Frontmatter is bridge-private | Write content that itself starts with `---` | Content stored verbatim in body; bridge frontmatter remains separate and well-formed |
| Unknown handle | Unregistered handle | Error `INVALID_HANDLE`; no file modified |
| First write without prior read | Handle writes block it never read | No race possible; write goes to base block |

#### 8.1.4 memory_append_block and memory_append_episodic Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Append to existing block | Valid handle + name + text | Text appended after existing body; frontmatter untouched except updated_at |
| Append to non-existent block | Unknown name + text | Error `BLOCK_NOT_FOUND` (appends do not create blocks — use memory_write_block) |
| Empty text | Valid name + empty string | Success (no-op; updated_at unchanged) |
| Append never branches | Handle A reads, handle B writes, handle A appends | Append applied to the base block (serialized under mutex); no branch created |
| Append routes to existing branch | Handle already has a branch of the block, then appends | Append applied to the handle's branch (preserves the handle's consistent view) |
| Episodic append creates monthly file | First memory_append_episodic of the month | `episodic-YYYY-MM.md` created with bridge-generated frontmatter (summary "Conversation log for <Month YYYY>") |
| Episodic month rotation | Append in month M, then in month M+1 | Two monthly files exist; each entry in the correct file |
| Episodic entries timestamped | Two appends | Entries appear in order with bridge-added timestamps |
| Episodic blocks indexed | After first episodic append | `memory_get_index` includes the episodic block with its summary |
| Episodic readable as block | memory_get_block("episodic-YYYY-MM") | Returns the log body (frontmatter stripped) |

#### 8.1.5 Derived Index Tests (memory_get_index)

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| Empty blocks directory | No block files | Returns empty index array |
| Index reflects frontmatter | Three blocks with known summaries | Index entries match each block's summary and updated_at exactly |
| Sorted by name | Blocks created out of order | Index entries sorted lexicographically by block name |
| Timestamps in extended ISO 8601 | Any indexed block | `updated_at` values use extended ISO 8601 (e.g., `2026-05-20T14:23:00Z`) in the JSON |
| No index file on disk | Call memory_get_index | No `index.md` (or any index file) is created — index is purely derived |
| Branch files excluded | Block has a branch file from another handle | Branch file does not appear as an index entry |
| Bridge state file excluded | `.bridge-state.json` present | Does not appear in the index |
| Missing frontmatter tolerated | Hand-created block with no frontmatter | Index entry present with empty/placeholder summary; no error (user-editable transparency preserved) |
| Per-handle cache correctness | Read index, write a block, read index again | Second read reflects the write (cache invalidated on write) |
| Index reflects own branch | Handle with a branched block reads index | Entry shows the handle's branch summary/updated_at (consistent per-handle view) |

#### 8.1.6 Per-Handle Branching Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| No race (normal write) | Handle reads block, no other writes, handle writes | Write goes to base block; no branch created |
| Race detected → branch created | Handle A reads, handle B writes, handle A writes | A's write goes to a new branch file; base block untouched; A's response identical in shape to the no-race case (branching invisible) |
| Branch naming format | Trigger a branch for handle `h7k3xy90` | Branch filename matches `<basename>.branch-h7k3xy90-<YYYYMMDD>T<HHMMSS>Z.<ext>` |
| Branch timestamp frozen | Write to the branch repeatedly | Branch filename timestamp never changes (creation time, informational only) |
| Branch isolation | Handles A and B both branched on the same block | Each handle's reads/writes route to its own branch; neither sees the other's branch |
| Subsequent reads route to branch | After branch creation, handle reads the block | Branch content returned, `changed_since_last_read: false` |
| Subsequent writes route to branch | After branch creation, handle writes again | Branch file updated; base still untouched; no second branch created |
| No branches of branches | Base changes again while handle has a branch | Handle continues using its single branch; no nested branching |
| External (user) edit detected as race | Handle reads, user edits the file in a text editor, handle writes | Branch created (version signature = ModTime + size changed) |
| Branching disabled | `branching.enabled: false`, trigger race | Last-writer-wins; write goes to base block |
| Race on core | Handle A reads core, B writes core, A writes core | core.md branches like any block (`core.branch-...md`) |

#### 8.1.7 memory_run_maintenance Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| No pending branches | Clean memory dir | Returns immediately: `merged_blocks: 0`, `more_pending: false` |
| Single branch merged | One branch file | Semantic-merge sub-agent invoked; merged result written to base by the **bridge**; branch file deleted; `merged_blocks: 1` |
| Multiple branches, under cap | 3 branches, `max_blocks_per_call: 10` | All merged in one call; `more_pending: false` |
| Multiple branches, over cap | 15 branches, cap 10 | First call merges 10, `more_pending: true`; second call merges 5, `more_pending: false` |
| Orphaned branches merged | Branch whose handle is no longer live | Merged anyway (maintenance merges all branches on disk regardless of handle liveness) |
| Branch map cleared after merge | Handle with branch, run maintenance | Handle's branch-map entry removed; handle's next read returns merged base content with `changed_since_last_read: true` |
| Merge mutex held | Concurrent write attempted during a merge | Write blocks until merge completes (or `MAINTENANCE_IN_PROGRESS` if blocking too long) |
| Handle eviction sweep | Handle with zero branches, inactive > `retention_days` | Handle evicted during maintenance; subsequent use returns `INVALID_HANDLE` |
| Active handle not evicted | Handle inactive > retention but has a branch | Handle retained (eviction requires zero branches AND inactivity) |
| Merge failure handling | Merge sub-agent fails/times out | Branch left intact for retry; error recorded in `errors` array; other merges proceed |

#### 8.1.8 Bridge State Persistence Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| State written at shutdown | Create handles/branches, close stdin (EOF) | `.bridge-state.json` contains live handles, branch maps, read baselines, last-activity |
| Debounced checkpoint | Burst of memory operations | State file written at most once per `checkpoint_interval_seconds` (default 5) |
| Immediate checkpoint on branch creation | Trigger a branch | State file written immediately (not debounced) |
| Atomic state write | Kill bridge mid-checkpoint (simulated) | State file is either old or new version, never partial (temp + rename) |
| Load and reconcile at startup | Restart bridge with valid state file | Handles, branch maps, and baselines restored; pre-restart handles work without re-init |
| Reconcile removes stale entries | State references a branch file deleted on disk | Entry dropped during reconcile; no error |
| Corrupt state file | Truncated/invalid JSON | Bridge starts cleanly, logs warning, falls back to lazy adoption |
| Lazy adoption | No state file, branch files `*.branch-<handle>-*` on disk | Handle resurrected from filename on first use; branch routing restored |
| Lazy adoption of unknown handle | Tool call with handle matching an on-disk branch file | Handle adopted, branch map rebuilt for that handle |

#### 8.1.9 Write Mutex Serialization Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| Concurrent writes | Two goroutines call memory_write_block on the same block simultaneously | One write completes fully before the other starts; second is branch-routed or applied per race rules; file never contains interleaved content |
| Write + append concurrent | One goroutine writes block X, another appends to block Y | Both serialize; both files correct |
| Mutex does not deadlock | Rapid alternation of reads, writes, appends, index calls | All operations complete within timeout |
| Index derivation under mutex | memory_get_index concurrent with writes | Index reflects a consistent point-in-time view |

#### 8.1.10 Error Response Convention Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Error shape | Any failing memory tool call | Response is `{ handle, ok: false, error: { code, message [, context] } }` |
| Known error codes | Trigger each failure mode | Codes drawn from: `INVALID_HANDLE`, `MALFORMED_HANDLE`, `BLOCK_NOT_FOUND`, `INVALID_BLOCK_NAME`, `SUMMARY_REQUIRED`, `SUMMARY_TOO_LONG`, `MAINTENANCE_IN_PROGRESS`, `INTERNAL_ERROR` |
| No abstraction leaks | Inspect every error message produced by the test suite | No message mentions branches, branch filenames, the mutex, frontmatter, or filesystem paths |
| Uniform recovery | `INVALID_HANDLE` on any tool | Calling memory_start_conversation and retrying with the new handle succeeds |

#### 8.1.11 spawn_agent Tests

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

#### 8.1.12 check_agent Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| Unknown job_id | Poll with fabricated ID | Error: "Unknown job_id" |
| Running job | Start slow mock, poll immediately | `status: "running"`, `elapsed_seconds` > 0 |
| Completed job | Start fast mock, wait, then poll | `status: "complete"`, result contains output |
| Already collected | Poll same job_id twice after completion | Second poll returns error (job cleaned up) |
| Expired job | Wait past job_expiry_seconds, then poll | Error: "Unknown job_id" (cleaned up) |
| Source field (spawn_agent) | Spawn agent, poll | `source: "spawn_agent"` in response |
| Source field (run_command) | Run command (async), poll | `source: "run_command"` in response |

#### 8.1.13 run_command Tests

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

#### 8.1.14 Job Lifecycle Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Cleanup goroutine runs | After job_expiry_seconds, uncollected jobs are removed |
| Graceful shutdown | All active subprocesses are killed, state checkpoint written, bridge exits cleanly |
| Job ID uniqueness | 1000 sequential job IDs are all unique |
| Mixed job sources | Jobs from both spawn_agent and run_command coexist in job manager |

#### 8.1.15 MCP Integration Tests

These tests verify the bridge works correctly as an MCP server. Use the `mcp-go` SDK's test utilities or send raw JSON-RPC messages over a pipe.

| Test Case | Expected Behavior |
|-----------|-------------------|
| MCP initialization handshake | Bridge responds with capabilities and tool list |
| Tool listing | Returns all twelve tools: memory_start_conversation, memory_get_core, memory_write_core, memory_get_index, memory_get_block, memory_write_block, memory_append_block, memory_append_episodic, memory_run_maintenance, spawn_agent, check_agent, run_command |
| Tool call with valid params | Returns well-formed MCP result |
| Tool call with missing required param | Returns MCP error with descriptive message |
| Missing handle param on memory tool | Returns MCP error (handle is required on all memory tools except memory_start_conversation) |
| Two concurrent tool calls (via pipe) | Both complete correctly (test serialization) |

### 8.2 Memory Skill Tests

Memory skill testing is behavioral — it verifies that Claude follows the SKILL.md instructions correctly in actual conversations. These are manual tests (or semi-automated via `claude -p` scripting).

#### 8.2.1 Conversation Start Compliance

**Test procedure:**
1. Ensure the memory store has core content and several blocks with known summaries.
2. Start a new Claude Desktop conversation.
3. Send a message: "What do you know about me?"
4. Verify (via bridge log) that Claude called `memory_start_conversation` first.
5. Verify Claude's response incorporates content from the returned core and index (no extra read calls should be needed — both arrive in the start response).

**Pass criteria:** Claude calls `memory_start_conversation` before any other memory tool and integrates the core/index content naturally.

#### 8.2.2 Conversation Start — Cold Start

**Test procedure:**
1. Empty the memory store (remove core.md and all blocks).
2. Start a new conversation.
3. Send a message: "Hi, what are we working on?"
4. Verify Claude recognizes the empty core/index as a first-run scenario and seeds initial content via `memory_write_core` (and optionally `memory_write_block`).

**Pass criteria:** Claude seeds reasonable initial content derived from Layer 1 memory, using only memory-aware tools.

#### 8.2.3 Memory Write — Project Update

**Test procedure:**
1. Start a conversation with seeded memory.
2. Discuss a specific project that has a block (e.g., "The MCP bridge is now feature-complete and passing all tests.")
3. Check whether Claude updates the project block (via `memory_write_block` or `memory_append_block`) and/or the core during or at the end of the conversation.
4. Verify the update is factually correct and concise.

**Pass criteria:** The project block reflects the new status. A subsequent `memory_get_index` shows a current `updated_at` for that block.

#### 8.2.4 Episodic Log Entry

**Test procedure:**
1. Have a substantive conversation (at least 10 exchanges).
2. End the conversation with "Thanks, that's all for now."
3. Verify (via bridge log) a `memory_append_episodic` call, and check `blocks/episodic-YYYY-MM.md` for the new entry.

**Pass criteria:** A dated entry exists summarizing the session's key topics and outcomes.

#### 8.2.5 Block Creation

**Test procedure:**
1. Introduce a new project in conversation: "I'm starting a new project called 'dashboard-v2' to rebuild our analytics dashboard in React."
2. Discuss it for several exchanges (goals, tech stack, timeline).
3. Check whether Claude creates the block via `memory_write_block` with a name like `project-dashboard-v2` **and a summary** (required for new blocks).

**Pass criteria:** New block file exists with reasonable content and frontmatter. The derived index shows the new block with Claude's summary.

#### 8.2.6 Correct Tool Usage (Memory-Aware Tools Only)

**Test procedure:**
1. Monitor the bridge log and Claude Desktop's tool usage during a memory session.
2. Verify that `memory_start_conversation` was called before any other memory tool.
3. Verify that all memory reads and writes use the bridge's memory tools, addressed by block *name*.
4. Verify that every memory tool call includes the handle returned by `memory_start_conversation`.
5. Verify that no memory operations use `Filesystem:read_file`, `Filesystem:write_file`, `Filesystem:edit_file`, `Filesystem:search_files`, `bash_tool`, `create_file`, or `str_replace` on the memory directory.

**Pass criteria:** All memory operations go through the bridge's memory-aware tools with a valid handle. No Filesystem extension or cloud VM tools touch the memory directory.

#### 8.2.7 Error Recovery Compliance

**Test procedure:**
1. Mid-conversation, restart the bridge with a deliberately removed state file (so the LLM's handle becomes unknown and lazy adoption cannot resurrect it — no branches exist).
2. Ask Claude to update a block.
3. Verify Claude receives `INVALID_HANDLE`, calls `memory_start_conversation` to obtain a fresh handle, and retries the write successfully — without asking the user for help.

**Pass criteria:** Claude follows the uniform recovery protocol (re-init and retry) transparently.

#### 8.2.8 Compliance Monitoring Script

A simple post-session check script can verify compliance by examining the bridge log:

```
Pseudo-code for compliance-check.sh:

1. Parse bridge.log for the most recent conversation (entries since last
   memory_start_conversation)
2. Check: Was memory_start_conversation the first memory tool call?
3. Check: Did every memory tool call carry the same handle?
4. Check: Were any blocks written or appended? (Look for memory_write_*,
   memory_append_*)
5. If conversation lasted > 5 tool calls but never started a memory
   conversation: FLAG "Skill not loading memory"
6. If conversation lasted > 10 tool calls but no memory writes at all:
   FLAG "Skill not persisting"
7. Report summary
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

#### 8.4.1 Full Conversation Lifecycle

**Procedure:**
1. Seed memory with known content.
2. Open Claude Desktop and start a conversation.
3. Verify the conversation start protocol (`memory_start_conversation` called; core and index used).
4. Discuss a topic that triggers a block read (`memory_get_block`).
5. Provide new information that should be persisted.
6. End the conversation.
7. Check the memory store (via a text editor — transparency!) for expected updates.
8. Start a NEW conversation and verify continuity (Claude remembers previous session's updates).

**Pass criteria:** Memory persists across conversations. Second session demonstrates awareness of first session's changes.

#### 8.4.2 Concurrent Conversations and Maintenance

**Procedure:**
1. Open two Claude Desktop conversations (A and B) against the same bridge.
2. In A, read a project block. In B, update the same block. In A, update the block.
3. Verify (on disk) that A's update created a branch file and the base block holds B's version — and that neither conversation's responses mention branching.
4. In A, ask: "Please run memory maintenance" (repeating while `more_pending` is true).
5. Verify the branch is merged into the base block, the branch file is gone, and a subsequent read in A returns the merged content with `changed_since_last_read: true`.

**Pass criteria:** Race produces a branch invisibly; maintenance merges it; both conversations' contributions survive in the merged block.

#### 8.4.3 Sub-Agent Within Conversation

**Procedure:**
1. Start a conversation about a coding project.
2. Ask Claude to "spawn a sub-agent to find all TODO comments in the project."
3. Verify the sub-agent is spawned, results returned, and Claude integrates them into the conversation.
4. Ask Claude to persist the findings to the project block.
5. Verify the block is updated via `memory_write_block` or `memory_append_block`.

**Pass criteria:** Sub-agent results are seamlessly incorporated into conversation and persisted to memory.

#### 8.4.4 Bridge Restart Mid-Conversation

**Procedure:**
1. Start a conversation; trigger a branch (as in 8.4.2 steps 1–3).
2. Restart the bridge (Claude Desktop relaunches it automatically).
3. Continue the conversation: read and write the branched block.
4. Verify the handle still works (state restored from `.bridge-state.json`) and branch routing is preserved.

**Pass criteria:** The conversation continues seamlessly across the bridge restart; no `INVALID_HANDLE` errors; the branch is still routed correctly.

#### 8.4.5 Concurrent Tool Usage

**Procedure:**
1. Start a conversation that requires both bridge tools and Filesystem extension tools (memory operations plus reading a source file outside the memory directory).
2. Verify Claude uses the bridge's memory tools for memory and `Filesystem:read_file` for the non-memory file.
3. Verify there are no tool name collisions or routing errors.

**Pass criteria:** Both MCP servers work simultaneously without interference, with a clean memory/non-memory division.

### 8.5 Acceptance Criteria

The system is considered ready for daily use when:

| # | Criterion | Verified by |
|---|-----------|-------------|
| AC1 | Bridge starts and registers all 12 tools with Claude Desktop | MCP integration tests 8.1.15 |
| AC2 | spawn_agent completes fast tasks synchronously (< 25s) | Sub-agent test 8.3.1 |
| AC3 | spawn_agent handles slow tasks asynchronously (> 25s) | Sub-agent test 8.3.4 |
| AC4 | check_agent returns correct status and results for both spawn_agent and run_command jobs | check_agent tests 8.1.12 |
| AC5 | run_command executes simple commands and returns stdout/stderr/exit_code | run_command tests 8.1.13 |
| AC6 | run_command uses hybrid sync/async model for long-running commands | run_command tests 8.1.13 |
| AC7 | memory_start_conversation returns a unique handle plus core and index in one round trip | Tests 8.1.1 |
| AC8 | All memory tools require and echo the handle; INVALID_HANDLE recovery works via re-init and retry | Tests 8.1.2, 8.1.10; skill test 8.2.7 |
| AC9 | memory_write_block creates/updates blocks with bridge-managed frontmatter (summary required for new blocks) | Tests 8.1.3 |
| AC10 | Appends are serialized, never create branches, and route to an existing branch if one exists | Tests 8.1.4 |
| AC11 | memory_get_index derives the index from block frontmatter with no stored index file | Tests 8.1.5 |
| AC12 | Read-modify-write races create per-handle branches invisibly; per-handle routing gives each conversation a consistent view | Branching tests 8.1.6; integration test 8.4.2 |
| AC13 | memory_run_maintenance merges branches (respecting max_blocks_per_call / more_pending) and sweeps stale handles | Tests 8.1.7 |
| AC14 | Bridge state survives restarts (state file + reconcile), with lazy adoption as fallback | Tests 8.1.8; integration test 8.4.4 |
| AC15 | Error responses follow the convention and never leak branches, mutexes, frontmatter, or paths | Tests 8.1.10 |
| AC16 | Memory skill starts every conversation with memory_start_conversation and uses memory-aware tools exclusively | Skill tests 8.2.1, 8.2.6 |
| AC17 | Memory skill writes updates during conversation and creates episodic log entries | Skill tests 8.2.3, 8.2.4 |
| AC18 | Memory persists across conversations | Integration test 8.4.1 |
| AC19 | Sub-agent directory sandbox blocks unauthorized access | Sub-agent test 8.3.3 |
| AC20 | Both MCP servers (bridge + filesystem) work simultaneously | Integration test 8.4.5 |
| AC21 | No memory operations use cloud VM tools or the Filesystem extension | Skill test 8.2.6 |
