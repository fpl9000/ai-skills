# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>

## Contents

NOTE: Chapter 9, "Future Enhancements", appears after the other chapters, because it is not targeted for near-term implementation.

- [1. Overview](#1-overview)
- [2. System Architecture](#2-system-architecture)
- [3. MCP Bridge Server](#3-mcp-bridge-server)
- [4. Memory System (Layer 2)](#4-memory-system-layer-2)
- [5. Memory Skill](#5-memory-skill)
- [6. Sub-Agent System](#6-sub-agent-system)
- [7. Build and Deployment](#7-build-and-deployment)
- [8. Testing Strategy](#8-testing-strategy)
- [10. References](#10-references)
- [11. Open Questions](#11-open-questions)
- [12. Appendix: mark3labs/mcp-go SDK Reference](#12-appendix-mark3labsmcp-go-sdk-reference)
- [9. Future Enhancements](#9-future-enhancements)


## 1. Overview

### 1.1 What We're Building

The stateful agent system consists of three components that together give Claude persistent memory, local machine access, and task delegation capabilities:

1. **MCP Bridge Server** — A Go binary that runs locally, providing Bash access, sub-agent spawning, and mutex-protected memory file writes to be used by the Claude Desktop App via the MCP protocol over stdio.

2. **Memory System (Layer 2)** — A directory of markdown files on the local filesystem that stores deep project context, episodic recall, decision history, and technical notes. This supplements Anthropic's built-in memory (Layer 1), which is limited to ~500–2,000 tokens.

3. **Memory Skill** — A Claude Desktop skill (.zip file) containing instructions that teach Claude how to manage the Layer 2 memory lifecycle: when to read files, when to write updates, how to structure content, and when to create new blocks.

### 1.2 Component Inventory

| Component | Type | Location | Purpose |
|-----------|------|----------|---------|
| MCP Bridge Server<br/>(aka "the bridge") | Go binary | `C:\franl\.claude-agent-memory\bin\mcp-bridge.exe` | Bash access, sub-agent spawning, mutex-protected memory reads/writes. Source code located in `C:\franl\git\mcp-bridge\` |
| Anthropic Filesystem Extension | MCP server | Installed via Claude Desktop | Basic filesystem tools (read, write, edit, list, search) |
| Memory directory | Markdown files | `C:\franl\.claude-agent-memory\` | Layer 2 persistent storage |
| Memory skill | .zip file | Uploaded via Claude Desktop Settings | Instructions for memory lifecycle |
| CLAUDE.md | Markdown file | `C:\Users\flitt\.claude\CLAUDE.md` | Sub-agent environment context |
| Bridge config | YAML file | `C:\franl\.claude-agent-memory\bridge-config.yaml` | Bridge runtime settings |

### 1.3 Design Principles

These principles are inherited from the proposal and govern all design decisions:

1. **Transparency.** All memory is stored in human-readable, human-editable markdown files. No opaque databases, no binary formats. The user can open any file in a text editor, review it, correct it, or delete it.

2. **Simplicity.** Start with the simplest approach that works. Add complexity (search indexes, memory-aware tools, parallel sub-agents) only when the simple approach proves insufficient in practice. Future enhancements are described in [Chapter 9](stateful-agent-design-chapter9.md).

3. **Single binary.** The MCP bridge compiles to a single static Go binary with no runtime dependencies. Installation is copying the `.exe` file.

4. **Bridge-mediated memory access with session tracking.** The bridge provides sub-agent lifecycle management tools (`spawn_agent`, `check_agent`), a direct local command execution tool (`run_command`), a session initialization tool (`memory_session_start`), a session-tracked memory reader (`safe_read_file`), and mutex-protected memory file writers (`safe_write_file`, `safe_append_file`). The `run_command` tool executes shell commands on the local machine and returns stdout/stderr directly. All memory file operations (read and write) go through the bridge, which tracks per-session file versions to detect concurrent read-modify-write races. Non-memory filesystem operations (list, search, and non-memory reads/writes) are handled by the Filesystem extension.

5. **Single-writer model with mutex protection and branching.** Only the primary Claude Desktop agent writes to Layer 2 memory. Sub-agents have read-only access to Layer 2 memory. The bridge's in-process write mutex serializes all memory file I/O. When a concurrent read-modify-write race is detected (via per-session file version tracking), the bridge creates a "branch" of the memory file instead of overwriting the other conversation's changes. Branches are merged later during off-hours via a semantic merge process (see [Chapter 3, Section 3.12](stateful-agent-design-chapter3.md#312-branching) for details).

6. **Compliance-based memory management.** Claude's memory updates are guided by skill instructions (compliance), not enforced by tool constraints. This is pragmatic — the alternative (a dedicated memory server with structured CRUD) is more complex and can be added later if compliance proves insufficient.

### 1.4 Terminology

| Term | Definition |
|------|-----------|
| **Primary agent** | The Claude instance running in Claude Desktop App. Has Layer 1 memory, MCP tools, and the memory skill. |
| **Sub-agent** | An ephemeral Claude Code CLI instance (`claude -p`) spawned by the bridge. One-shot, stateless, no Layer 1 memory. |
| **Layer 1** | Anthropic's built-in memory. Auto-generated summary (~500–2,000 tokens) injected into every conversation. Influenced indirectly via `memory_user_edits` steering instructions. ~24-hour lag for updates. |
| **Layer 2** | Our supplementary memory system. Markdown files at `C:\franl\.claude-agent-memory\`. Under our full control. Updates are immediate. |
| **MCP bridge** | The Go binary that serves as an MCP server, providing `memory_session_start`, `safe_read_file`, `safe_write_file`, `safe_append_file`, `spawn_agent`, `check_agent`, and `run_command` tools. |
| **Filesystem extension** | Anthropic's official `@modelcontextprotocol/server-filesystem` MCP server. Provides `read_file`, `write_file`, `edit_file`, etc. Used for non-memory file operations. Memory file reads go through the bridge's `safe_read_file` tool instead. |
| **Write mutex** | A Go `sync.Mutex` in the bridge process that serializes all memory file I/O (`safe_read_file`, `safe_write_file`, and `safe_append_file`). Prevents concurrent conversations from interleaving or corrupting memory updates. |
| **Memory skill** | The .zip file uploaded to Claude Desktop containing SKILL.md — instructions for managing Layer 2 memory. |
| **Session ID** | A short, bridge-generated identifier (e.g., `ses-7ka2`) that uniquely identifies a conversation's memory session. Passed as a parameter to all memory tools so the bridge can track which files each conversation has read and detect stale-read races. |
| **Session tracker** | An in-memory map in the bridge (`session_id → file_path → last_seen_modtime`) that records when each session last read each memory file. Used by `safe_write_file` and `safe_append_file` to detect concurrent read-modify-write races. |
| **Branch (memory)** | A copy of a memory file created when a concurrent read-modify-write race is detected. Named with a timestamp and random suffix (e.g., `core.branch-20260313T1423-a1b2.md`). The original file is left unmodified; the racing conversation's changes go to the branch file. |
| **Merge (memory)** | A semantic merge process that reconciles a branched memory file with its base file. Performed by a sub-agent during off-hours. The merger reads both versions, understands the meaning of each set of changes, and produces a unified result. |
| **Sync window** | The 25-second window during which `spawn_agent` and `run_command` wait for their subprocess to complete before switching to async mode. Sized to stay safely under Claude Desktop's ~30-second reliability threshold. Shared implementation via the async executor (see [Section 3.10](#310-async-executor)). |
| **Block** | An individual markdown file in the `blocks/` directory. Each block covers a project, topic, or time period. |
| **Block reference** | A row in `index.md` mapping a block filename to its summary and last-updated date. |

---

## 2. System Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    Claude Desktop App                            │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Claude LLM (Anthropic servers)                             │ │
│  │                                                             │ │
│  │  Layer 1 memory (auto-injected, ~500–2,000 tokens)          │ │
│  │  Memory skill instructions (from SKILL.md)                  │ │
│  │  Cloud VM tools (bash_tool, create_file — DO NOT USE        │ │
│  │    for persistent data; ephemeral, resets between sessions) │ │
│  └──────────────┬─────────────────────┬────────────────────────┘ │
│                 │ MCP (stdio)         │ MCP (stdio)              │
│                 ▼                     ▼                          │
│  ┌──────────────────────┐  ┌──────────────────────────────┐      │
│  │  MCP Bridge Server   │  │  Anthropic Filesystem Ext.   │      │
│  │  (our Go binary)     │  │  (@modelcontextprotocol/     │      │
│  │                      │  │   server-filesystem)         │      │
│  │  Tools:              │  │                              │      │
│  │  • memory_session_   │  │  Tools:                      │      │
│  │      start           │  │  • read_file                 │      │
│  │  • safe_read_file    │  │  • write_file                │      │
│  │  • safe_write_file   │  │  • edit_file                 │      │
│  │  • safe_append_file  │  │  • create_directory          │      │
│  │  • spawn_agent       │  │  • list_directory            │      │
│  │  • check_agent       │  │  • search_files              │      │
│  │  • run_command       │  │  • ... (11 tools total)      │      │
│  │       │              │  │                              │      │
│  │       │ subprocess   │  │  Allowed dirs:               │      │
│  │       ▼              │  │  • C:\franl                  │      │
│  │  ┌────────────┐      │  │  • C:\temp                   │      │
│  │  │ claude -p  │      │  │  • C:\apps                   │      │
│  │  │ (sub-agent)│      │  │                              │      │
│  │  └────────────┘      │  │                              │      │
│  └──────────────────────┘  └──────────────────────────────┘      │
│                                                                  │
│  Local filesystem: C:\franl\.claude-agent-memory\                │
│  ├── core.md                                                     │
│  ├── index.md                                                    │
│  └── blocks\                                                     │
│      ├── project-*.md                                            │
│      ├── reference-*.md                                          │
│      ├── episodic-YYYY-MM.md                                     │
│      └── decisions.md                                            │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

**Session initialization:**
```
Claude LLM
  → calls Bridge:memory_session_start()
  → Bridge generates a unique session ID (e.g., "ses-7ka2")
  → Bridge registers the session in its internal tracker
  → Returns session_id to Claude (used in all subsequent memory tool calls)
```

**Memory read (session start and during session):**
```
Claude LLM
  → calls Bridge:safe_read_file(path, session_id)
  → Bridge acquires write mutex, reads file, records ModTime for this session
  → If branched versions exist, their content is included (annotated)
  → Returns file content (+ branch content if any)
  Claude should NEVER use Filesystem:read_file for memory files — that
  bypasses session tracking and prevents race detection.
```

**Memory write (during session):**
```
Claude LLM
  → calls Bridge:safe_write_file(path, content, session_id)
  → Bridge acquires write mutex
  → Bridge compares file's current ModTime against this session's last-seen ModTime
  → If ModTime matches (no race): atomic write replaces the file
  → If ModTime differs (race detected): writes to a branch file instead
  → Returns success (with branch_created flag if applicable)
  Claude should NEVER use Filesystem:write_file or Filesystem:edit_file
  for memory files — those bypass the mutex and session tracking.
```

**Sub-agent invocation:**
```
Claude LLM
  → calls Bridge:spawn_agent(task, ...)
  → Bridge launches `claude -p` subprocess locally
  → Sub-agent uses local bash, filesystem, network (no cloud VM)
  → Bridge returns result (sync) or job_id (async)
  → (if async) Claude LLM polls with Bridge:check_agent(job_id)
```

**Local command execution:**
```
Claude LLM
  → calls Bridge:run_command("grep -r 'TODO' src/", ...)
  → Bridge launches shell subprocess locally (Cygwin bash)
  → No LLM involved — direct command execution, stdout/stderr captured
  → Bridge returns result (sync) or job_id (async)
  → (if async) Claude LLM polls with Bridge:check_agent(job_id)
  Note: run_command uses the same hybrid sync/async model as spawn_agent,
  sharing the async executor and job lifecycle manager. Use run_command
  for simple commands; use spawn_agent when the task requires LLM reasoning.
```

### 2.3 What the Bridge Does NOT Do

The bridge is deliberately minimal. It does **not** provide:

- Non-memory filesystem tools (list, search) — handled by the Filesystem extension. The bridge provides `safe_read_file`, `safe_write_file`, and `safe_append_file` specifically for memory files; all non-memory file operations use the Filesystem extension.
- Network request tools (http_get, http_post) — deferred. Sub-agents or `run_command` (e.g., `run_command("curl ...")`) can perform network operations. Dedicated network tools can be added to the bridge later if needed.
- Memory-aware tools (update_memory_block, memory_search) — deferred to future enhancement. See [Chapter 9, Future Enhancements](stateful-agent-design-chapter9.md).

This keeps the initial bridge focused: seven tool handlers, a write mutex, a session tracker, branching logic, the async executor, and the job lifecycle manager.

---

## 3. MCP Bridge Server

The MCP bridge server is a Go binary that runs locally, providing Bash access, sub-agent spawning,
and memory access to be used by the Claude Desktop App via the MCP protocol.

### 3.1 Go Module Structure

```
mcp-bridge/
├── go.mod                    # Module: github.com/fpl9000/mcp-bridge
├── go.sum
├── main.go                   # Entry point: loads config, registers tools, starts stdio server
├── config.go                 # Configuration loading and validation
├── tools.go                  # Tool handler registration
├── async.go                  # Shared async executor: sync window, async handoff, output truncation
│                             #   Used by both spawn_agent and run_command
├── spawn.go                  # spawn_agent tool handler: builds claude -p command, delegates to async executor
├── check.go                  # check_agent tool handler
├── run_command.go            # run_command tool handler: builds shell command, delegates to async executor
├── session.go                # memory_session_start tool handler + session tracker
├── safe_read.go              # safe_read_file tool handler (session-tracked read with branch awareness)
├── safe_write.go             # safe_write_file tool handler (mutex-protected atomic write with branching)
├── safe_append.go            # safe_append_file tool handler (mutex-protected append with branching)
├── branching.go              # Branch detection, naming, and merge-readiness checks
├── writemutex.go             # Write mutex shared by safe_read_file, safe_write_file, and safe_append_file
├── jobs.go                   # Job lifecycle manager (background goroutine)
├── logging.go                # Structured logging to file
└── bridge-config.yaml        # Default configuration (embedded or external)
```

**Dependencies:**
- `github.com/mark3labs/mcp-go` — MCP SDK for Go (see [Chapter 12, Appendix: mark3labs/mcp-go SDK Reference](stateful-agent-design-chapter12.md#12-appendix-mark3labsmcp-go-sdk-reference) for details).
- Go standard library — everything else (os/exec, sync, time, encoding/json, log, filepath).

No CGO. No external C libraries. Pure Go for single-binary compilation.

### 3.2 Configuration

The bridge reads its configuration from a YAML file. The config file location is determined by (in priority order):

1. `--config` command-line flag
2. `MCP_BRIDGE_CONFIG` environment variable
3. Default: `C:\franl\.claude-agent-memory\bridge-config.yaml`

**Configuration schema:**

```yaml
# bridge-config.yaml

# Async executor settings (shared by spawn_agent and run_command)
async:
  sync_window_seconds: 25         # How long to wait before going async
                                  # Must be < 30 (Claude Desktop reliability threshold)
  job_expiry_seconds: 600         # Uncollected jobs cleaned up after this

# Default working directory for spawn_agent and run_command.
# On this system, C:\franl\ is the Cygwin home directory and the root of all
# project work. This is preferred over os.UserHomeDir() (which returns the
# Windows home directory C:\Users\flitt\) because commands run via Cygwin bash
# and sub-agents expect a Cygwin-rooted working environment.
default_working_directory: "C:\\franl"

# Sub-agent defaults (for spawn_agent tool)
sub_agent:
  default_timeout_seconds: 300    # Max subprocess runtime (kills after this)
  default_max_output_tokens: 4000 # Truncation threshold (chars/4 heuristic)
  max_concurrent_agents: 5        # Cap on simultaneous running sub-agents

# Local command execution (for run_command tool)
run_command:
  shell: "C:\\apps\\cygwin\\bin\\bash.exe"   # Shell to execute commands
  shell_args: ["-c"]                         # Arguments before the command string
  default_timeout_seconds: 120    # Max command runtime (kills after this)
  default_max_output_bytes: 51200 # Truncate output beyond 50 KB (~12,500 tokens)

# Memory directory (used by memory tools for path validation)
memory:
  directory: "C:\\franl\\.claude-agent-memory"

# Session tracking
session:
  id_length: 8                    # Length of generated session IDs (e.g., "ses-7ka2")
  max_sessions: 20                # Cap on tracked sessions (oldest evicted when exceeded)

# Branching (concurrent read-modify-write race resolution)
branching:
  enabled: true                   # Set to false to revert to last-writer-wins behavior

# Logging
logging:
  file: "C:\\franl\\.claude-agent-memory\\bridge.log"
  level: "info"                   # debug, info, warn, error
  max_size_mb: 10                 # Rotate after this size
  max_backups: 3                  # Keep this many rotated logs

# Claude Code CLI path (if not in PATH)
claude_cli:
  path: "claude"                  # Or full path: "C:\\path\\to\\claude.exe"
```

**Pseudo-code for configuration loading:**

```
func LoadConfig(path string) Config:
    // Read YAML file
    // Apply defaults for any missing fields
    // Validate:
    //   - async.sync_window_seconds < 30
    //   - memory.directory exists (or create it)
    //   - logging.file parent directory exists
    //   - claude_cli.path is executable
    //   - run_command.shell is executable
    // Return validated config
```

### 3.3 Tool Summary

| Tool | MCP Name | Purpose |
|------|----------|---------|
| `memory_session_start` | `memory_session_start` | Register a new memory session and receive a unique session ID. Call once per conversation before any memory reads or writes. |
| `safe_read_file` | `safe_read_file` | Session-tracked read of a memory file. Records the file's ModTime for race detection. Returns branch content (annotated) if branches exist. |
| `safe_write_file` | `safe_write_file` | Mutex-protected atomic write (full file replacement) for memory files. Detects concurrent read-modify-write races via session tracking; creates a branch file instead of overwriting if a race is detected. |
| `safe_append_file` | `safe_append_file` | Mutex-protected append for memory files. Detects races and branches like `safe_write_file`. Primary use: episodic log entries. |
| `spawn_agent` | `spawn_agent` | Launch a sub-agent (`claude -p`) with a task. Returns result (sync) or job_id (async). |
| `check_agent` | `check_agent` | Poll a running async job by job_id. Returns status and result. Used for both `spawn_agent` and `run_command` async jobs. |
| `run_command` | `run_command` | Execute a shell command on the local machine. No LLM involved — direct subprocess execution. Uses the same hybrid sync/async model as `spawn_agent`. Far cheaper than spawning a sub-agent for simple commands. |

### 3.4 Tool: spawn_agent

This is the most complex tool in the bridge. It launches a Claude Code CLI sub-agent with a task. The subprocess lifecycle (sync window, async handoff, output truncation) is managed by the shared async executor (see [Section 3.13](#313-async-executor)).

**MCP tool definition (registered with mcp-go):**

```
Name:        "spawn_agent"
Description: "Spawn a sub-agent (Claude Code CLI) to perform a focused task.
             Returns immediately with either a completed result or a job_id
             for polling via check_agent."

Input Schema:
  task:               string, required  — The task prompt
  system_prompt:      string, optional  — Task-specific instructions (appended to default preamble)
  model:              string, optional  — Sub-agent model (e.g., "sonnet", "opus")
  working_directory:  string, optional  — CWD and sandbox root (default: config.DefaultWorkingDirectory)
  additional_dirs:    string[], optional — Extra dirs for --add-dir
  timeout_seconds:    integer, optional — Max subprocess runtime (default: from config)
  max_output_tokens:  integer, optional — Output truncation threshold (default: from config)
  allow_memory_read:  boolean, optional — Grant read access to memory dir (default: false)

Output Schema:
  status:     "complete" | "running"
  job_id:     string | null
  result:     string | null
  started_at: string (ISO 8601)
```

**Handler pseudo-code:**

```
func HandleSpawnAgent(params SpawnAgentParams) AsyncResult:

    // 1. Check concurrent agent cap
    if jobManager.ActiveCount() >= config.SubAgent.MaxConcurrentAgents:
        return error("Maximum concurrent sub-agents reached ({config.SubAgent.MaxConcurrentAgents}). 
                      Wait for a running agent to complete, or check/cancel an existing job.")

    // 2. Build the system prompt
    //    The default preamble is ALWAYS included. The caller's system_prompt, if any,
    //    is appended after it. The combined text replaces Claude Code's default
    //    behavioral prompt via --system-prompt.
    fullPrompt = DEFAULT_PREAMBLE
    if params.SystemPrompt != "":
        fullPrompt += "\n\n" + params.SystemPrompt

    // 3. Construct the claude -p command line
    args = ["--print", "--system-prompt", fullPrompt]

    if params.Model != "":
        args += ["--model", params.Model]

    if params.WorkingDirectory != "":
        // This also sets Claude Code's directory sandbox
        // (sub-agent CANNOT access files outside this directory)
    
    if params.AllowMemoryRead:
        args += ["--add-dir", config.Memory.Directory]

    for dir in params.AdditionalDirs:
        args += ["--add-dir", dir]

    // 4. Build the exec.Cmd
    cmd = exec.Command(config.ClaudeCLI.Path, args...)
    cmd.Dir = params.WorkingDirectory or config.DefaultWorkingDirectory
    cmd.Stdin = strings.NewReader(params.Task)  // Task goes to stdin

    // 5. Determine timeout
    timeout = params.TimeoutSeconds or config.SubAgent.DefaultTimeoutSeconds

    // 6. Determine truncation threshold (in tokens)
    maxOutput = params.MaxOutputTokens or config.SubAgent.DefaultMaxOutputTokens

    // 7. Delegate to the shared async executor
    //    This handles: subprocess start, sync window, async handoff, output capture,
    //    timeout enforcement, and output truncation.
    return asyncExecutor.Run(cmd, timeout, maxOutput, "spawn_agent")
```

### 3.5 Tool: check_agent

This tool polls the status of any async job, whether spawned by `spawn_agent` or `run_command`. Both tools use the same job lifecycle manager, so `check_agent` is the unified polling interface.

**MCP tool definition:**

```
Name:        "check_agent"
Description: "Check the status of a running async job by job ID.
             Works for jobs created by both spawn_agent and run_command.
             Returns the current status and result if complete."

Input Schema:
  job_id:  string, required  — Job ID from spawn_agent or run_command

Output Schema:
  status:          "running" | "complete" | "failed" | "timed_out"
  result:          string | null
  error:           string | null
  started_at:      string (ISO 8601)
  elapsed_seconds: number
  source:          "spawn_agent" | "run_command"  — Which tool created this job
```

**Handler pseudo-code:**

```
func HandleCheckAgent(params CheckAgentParams) CheckAgentResult:

    job = jobManager.Get(params.JobID)
    if job == nil:
        return error("Unknown job_id: " + params.JobID + 
                      ". Job may have expired or already been collected.")

    elapsed = time.Since(job.StartedAt).Seconds()

    // Check if process has completed
    select:
        case err = <-job.Done:
            // Process finished — collect result
            output = job.OutputBuffer.String()
            output = truncateIfNeeded(output, job.MaxOutput)

            // Mark job as collected (will be cleaned up by lifecycle manager)
            jobManager.MarkCollected(params.JobID)

            if err != nil:
                return {
                    status: "failed",
                    result: output,
                    error: err.String(),
                    started_at: job.StartedAt.Format(ISO8601),
                    elapsed_seconds: elapsed,
                    source: job.Source
                }

            return {
                status: "complete",
                result: output,
                error: null,
                started_at: job.StartedAt.Format(ISO8601),
                elapsed_seconds: elapsed,
                source: job.Source
            }

        default:
            // Still running — check if we've exceeded the timeout
            if time.Now().After(job.Deadline):
                job.Process.Kill()
                output = job.OutputBuffer.String()
                output = truncateIfNeeded(output, job.MaxOutput)
                jobManager.MarkCollected(params.JobID)

                return {
                    status: "timed_out",
                    result: output,
                    error: "Process exceeded timeout of " + job.TimeoutSeconds + "s",
                    started_at: job.StartedAt.Format(ISO8601),
                    elapsed_seconds: elapsed,
                    source: job.Source
                }

            // Still running and within timeout
            return {
                status: "running",
                result: null,
                error: null,
                started_at: job.StartedAt.Format(ISO8601),
                elapsed_seconds: elapsed,
                source: job.Source
            }
```

### 3.6 Tool: run_command

This tool executes a shell command on the local machine and returns its output. No LLM is involved — this is direct subprocess execution, making it dramatically cheaper than `spawn_agent` for simple operations like `curl`, `git status`, `grep`, `find`, `cat`, `ls`, directory listings, and short scripts. It uses the same hybrid sync/async model as `spawn_agent` via the shared async executor (see [Section 3.13](#313-async-executor)), so long-running commands (e.g., a recursive `grep` of a large codebase) are handled correctly without hitting the MCP timeout.

**When to use `run_command` vs. `spawn_agent`:**
- Use `run_command` when the task can be expressed as a single shell command or short pipeline and requires no LLM reasoning. Examples: `git status`, `curl https://api.example.com/data`, `grep -r 'TODO' src/`, `wc -l *.go`, `find . -name '*.md' -mtime -7`.
- Use `spawn_agent` when the task requires LLM reasoning, multi-step problem solving, or iterative refinement. Examples: "Refactor the error handling in server.go", "Write unit tests for the auth module", "Read this log file and summarize the errors".

**Security model:** No restrictions beyond the OS-level permissions of the bridge process. The primary agent already has equivalent local access via `spawn_agent` (which can run arbitrary commands through Claude Code CLI), so `run_command` does not expand the attack surface — it just makes the common case cheaper. All commands are logged (command text, working directory, exit code, truncated output) for auditability.

**Shell configuration:** Commands are executed via a configurable shell, defaulting to Cygwin bash (`C:\apps\cygwin\bin\bash.exe -c "<command>"`). This ensures consistent UNIX-like behavior for commands like `grep`, `find`, `curl`, etc. The shell and its arguments are configurable in `bridge-config.yaml` (see [Section 3.2](#32-configuration)).

**MCP tool definition:**

```
Name:        "run_command"
Description: "Execute a shell command on the local machine and return its output.
             No LLM involved — direct subprocess execution. Uses the same hybrid
             sync/async model as spawn_agent: commands completing within the sync
             window return results immediately; longer commands return a job_id
             for polling via check_agent. Use this for simple operations (curl,
             grep, git, ls, etc.); use spawn_agent when LLM reasoning is needed."

Input Schema:
  command:            string, required   — Shell command to execute
  working_directory:  string, optional   — CWD for the command (default: config.DefaultWorkingDirectory)
  timeout_seconds:    integer, optional  — Max runtime in seconds (default: from config, typically 120)
  max_output_bytes:   integer, optional  — Truncate combined stdout+stderr beyond this
                                           (default: from config, typically 50 KB)

Output Schema:
  status:          "complete" | "running"    — "complete" if finished within sync window
  job_id:          string | null             — Non-null only if async (status == "running")
  exit_code:       integer | null            — Process exit code (null if still running)
  stdout:          string | null             — Captured stdout (null if still running)
  stderr:          string | null             — Captured stderr (null if still running)
  timed_out:       boolean                   — True if killed due to timeout
  truncated:       boolean                   — True if output was truncated to max_output_bytes
  elapsed_ms:      integer                   — Wall-clock milliseconds
  started_at:      string (ISO 8601)
```

**Handler pseudo-code:**

```
func HandleRunCommand(params RunCommandParams) AsyncResult:

    // 1. Validate inputs
    if params.Command == "":
        return error("command is required and must be non-empty")

    // 2. Resolve configuration defaults
    timeout = params.TimeoutSeconds or config.RunCommand.DefaultTimeoutSeconds
    maxOutputBytes = params.MaxOutputBytes or config.RunCommand.DefaultMaxOutputBytes
    workDir = params.WorkingDirectory or config.DefaultWorkingDirectory

    // 3. Construct the shell command
    //    Wraps the command in the configured shell (Cygwin bash by default).
    //    This ensures consistent UNIX-like behavior on Windows.
    //    Example: ["C:\apps\cygwin\bin\bash.exe", "-c", "grep -r 'TODO' src/"]
    shellPath = config.RunCommand.Shell          // e.g., "C:\apps\cygwin\bin\bash.exe"
    shellArgs = config.RunCommand.ShellArgs      // e.g., ["-c"]
    fullArgs = append(shellArgs, params.Command)

    cmd = exec.Command(shellPath, fullArgs...)
    cmd.Dir = workDir

    // 4. Log the command for auditability
    log.Info("run_command: command=%q, cwd=%s, timeout=%ds", params.Command, workDir, timeout)

    // 5. Delegate to the shared async executor
    //    Same hybrid sync/async model as spawn_agent:
    //    - Waits up to sync_window_seconds for the command to finish
    //    - If the command completes within the sync window, returns result immediately
    //    - If not, registers an async job and returns job_id for check_agent polling
    result = asyncExecutor.Run(cmd, timeout, maxOutputBytes, "run_command")

    // 6. If sync completion, enrich with run_command-specific fields
    if result.Status == "complete":
        return {
            status: "complete",
            job_id: null,
            exit_code: cmd.ProcessState.ExitCode(),
            stdout: result.Stdout,
            stderr: result.Stderr,
            timed_out: false,
            truncated: result.Truncated,
            elapsed_ms: result.ElapsedMs,
            started_at: result.StartedAt
        }

    // 7. Async handoff — return job_id for polling via check_agent
    return {
        status: "running",
        job_id: result.JobID,
        exit_code: null,
        stdout: null,
        stderr: null,
        timed_out: false,
        truncated: false,
        elapsed_ms: result.ElapsedMs,
        started_at: result.StartedAt
    }
```

**Output truncation:** When combined stdout+stderr exceeds `max_output_bytes` (default 50 KB, ~12,500 tokens), the output is truncated from the middle, preserving the first and last portions with a marker:

```
[...output truncated: {total_bytes} bytes exceeded limit of {max_output_bytes} bytes.
    Showing first {keep_bytes} and last {keep_bytes} bytes...]
```

Middle truncation is preferred over tail truncation because command output often has useful context at both the beginning (headers, initial progress) and the end (summary, final errors).

### 3.7 Tool: memory_session_start

This tool initializes a memory session and returns a unique session ID. The skill instructs Claude to call it once at the start of every conversation, before any memory reads or writes. The session ID is passed as a parameter to all subsequent memory tool calls (`safe_read_file`, `safe_write_file`, `safe_append_file`), enabling the bridge to track which files each conversation has read and detect stale-read races.

**Why the bridge generates the ID (not Claude):** If Claude composed its own session identifier (e.g., a descriptive phrase), it would need to reproduce it verbatim on every subsequent tool call — and LLMs are unreliable at exact string consistency across many calls. A bridge-generated short opaque ID (e.g., `ses-7ka2`) is trivially reproducible: Claude just parrots back a fixed string. Uniqueness is guaranteed by the bridge, which controls generation and checks for collisions.

**MCP tool definition:**

```
Name:        "memory_session_start"
Description: "Register a new memory session and receive a unique session ID.
             Call this once at the start of every conversation, before any
             memory reads or writes. Pass the returned session_id to all
             subsequent safe_read_file, safe_write_file, and safe_append_file
             calls. If your context is compacted and you lose the session ID,
             call this again to get a new one."

Input Schema:
  (no required parameters)

Output Schema:
  session_id:       string   — Short unique identifier (e.g., "ses-7ka2")
  started_at:       string   — ISO 8601 timestamp
  branches_exist:   boolean  — True if any branched memory files currently exist
                               (signals that a merge may be needed)
```

**Handler pseudo-code:**

```
func HandleMemorySessionStart(params MemorySessionStartParams) MemorySessionStartResult:

    // 1. Generate a unique session ID.
    //    Format: "ses-" + 4 hex chars from crypto/rand (e.g., "ses-7ka2").
    //    Check for collisions against the session tracker (vanishingly unlikely
    //    with 65,536 possible values and typically <5 active sessions, but
    //    defense in depth costs nothing).
    sessionID = generateSessionID(config.Session.IDLength)
    while sessionTracker.Exists(sessionID):
        sessionID = generateSessionID(config.Session.IDLength)

    // 2. Register the session in the tracker.
    //    If the tracker is at capacity (config.Session.MaxSessions), evict the
    //    oldest session. This prevents unbounded memory growth from leaked sessions
    //    (conversations that called memory_session_start but never ended cleanly).
    sessionTracker.Register(sessionID)

    // 3. Check for existing branch files in the memory directory.
    //    This gives Claude a heads-up that a merge may be needed, which it can
    //    mention to the user or schedule via a sub-agent.
    branchesExist = branching.AnyBranchesExist(config.Memory.Directory)

    return {
        session_id: sessionID,
        started_at: time.Now().Format(ISO8601),
        branches_exist: branchesExist
    }
```

### 3.8 Tool: safe_read_file

This tool reads a memory file and records its modification time in the session tracker. This is how the bridge knows what version of a file each conversation has seen, enabling race detection on subsequent writes. If branched versions of the file exist, their content is included in the response, annotated to distinguish them from the base file.

**Why not use the Filesystem extension's `read_file`?** Because the bridge needs to track reads in order to detect stale-read races. If Claude reads `core.md` via `Filesystem:read_file`, the bridge never sees the read and cannot determine whether a subsequent `safe_write_file` call is operating on stale data. By routing all memory reads through the bridge, the bridge has complete lifecycle visibility: it knows what each conversation has read and when, and can compare against the file's current state at write time.

**MCP tool definition:**

```
Name:        "safe_read_file"
Description: "Read a memory file with session tracking for race detection.
             Records the file's modification time so that subsequent writes
             can detect if the file was modified by another conversation.
             If branched versions of the file exist, their content is included
             in the response, annotated to distinguish base from branch content.
             Restricted to the memory directory."

Input Schema:
  path:        string, required  — Absolute path to the file (must be within memory directory)
  session_id:  string, required  — Session ID from memory_session_start

Output Schema:
  content:          string        — The base file's content
  branches:         []Branch      — Array of branch info (empty if no branches exist)
    branch.filename:  string      — Branch filename (e.g., "core.branch-20260313T1423-a1b2.md")
    branch.created:   string      — Branch creation time (extracted from filename, ISO 8601)
    branch.content:   string      — Full content of the branch file
  has_branches:     boolean       — Convenience flag: true if branches array is non-empty
  path:             string        — The absolute path that was read
  mod_time:         string        — File modification time (ISO 8601) — for informational purposes
```

**Handler pseudo-code:**

```
func HandleSafeReadFile(params SafeReadFileParams) SafeReadFileResult:

    // 1. Validate that the path is within the memory directory.
    absPath = filepath.Abs(params.Path)
    if !strings.HasPrefix(absPath, config.Memory.Directory):
        return error("safe_read_file is restricted to the memory directory: " +
                      config.Memory.Directory)

    // 2. Validate the session ID.
    if !sessionTracker.Exists(params.SessionID):
        return error("Unknown session_id: " + params.SessionID +
                      ". Call memory_session_start first.")

    // 3. Acquire the write mutex. This serializes reads alongside writes,
    //    ensuring that the ModTime we record is consistent with the file
    //    content we return. Without this, a concurrent write could modify
    //    the file between our Stat() and Read() calls, causing us to record
    //    a stale ModTime for fresh content (or vice versa).
    writeMutex.Lock()
    defer writeMutex.Unlock()

    // 4. Stat the file to get its current ModTime.
    stat, err = os.Stat(absPath)
    if err:
        if os.IsNotExist(err):
            return error("File does not exist: " + absPath)
        return error("Failed to stat file: " + err)

    // 5. Read the base file content.
    content, err = os.ReadFile(absPath)
    if err:
        return error("Failed to read file: " + err)

    // 6. Record this file's ModTime in the session tracker.
    //    This is the baseline that safe_write_file will compare against
    //    to detect races.
    sessionTracker.RecordRead(params.SessionID, absPath, stat.ModTime())

    // 7. Check for branch files.
    //    Branch files match the pattern: <stem>.branch-<timestamp>-<random>.<ext>
    //    For example, if absPath is "core.md", branches match "core.branch-*.md"
    branches = branching.FindBranches(absPath)

    branchResults = []
    for _, branchPath in branches:
        branchContent, err = os.ReadFile(branchPath)
        if err:
            log.Warn("Failed to read branch file %s: %v", branchPath, err)
            continue
        branchResults = append(branchResults, Branch{
            Filename: filepath.Base(branchPath),
            Created:  branching.ExtractTimestamp(branchPath),
            Content:  string(branchContent),
        })

    return {
        content: string(content),
        branches: branchResults,
        has_branches: len(branchResults) > 0,
        path: absPath,
        mod_time: stat.ModTime().Format(ISO8601),
    }
```

**Branch annotation:** When branches exist, the tool returns the base file content in the `content` field and each branch as a separate entry in the `branches` array. The skill instructions tell Claude how to interpret this: the base file represents the "main line" of memory, and each branch represents changes from a concurrent conversation that haven't been merged yet. Claude should consider all versions when answering questions, and can flag to the user that a merge is pending.

### 3.9 Tool: safe_write_file

This tool performs a mutex-protected, atomic full-file write. It is the primary tool for updating memory files (`core.md`, `index.md`, content blocks). It replaces the use of `Filesystem:write_file` and `Filesystem:edit_file` for all memory operations.

**Why not use the Filesystem extension's `write_file`?** Four reasons: (a) the Filesystem extension has no mutex — two concurrent conversations writing to the same memory file can interleave, with the second write silently clobbering the first; (b) `safe_write_file` is scoped to the memory directory, providing the "unambiguous tool names" benefit from proposal Open Question #22 — Claude can't accidentally use it to write to the cloud VM or to non-memory locations; (c) atomic write via temp-file-then-rename prevents partial writes from corrupting files if the process is interrupted; (d) the bridge tracks per-session file versions via the session tracker, and `safe_write_file` uses this to detect concurrent read-modify-write races — if a race is detected, the write is redirected to a branch file instead of overwriting the other conversation's changes.

**Why full-file replacement instead of surgical edits?** Full replacement is simpler and more reliable than `Filesystem:edit_file`'s find-and-replace pattern, which can fail if the search string doesn't match exactly (due to whitespace differences, prior modifications by another conversation, etc.). Claude already has the file content in context (it loaded the file to decide what to change), so providing the complete updated content is straightforward. For typical memory files (500–2,000 tokens), the output token cost of a full write is modest.

**MCP tool definition:**

```
Name:        "safe_write_file"
Description: "Atomically write content to a memory file. Acquires a write mutex
             shared with safe_read_file and safe_append_file. Uses temp-file-then-
             rename for atomicity. Restricted to the memory directory. Provide the
             COMPLETE file content — this is a full replacement, not an edit.
             If the file was modified by another conversation since this session
             last read it, the write is redirected to a branch file to preserve
             both versions."

Input Schema:
  path:        string, required  — Absolute path to the file (must be within memory directory)
  content:     string, required  — Complete file content to write
  session_id:  string, required  — Session ID from memory_session_start

Output Schema:
  success:         boolean
  bytes_written:   integer
  path:            string    — The path that was actually written (may be a branch file)
  branch_created:  boolean   — True if a race was detected and a branch file was created
  branch_path:     string    — Path of the branch file (null if no branch created)
```

**Handler pseudo-code:**

```
func HandleSafeWriteFile(params SafeWriteFileParams) SafeWriteFileResult:

    // 1. Validate that the path is within the memory directory.
    //    Resolve symlinks and ".." before checking to prevent path traversal.
    absPath = filepath.Abs(params.Path)
    if !strings.HasPrefix(absPath, config.Memory.Directory):
        return error("safe_write_file is restricted to the memory directory: " +
                      config.Memory.Directory)

    // 2. Validate the session ID.
    if !sessionTracker.Exists(params.SessionID):
        return error("Unknown session_id: " + params.SessionID +
                      ". Call memory_session_start first.")

    // 3. Ensure parent directory exists (handles new block creation).
    os.MkdirAll(filepath.Dir(absPath), 0755)

    // 4. Acquire the write mutex. This serializes all memory I/O
    //    (safe_read_file, safe_write_file, and safe_append_file) across
    //    all concurrent conversations in this Desktop App instance.
    writeMutex.Lock()
    defer writeMutex.Unlock()

    // 5. Race detection: compare the file's current ModTime against this
    //    session's last-seen ModTime for this file.
    targetPath = absPath
    branchCreated = false
    branchPath = ""

    if config.Branching.Enabled && fileExists(absPath):
        currentModTime = os.Stat(absPath).ModTime()
        lastSeenModTime = sessionTracker.GetLastRead(params.SessionID, absPath)

        if lastSeenModTime != nil && currentModTime.After(*lastSeenModTime):
            // Race detected: the file was modified by another conversation
            // since this session last read it. Write to a branch file instead
            // of overwriting the other conversation's changes.
            targetPath = branching.GenerateBranchPath(absPath)
            branchCreated = true
            branchPath = targetPath
            log.Info("Race detected for %s (session %s): branching to %s",
                      absPath, params.SessionID, targetPath)

    // 6. Write to a temp file in the same directory (same filesystem,
    //    so rename is atomic). Use the target directory, not os.TempDir(),
    //    to guarantee same-filesystem rename.
    tmpFile = os.CreateTemp(filepath.Dir(targetPath), ".safe-write-*.tmp")
    _, err = tmpFile.Write([]byte(params.Content))
    tmpFile.Close()
    if err:
        os.Remove(tmpFile.Name())  // Clean up on write failure
        return error("Failed to write temp file: " + err)

    // 7. Atomic rename: replaces the target file in one operation.
    //    On Windows, os.Rename cannot overwrite an existing file.
    //    The safest cross-platform approach is: remove target if it
    //    exists, then rename.
    if fileExists(targetPath):
        os.Remove(targetPath)
    err = os.Rename(tmpFile.Name(), targetPath)
    if err:
        return error("Failed to rename temp file to target: " + err)

    // 8. Update the session tracker with the new ModTime.
    //    This ensures that if this same session writes again, it won't
    //    falsely detect a race against its own previous write.
    newModTime = os.Stat(targetPath).ModTime()
    sessionTracker.RecordRead(params.SessionID, absPath, newModTime)

    return {
        success: true,
        bytes_written: len(params.Content),
        path: targetPath,
        branch_created: branchCreated,
        branch_path: branchPath
    }
```

**Windows rename caveat:** On Windows, `os.Rename` cannot atomically overwrite an existing file on all filesystems. The pseudo-code above uses a remove-then-rename sequence, which introduces a tiny window where the file doesn't exist. For our use case (low-frequency memory writes, mutex-serialized), this is acceptable. If true atomicity is needed later, the Windows `ReplaceFile` API can be called via `syscall`.

### 3.10 Tool: safe_append_file

This tool performs a mutex-protected append to a memory file. Its primary use case is adding entries to episodic log files (`episodic-YYYY-MM.md`), where each conversation appends a timestamped entry and a full rewrite is unnecessary.

**MCP tool definition:**

```
Name:        "safe_append_file"
Description: "Append text to a memory file. Acquires the same write mutex as
             safe_read_file and safe_write_file to prevent concurrent write
             conflicts. Creates the file if it doesn't exist. The text is
             appended exactly as provided — include leading newlines if needed
             for formatting. If the file was modified by another conversation
             since this session last read it, the append is redirected to a
             branch file to preserve both versions."

Input Schema:
  path:        string, required  — Absolute path to the file (must be within memory directory)
  text:        string, required  — Text to append
  session_id:  string, required  — Session ID from memory_session_start

Output Schema:
  success:         boolean
  bytes_written:   integer
  branch_created:  boolean   — True if a race was detected and a branch file was created
  branch_path:     string    — Path of the branch file (null if no branch created)
```

**Handler pseudo-code:**

```
func HandleSafeAppendFile(params SafeAppendFileParams) SafeAppendFileResult:

    // 1. Validate that the path is within the memory directory.
    absPath = filepath.Abs(params.Path)
    if !strings.HasPrefix(absPath, config.Memory.Directory):
        return error("safe_append_file is restricted to the memory directory: " +
                      config.Memory.Directory)

    // 2. Validate the session ID.
    if !sessionTracker.Exists(params.SessionID):
        return error("Unknown session_id: " + params.SessionID +
                      ". Call memory_session_start first.")

    // 3. Ensure parent directory exists.
    os.MkdirAll(filepath.Dir(absPath), 0755)

    // 4. Acquire the SAME write mutex as safe_read_file and safe_write_file.
    writeMutex.Lock()
    defer writeMutex.Unlock()

    // 5. Race detection (same logic as safe_write_file).
    targetPath = absPath
    branchCreated = false
    branchPath = ""

    if config.Branching.Enabled && fileExists(absPath):
        currentModTime = os.Stat(absPath).ModTime()
        lastSeenModTime = sessionTracker.GetLastRead(params.SessionID, absPath)

        if lastSeenModTime != nil && currentModTime.After(*lastSeenModTime):
            // Race detected. For append operations, the branch file is created
            // by copying the current base file content, then appending to the copy.
            // This preserves the full context in the branch.
            targetPath = branching.GenerateBranchPath(absPath)
            branchCreated = true
            branchPath = targetPath

            // Copy current base file to the branch path before appending.
            baseContent, _ = os.ReadFile(absPath)
            os.WriteFile(targetPath, baseContent, 0644)

            log.Info("Race detected for %s (session %s): branching to %s",
                      absPath, params.SessionID, targetPath)

    // 6. Open file for append (create if needed), write, close.
    f = os.OpenFile(targetPath, O_WRONLY|O_APPEND|O_CREATE, 0644)
    n, err = f.Write([]byte(params.Text))
    f.Close()

    if err:
        return error("Failed to append: " + err)

    // 7. Update session tracker with new ModTime.
    newModTime = os.Stat(targetPath).ModTime()
    sessionTracker.RecordRead(params.SessionID, absPath, newModTime)

    return {
        success: true,
        bytes_written: n,
        branch_created: branchCreated,
        branch_path: branchPath
    }
```

### 3.11 Write Mutex and Session Tracking

The write mutex serializes all memory file I/O. It is a single `sync.Mutex` shared by `safe_read_file`, `safe_write_file`, and `safe_append_file`.

**Why a single mutex works:** All conversations in the same Claude Desktop App instance share the same bridge process (same Go binary, same stdio pipe). Go's `sync.Mutex` provides in-process mutual exclusion — no file-locking APIs needed, no OS-specific behavior to worry about. When one conversation's tool call acquires the mutex, any other conversation's concurrent tool call blocks until the first releases it.

**Why reads also acquire the mutex:** `safe_read_file` must acquire the mutex to ensure that the `ModTime` it records is consistent with the file content it returns. Without this, a concurrent write could modify the file between the `Stat()` and `Read()` calls, causing the session tracker to record a stale `ModTime` for fresh content — which would defeat race detection.

**Why a single mutex (not per-file mutexes):** A per-file mutex would allow concurrent operations on different files, but the added complexity isn't justified. Memory I/O is infrequent (a few operations per session, each taking sub-millisecond I/O time) and the mutex hold time is negligible. A single mutex keeps the implementation trivial and eliminates any possibility of deadlock from lock ordering.

**What the mutex protects against and what it does not:** The mutex prevents torn writes (no interleaving of concurrent file operations) and ensures consistent `Stat()`-then-`Read()` / `Stat()`-then-`Write()` sequences. It does *not* prevent semantic divergence from concurrent read-modify-write sequences — that is handled by the session tracker and branching system (see [Section 3.12](#312-branching)).

**Session tracker:** The session tracker is an in-memory map that records, for each session, the `ModTime` of each file at the time it was last read or written by that session. This is the mechanism that enables race detection in `safe_write_file` and `safe_append_file`.

**Session tracker data structure (session.go):**

```go
package main

import (
    "sync"
    "time"
)

// SessionTracker records per-session file version information for
// concurrent read-modify-write race detection.
type SessionTracker struct {
    mu       sync.Mutex
    sessions map[string]*SessionInfo  // session_id → session info
    config   SessionConfig
}

type SessionInfo struct {
    StartedAt  time.Time
    FileReads  map[string]time.Time   // abs_path → last-seen ModTime
}

// Register creates a new session. If at capacity, evicts the oldest session.
func (st *SessionTracker) Register(sessionID string) { ... }

// RecordRead stores the ModTime for a file in a session's tracking map.
// Called by safe_read_file (after reading) and safe_write_file/safe_append_file
// (after writing, to update the baseline for subsequent writes).
func (st *SessionTracker) RecordRead(sessionID, absPath string, modTime time.Time) { ... }

// GetLastRead returns the last-seen ModTime for a file in a session, or nil
// if the session has never read this file.
func (st *SessionTracker) GetLastRead(sessionID, absPath string) *time.Time { ... }

// Exists checks whether a session ID is registered.
func (st *SessionTracker) Exists(sessionID string) bool { ... }
```

The session tracker uses its own `sync.Mutex` (separate from the write mutex) to protect concurrent access to the session map. This is safe because the session tracker is only accessed while the write mutex is held — but having its own mutex makes the session tracker independently testable and safe for future use patterns.

**Implementation (writemutex.go):**

```go
package main

import "sync"

// writeMutex serializes all memory file I/O across all concurrent
// conversations. safe_read_file, safe_write_file, and safe_append_file
// all acquire this mutex before performing any filesystem operations.
var writeMutex sync.Mutex
```

All three memory tool handlers call `writeMutex.Lock()` / `defer writeMutex.Unlock()` at the start of their I/O operations.

### 3.12 Branching

Branching is the mechanism that resolves the concurrent read-modify-write race condition. When `safe_write_file` or `safe_append_file` detects that a memory file has been modified by another conversation since the current session last read it, the write is redirected to a "branch" file instead of overwriting the other conversation's changes. This preserves data from all concurrent conversations at the cost of deferred merge complexity.

**When branching occurs:** A branch is created when ALL of the following conditions are true: (a) `config.Branching.Enabled` is `true`; (b) the target file already exists on disk; (c) the session tracker has a recorded `ModTime` for this file in the current session (meaning `safe_read_file` was previously called); (d) the file's current `ModTime` is newer than the session's recorded `ModTime` (meaning another conversation wrote to the file after this session last read it).

**When branching does NOT occur:** If the session has never read the file (e.g., creating a brand-new block), no baseline exists and no race is possible — the write proceeds normally. If branching is disabled in config, all writes use last-writer-wins semantics (the v1 behavior). If the `ModTime` matches, no race has occurred and the write proceeds normally.

**Branch file naming convention:**

```
<original-stem>.branch-<ISO8601-compact>-<random-suffix>.<ext>
```

Examples:
- `core.md` → `core.branch-20260313T142305-a1b2.md`
- `blocks/project-mcp-bridge.md` → `blocks/project-mcp-bridge.branch-20260313T142305-x7k9.md`
- `blocks/episodic-2026-03.md` → `blocks/episodic-2026-03.branch-20260313T142305-f3e1.md`

The naming convention is designed to be:
- **Parseable** — simple pattern matching (`*.branch-*.*`) identifies all branches; regex `^(.+)\.branch-(\d{8}T\d{6})-([0-9a-f]{4})\.(.+)$` extracts all components.
- **Sortable** — ISO 8601 compact timestamps sort chronologically by filename.
- **Self-documenting** — the creation timestamp is embedded in the filename, surviving bridge restarts with no external metadata.
- **Windows-safe** — no colons or special characters in the timestamp (uses `T` separator, no `:` or `-` within the time portion).
- **Collision-resistant** — the 4-hex-char random suffix (from `crypto/rand`) provides 65,536 possibilities per second, which is far more than needed given that branches are created under a mutex (at most one per mutex acquisition).

**Branch detection (branching.go):**

```
// FindBranches returns all branch files for a given base file path.
// For example, FindBranches("C:\franl\.claude-agent-memory\core.md")
// returns all files matching "core.branch-*.md" in the same directory.
func FindBranches(basePath string) []string:
    dir = filepath.Dir(basePath)
    stem = filenameStem(basePath)   // "core" from "core.md"
    ext = filepath.Ext(basePath)    // ".md"
    pattern = filepath.Join(dir, stem + ".branch-*" + ext)
    matches, _ = filepath.Glob(pattern)
    sort.Strings(matches)  // Chronological order (ISO timestamps sort correctly)
    return matches

// GenerateBranchPath creates a new branch filename for the given base path.
func GenerateBranchPath(basePath string) string:
    dir = filepath.Dir(basePath)
    stem = filenameStem(basePath)
    ext = filepath.Ext(basePath)
    timestamp = time.Now().Format("20060102T150405")  // Go's reference time format
    random = randomHex(4)  // 4 hex chars from crypto/rand
    return filepath.Join(dir, stem + ".branch-" + timestamp + "-" + random + ext)

// ExtractTimestamp parses the creation timestamp from a branch filename.
func ExtractTimestamp(branchPath string) string:
    // Parse "core.branch-20260313T142305-a1b2.md" → "2026-03-13T14:23:05"
    // Returns ISO 8601 format for the tool response.

// AnyBranchesExist checks if any branch files exist in the memory directory tree.
func AnyBranchesExist(memoryDir string) bool:
    // Walk the memory directory looking for any file matching *.branch-*.*
```

**`index.md` behavior with branches:** File names in `index.md` always reference the canonical (non-branched) names (e.g., `core.md`, `project-mcp-bridge.md`). The `Updated` date stamp in `index.md` reflects the most recent write to the file or any of its branches — whichever is later. This ensures that the index accurately represents "when was this topic last touched" regardless of branching.

**Merge process:** Branched files are reconciled via a **semantic merge** — not a textual three-way merge. The merger (typically a sub-agent spawned during off-hours) reads both the base file and each branch, understands the meaning and intent of the changes in each version, and produces a single unified file that preserves the important information from all versions. This is fundamentally different from `git merge`, which operates on text lines; our memory files are prose markdown where the semantic content matters more than the exact wording.

The merge process:

1. **Detection:** A sub-agent (or the primary agent, prompted by `branches_exist: true` from `memory_session_start`) identifies files with branches by scanning for `*.branch-*.*` in the memory directory.

2. **Reading:** The merger reads the base file and all its branches. The branch creation timestamps (from filenames) establish chronological order.

3. **Semantic merge:** The merger analyzes each version's content, identifies what information is unique to each version, what information is shared, and what information conflicts. For conflicts (e.g., two different status updates for the same project), the merger uses the chronologically latest version as authoritative, but preserves earlier information if it contains facts not present in the later version.

4. **Writing:** The merged result is written to the base file path via `safe_write_file`. The branch files are then deleted.

5. **Cost:** Merges cost tokens (the sub-agent must read and reason about the content). Simple merges (e.g., two conversations added different entries to an episodic log) can be handled by a cheaper model (Sonnet or Haiku). Complex merges (e.g., two conversations made conflicting updates to `core.md`) may require Opus.

**Merge scheduling:** Merges can be triggered in several ways: (a) manually by the user asking "please merge any branched memory files"; (b) at session start when `memory_session_start` returns `branches_exist: true` and the primary agent decides to merge before proceeding; (c) during off-hours via a scheduled wake-up (see [Chapter 9, Future Enhancements](stateful-agent-design-chapter9.md)). In all cases, the merge is performed by a sub-agent with `allow_memory_read: true` and access to the bridge's write tools.

**Expected frequency:** Branching is expected to be rare. It only occurs when two conversations are active simultaneously *and* both modify the same memory file. The typical usage pattern — one active conversation at a time — produces zero branches.

### 3.13 Async Executor

The async executor is the shared component that implements the hybrid sync/async execution model. Both `spawn_agent` and `run_command` delegate to it for subprocess lifecycle management. Extracting this into a shared component avoids duplicating the sync-window / async-handoff logic across tool handlers.

**Responsibilities:**
- Start a subprocess from a prepared `exec.Cmd`
- Capture stdout and stderr into a thread-safe buffer
- Wait up to `sync_window_seconds` for the process to complete (sync path)
- If the process completes within the sync window, return the result immediately
- If the process exceeds the sync window, register an async job with the job lifecycle manager and return a `job_id` (async path)
- Enforce the per-command timeout (kill process if it exceeds the deadline)
- Truncate output to the configured limit

**Why a separate component?** Before `run_command` was added, the sync/async logic lived inline in `spawn_agent`'s handler. With two tools now sharing the same pattern, extracting it prevents code duplication and ensures both tools have identical timeout, truncation, and async-handoff behavior. The async executor is purely internal — it is not an MCP tool and is not visible to the primary agent.

**Pseudo-code (async.go):**

```
type AsyncResult struct {
    Status    string    // "complete" or "running"
    JobID     string    // Non-null only if Status == "running"
    Stdout    string    // Captured stdout (sync path only)
    Stderr    string    // Captured stderr (sync path only)
    Truncated bool      // True if output was truncated
    ElapsedMs int       // Wall-clock milliseconds
    StartedAt string    // ISO 8601
}

// Run starts a subprocess and manages the sync/async handoff.
// The caller (spawn_agent or run_command) is responsible for constructing
// the exec.Cmd with the correct command, arguments, working directory, and stdin.
// The source parameter identifies which tool created the job (for check_agent's
// response and for logging).
func (ae *AsyncExecutor) Run(cmd *exec.Cmd, timeoutSeconds int,
                              maxOutput int, source string) AsyncResult:

    // 1. Set up output capture
    //    stdout and stderr are merged into a single thread-safe buffer
    //    so that interleaved output is preserved in order.
    outputBuffer = new ConcurrentBuffer()
    cmd.Stdout = outputBuffer
    cmd.Stderr = outputBuffer

    // 2. Start the subprocess
    startedAt = time.Now()
    err = cmd.Start()
    if err:
        return error("Failed to start process: " + err)

    // 3. Compute deadlines
    syncDeadline = startedAt.Add(config.Async.SyncWindowSeconds * time.Second)
    processDeadline = startedAt.Add(timeoutSeconds * time.Second)

    // 4. Wait for completion in a goroutine
    done = make(chan error, 1)
    go func():
        done <- cmd.Wait()

    // 5. Sync window: wait for process completion or sync deadline
    select:
        case err = <-done:
            // Process completed within sync window — return result immediately
            elapsed = time.Since(startedAt).Milliseconds()
            output = outputBuffer.String()
            truncated = false

            if len(output) > maxOutput:
                output = truncateMiddle(output, maxOutput)
                truncated = true

            return AsyncResult{
                Status:    "complete",
                JobID:     "",
                Stdout:    output,         // For run_command; spawn_agent uses as combined output
                Stderr:    "",             // Merged into Stdout
                Truncated: truncated,
                ElapsedMs: elapsed,
                StartedAt: startedAt.Format(ISO8601),
            }

        case <-time.After(time.Until(syncDeadline)):
            // Sync window expired — register async job for check_agent polling
            jobID = jobManager.Register(cmd.Process, outputBuffer, startedAt,
                                         processDeadline, maxOutput, done, source)

            log.Info("Process exceeded sync window, source=%s, job_id=%s", source, jobID)

            elapsed = time.Since(startedAt).Milliseconds()
            return AsyncResult{
                Status:    "running",
                JobID:     jobID,
                Stdout:    "",
                Stderr:    "",
                Truncated: false,
                ElapsedMs: elapsed,
                StartedAt: startedAt.Format(ISO8601),
            }
```

**Timeout enforcement:** When a process exceeds its `timeoutSeconds` deadline, it is killed by one of two mechanisms: (a) `check_agent` detects the deadline has passed and kills the process when polled, or (b) the job lifecycle manager's cleanup goroutine kills expired processes during its periodic sweep. This dual-path ensures processes are killed even if the primary agent never polls.

### 3.14 Job Lifecycle Manager

The job manager is a background goroutine that tracks active async jobs (from both `spawn_agent` and `run_command`) and cleans up expired ones.

**Data structures:**

```
type Job struct {
    ID             string
    Source         string              // "spawn_agent" or "run_command" — identifies which tool created the job
    Process        *os.Process
    OutputBuffer   *ConcurrentBuffer   // Thread-safe buffer capturing stdout+stderr
    StartedAt      time.Time
    Deadline       time.Time           // StartedAt + TimeoutSeconds
    MaxOutput      int                 // Token limit (spawn_agent) or byte limit (run_command)
    Done           chan error           // Signaled when process exits
    Collected      bool                // True after check_agent retrieves the result
}

type JobManager struct {
    mu     sync.Mutex
    jobs   map[string]*Job
    config Config
}
```

**Pseudo-code for the background cleanup goroutine:**

```
func (jm *JobManager) CleanupLoop():
    ticker = time.NewTicker(30 * time.Second)  // Check every 30s

    for range ticker.C:
        jm.mu.Lock()
        now = time.Now()

        for id, job in jm.jobs:
            // Clean up collected jobs immediately
            if job.Collected:
                delete(jm.jobs, id)
                continue

            // Clean up uncollected jobs that have expired
            // (process finished but primary agent never polled)
            expiryTime = job.StartedAt.Add(config.Async.JobExpirySeconds * time.Second)
            if now.After(expiryTime):
                // If process is still running, kill it
                if !job.ProcessDone():
                    job.Process.Kill()
                log.Warn("Job %s (source=%s) expired without being collected", id, job.Source)
                delete(jm.jobs, id)

        jm.mu.Unlock()
```

**Job ID generation:** Use a short, human-readable ID composed of a prefix and random suffix, e.g., `job-a1b2c3`. The prefix makes log entries easy to grep. Use `crypto/rand` for the random component.

### 3.15 Logging

All bridge operations are logged to a file for auditability and debugging. Logging does **not** go to stdout/stderr (those are reserved for MCP stdio transport).

**What to log:**

| Event | Level | Fields |
|-------|-------|--------|
| Bridge started | info | config path, version |
| Tool call received | info | tool name, abbreviated params |
| spawn_agent: subprocess launched | info | job_id (if async), model, working_dir |
| spawn_agent: sync completion | info | elapsed time, output size |
| spawn_agent: async handoff | info | job_id, elapsed time at handoff |
| run_command: command executed | info | command (first 200 chars), working_dir, timeout |
| run_command: sync completion | info | exit_code, elapsed time, output size, truncated |
| run_command: async handoff | info | job_id, command (first 200 chars), elapsed time at handoff |
| check_agent: status poll | debug | job_id, source, status, elapsed |
| check_agent: result collected | info | job_id, source, status, elapsed, output size |
| memory_session_start: new session | info | session_id |
| safe_read_file: read | info | path, session_id, has_branches, bytes read |
| safe_write_file: write | info | path, session_id, bytes written, branch_created |
| safe_write_file: race detected | warn | path, session_id, branch_path |
| safe_append_file: append | info | path, session_id, bytes written, branch_created |
| safe_append_file: race detected | warn | path, session_id, branch_path |
| Job expired | warn | job_id, reason |
| Sub-agent killed (timeout) | warn | job_id, elapsed |
| Error (any) | error | tool name, error details |
| Bridge shutdown | info | active jobs killed |

**Format:** Structured JSON lines (one JSON object per log line). This is easy to parse, grep, and pipe into log aggregation tools.

```json
{"ts":"2026-02-21T14:30:00Z","level":"info","msg":"spawn_agent: subprocess launched","job_id":"job-a1b2c3","model":"sonnet","working_dir":"C:\\franl\\git\\mcp-bridge"}
```

### 3.16 Error Handling

The bridge should never crash from a tool call. All errors are caught and returned as MCP tool errors.

**Error categories:**

| Category | Example | Behavior |
|----------|---------|----------|
| Configuration error | Missing config file, invalid YAML | Bridge fails to start with clear error message |
| Tool input validation | Missing required param, invalid path | Return MCP tool error immediately |
| Subprocess launch failure | `claude` not found, shell not found, permission denied | Return MCP tool error with details |
| Subprocess timeout | Sub-agent or command exceeds `timeout_seconds` | Kill process, return `timed_out` status via `check_agent` |
| Subprocess crash | `claude -p` or shell command exits with non-zero | Return output + exit code via `result` field |
| Shell not found | Configured `run_command.shell` path doesn't exist | Return MCP tool error; verify Cygwin installation |
| File I/O error | Permission denied, disk full | Return MCP tool error with OS error details |
| Concurrent agent cap reached | 5 sub-agents already running | Return MCP tool error suggesting the user wait or check existing jobs |
| Unknown session ID | `session_id` not in tracker | Return MCP tool error: "Call memory_session_start first" |
| Branch creation failure | Disk full or permissions error during branch write | Return MCP tool error with OS error details; base file is not modified |

### 3.17 Graceful Shutdown

The bridge runs as a subprocess of Claude Desktop, communicating over stdio (stdin/stdout). When Claude Desktop *exits* (not merely when a conversation is closed — the bridge persists for the full desktop session), it closes the stdin pipe. **Stdin EOF is the authoritative shutdown signal** for the bridge — it is the only shutdown mechanism that works reliably on Windows and is consistent with the MCP stdio transport model.

Note: UNIX signals are not used for shutdown. On Windows, SIGTERM does not exist as an inter-process signal, and SIGINT is only available when a console window is present (Ctrl+C). Since the bridge runs as a background stdio subprocess with no attached console, neither signal is reliably deliverable. Stdin EOF is the correct and portable mechanism.

**Shutdown sequence when stdin EOF is detected:**

1. The `mcp-go` SDK's stdio read loop detects EOF on stdin and exits naturally.
2. The bridge detects the loop exit and begins shutdown.
3. Kill all running subprocesses — both sub-agents (from `spawn_agent`) and shell commands (from `run_command`) — by calling `Process.Kill()` on each active job. On Windows, this calls `TerminateProcess` immediately; there is no SIGTERM grace period.
4. Log the shutdown and number of jobs terminated.
5. Exit cleanly.

**Pseudo-code:**

```
func main():
    // ... setup ...

    // Start the MCP stdio server. This blocks until stdin is closed (EOF),
    // which happens when Claude Desktop exits or kills the bridge process.
    // The mcp-go SDK handles the stdio read/write loop internally.
    server.Run()  // returns when stdin closes

    // Stdin EOF received — begin graceful shutdown
    log.Info("Stdin EOF detected, killing %d active jobs", jobManager.ActiveCount())
    jobManager.KillAll()  // calls Process.Kill() on all running subprocesses
    os.Exit(0)
```


---

## 4. Memory System (Layer 2)

### 4.1 Two-Layer Memory Model

The full memory system has two layers with distinct characteristics:

| | Layer 1 (Anthropic built-in) | Layer 2 (Supplementary) |
|---|---|---|
| **Storage** | Anthropic's cloud (opaque) | Local markdown files |
| **Capacity** | ~500–2,000 tokens (Anthropic-managed) | Unbounded (loaded on demand) |
| **Loaded when** | Every turn (automatic) | At session start + on demand |
| **Update mechanism** | Indirect via `memory_user_edits` steering instructions | Direct via Bridge:safe_write_file, safe_append_file |
| **Update lag** | ~24 hours (nightly regeneration) | Immediate |
| **Content** | Identity, preferences, high-level project list | Deep project context, episodic recall, decisions, technical notes |
| **Editable by user** | Via Claude.ai Settings > Memory | Via any text editor |
| **Visible to sub-agents** | No (platform limitation) | Optional read-only access |

Layer 1 is always present and automatic. Layer 2 is opt-in, managed by the memory skill, and provides the depth that Layer 1 cannot. Together they approximate the functionality of purpose-built agent memory systems like Letta (formerly MemGPT), while maintaining full transparency and portability.

### 4.2 Three-Tier File Structure

Layer 2 is organized as a three-tier hierarchy inspired by Tim Kellogg's Strix architecture. The tiers correspond to access frequency and specificity:

```
C:\franl\.claude-agent-memory\
├── bridge-config.yaml           # MCP bridge configuration
├── core.md                      # Tier 1: Identity (always loaded, ~500–1,000 tokens)
├── index.md                     # Tier 2: Topic index (always loaded, ~300–800 tokens)
└── blocks\                      # Tier 3: Content (loaded on demand)
    ├── project-mcp-bridge.md    #   Project-specific context
    ├── project-agent-memory.md  #   Another project
    ├── reference-go-patterns.md #   Persistent reference material
    ├── decisions.md             #   Cross-project architectural decisions
    ├── episodic-2026-02.md      #   February 2026 conversation log
    ├── episodic-2026-03.md      #   March 2026 conversation log
    └── *.branch-*.*             #   Branch files (temporary, created by race
                                 #   detection, merged and deleted during off-hours)
```

**Loading rules:**

| Tier | File(s) | Loaded when | Approximate budget |
|------|---------|-------------|-------------------|
| Tier 1 | `core.md` | Every session start, before first response | 500–1,000 tokens |
| Tier 2 | `index.md` | Every session start, before first response | 300–800 tokens |
| Tier 3 | `blocks/*.md` | On demand, when conversation topic matches an index entry | Varies per block |

The total fixed context cost per session is Tier 1 + Tier 2 + skill instructions ≈ 1,500–3,000 tokens. This is a bounded, predictable cost that does not grow as the memory store expands (only the number of blocks grows; the blocks themselves are loaded selectively).

### 4.3 File Format: core.md

The core file is a compact narrative summary — the Layer 2 equivalent of "who am I and what am I working on." It is pure prose markdown with no YAML frontmatter (it doesn't need machine-readable metadata because it's always loaded in full).

**Target size:** 500–1,000 tokens (~400–800 words). If it grows beyond this, content should be migrated to dedicated blocks and the core should retain only summaries.

**Example:**

```markdown
# Core

Fran is a retired principal software engineer living in Massachusetts. He has deep
expertise in AI/ML systems, particularly stateful memory architectures for AI agents.
His primary programming language is Go, and he prefers detailed, comprehensive
explanations for technical topics.

## Active Projects

- **MCP Bridge Server** — A Go-based MCP bridge providing sub-agent spawning and
  local machine access to the Claude Desktop App. Currently in implementation phase.
  See `project-mcp-bridge.md` for details.

- **Stateful Agent Memory** — The Layer 2 memory system itself. Designing the
  file formats, session lifecycle, and skill instructions. See `project-agent-memory.md`.

## Key Facts

- GitHub username: fpl9000
- Bluesky handle: fpl9000.bsky.social
- Pronouns: he/him
- Prefers well-commented code (nearly as many comment lines as code lines)
- Uses Windows 11 with Cygwin; sub-agents should use Cygwin conventions
- Has caregiving responsibilities that sometimes interrupt sessions

## Communication Preferences

- Prefers clear but detailed responses; include technical details freely
- Prefers prose over bullet points in explanations
- Values authoritative sources and systematic approaches
```

### 4.4 File Format: index.md

The index is a markdown table mapping block filenames to one-line summaries and last-updated dates. Claude uses it to decide which blocks to load for the current conversation.

**Example:**

```markdown
# Index

| Block | Summary | Updated |
|-------|---------|---------|
| project-mcp-bridge.md | MCP bridge server: Go implementation, tool design, testing status | 2026-02-21 |
| project-agent-memory.md | Layer 2 memory system design and skill development | 2026-02-21 |
| reference-go-patterns.md | Go idioms, error handling patterns, and package conventions | 2026-02-15 |
| decisions.md | Cross-project architectural decisions and rationale | 2026-02-19 |
| episodic-2026-02.md | Conversation log for February 2026 | 2026-02-21 |
```

**Maintenance rule:** When Claude creates or updates a block, it must also update the corresponding row in `index.md` (or add a new row if the block is new). This is a compliance-based instruction in the memory skill.

### 4.5 File Format: Content Blocks

Content blocks use markdown with optional YAML frontmatter. The frontmatter provides machine-readable metadata for future search/filtering; the body is free-form markdown optimized for Claude's comprehension.

**Project block example:**

```markdown
---
created: 2026-02-15
updated: 2026-02-21
tags: [project, go, mcp]
---

# MCP Bridge Server

## Status
Implementation in progress. Core module structure defined. spawn_agent handler
is the current focus.

## Key Decisions
- Language: Go (single static binary, no runtime dependencies)
- MCP SDK: mark3labs/mcp-go
- Transport: stdio only (B1 architecture — no HTTP transport needed initially)
- Tools provided: spawn_agent, check_agent, append_file only (lean bridge)
- Basic filesystem: delegated to Anthropic's Filesystem extension (Path A)

## Architecture
The bridge is a single Go binary that registers five MCP tools via the mcp-go SDK.
It communicates with Claude Desktop over stdin/stdout using MCP's stdio transport.
Sub-agents are launched as `claude -p` subprocesses.

## Open Issues
- Need to test hybrid sync/async with real Claude Desktop (not just unit tests)
- Determine if output truncation heuristic (chars/4) is accurate enough
- Need Windows-specific testing for process management (SIGTERM behavior)

## Technical Notes
- The sync window (25s) was chosen to stay under Claude Desktop's ~30s reliability
  threshold. See proposal Open Question #3.
- Job IDs use crypto/rand for the random component (not math/rand).
```

**Reference block example:**

```markdown
---
created: 2026-02-10
updated: 2026-02-18
tags: [reference, go]
---

# Go Patterns and Conventions

## Error Handling
- Always wrap errors with context: fmt.Errorf("doing X: %w", err)
- Use errors.Is() and errors.As() for sentinel errors
- Return early on error; keep the happy path unindented

## Concurrency
- Prefer channels for signaling, mutexes for shared state
- Always use sync.WaitGroup for goroutine lifecycle management
- Context propagation: pass ctx as first parameter
...
```

### 4.6 File Format: Episodic Logs

Episodic logs are monthly files (`episodic-YYYY-MM.md`) containing dated entries for each significant conversation. New entries are appended to the current month's file via `Bridge:append_file`.

**Example:**

```markdown
---
created: 2026-02-01
updated: 2026-02-21
---

# February 2026

## 2026-02-21 — Stateful agent design document
Created the detailed design document for the stateful agent system (MCP bridge,
memory system, memory skill, sub-agents). Resolved all 27 open questions in the
proposal. Design document written to C:\franl\git\ai-skills\docs\agent-memory-design.md.

## 2026-02-20 — Proposal session 10: Open Questions #20–27
Resolved memory format (markdown + YAML frontmatter), filesystem access (lean bridge
+ Anthropic extension), hybrid environment ambiguity (three complementary strategies),
episodic granularity (monthly), block naming conventions, block reference clarification,
and sub-agent timing fields.

## 2026-02-19 — Proposal session 9: Hybrid sync/async execution
Discovered Claude Desktop's 60-second MCP timeout. Redesigned spawn_agent with hybrid
sync/async model. Resolved Open Questions #18 (system prompt), #4 (layer reconciliation),
#10 (concurrent writes), #9 (layer boundary), #19 (CLAUDE.md optimization).
```

**Entry format:** Each entry has a heading with date and brief title (`## YYYY-MM-DD — Title`), followed by a short prose summary (2–5 sentences). The summary should capture what was accomplished, any significant decisions, and any artifacts produced. It is deliberately concise — detailed project context belongs in project blocks, not in the episodic log.

**Appending new entries:** The memory skill instructs Claude to append a new entry at the end of the current month's episodic file before the session ends (or incrementally during long sessions). The `Bridge:append_file` tool is used instead of a full rewrite to avoid clobbering existing entries.

### 4.7 File Format: decisions.md

A single cross-project file for architectural decisions and their rationale. Unlike project blocks, this captures decisions that span projects or affect the overall system.

**Example:**

```markdown
---
created: 2026-02-10
updated: 2026-02-21
tags: [decisions, architecture]
---

# Architectural Decisions

## 2026-02-21 — Lean bridge (Path A)
The MCP bridge provides only spawn_agent, check_agent, and append_file. All basic
filesystem operations use the Anthropic Filesystem extension. Rationale: minimize
custom code, leverage existing infrastructure. Can upgrade to Path B (self-contained
bridge) if tool name collisions cause problems.

## 2026-02-19 — Hybrid sync/async execution model
spawn_agent uses a 25-second sync window. Tasks completing within the window return
results directly; longer tasks return a job_id for async polling. This works around
Claude Desktop's hardcoded ~60-second MCP timeout. Rationale: simpler than progress
tokens, no protocol extensions needed, and enables parallel sub-agents as a natural
extension.

## 2026-02-15 — Go for MCP bridge
Chose Go over Python, Rust, and TypeScript. Single static binary, excellent subprocess
management, fast startup. The mark3labs/mcp-go SDK is mature enough. Rationale: no
runtime dependencies means installation is just copying the .exe.
```

### 4.8 Block Naming Conventions

| Pattern | Usage | Examples |
|---------|-------|---------|
| `project-<name>.md` | Active or completed projects | `project-mcp-bridge.md`, `project-website.md` |
| `reference-<topic>.md` | Persistent reference material | `reference-go-patterns.md`, `reference-deploy-checklist.md` |
| `episodic-YYYY-MM.md` | Monthly conversation logs | `episodic-2026-02.md`, `episodic-2026-03.md` |
| `decisions.md` | Cross-project architectural decisions | (Single file) |

**When to create a new block:** When a conversation introduces a significant new project or topic that warrants its own structured tracking, and the content doesn't fit naturally into an existing block. Trivial or one-off topics belong as entries in the current month's episodic log, not as standalone blocks.

**When not to create a new block:** For temporary information, questions that are fully resolved in the current conversation, or topics that only need a brief mention (add to episodic log instead).

### 4.9 Why Markdown (Not JSON, SQLite, or YAML)

This decision is fundamental and is not revisited in the design. The rationale:

| Format | Decision |
|--------|-----------------|
| **JSON** | *Rejected:* Not human-readable at scale. Requires programmatic tooling to inspect or edit. Not Git-diff-friendly for prose content. Claude reads text natively — markdown is optimal. |
| **SQLite** | *Rejected:* Opaque binary format. Cannot be inspected in a text editor or GitHub web UI. Merge conflicts are unresolvable. Overkill for the expected data volume (dozens of files, hundreds of KB). |
| **YAML** | *Rejected:* Fragile whitespace sensitivity. Poor for long-form prose. Acceptable for metadata (hence the optional YAML frontmatter), but not for content bodies. |
| **Markdown** | *Accepted:* Human-readable, human-editable, Git-friendly diffs, viewable in any text editor or GitHub, Claude-native format, no parsing dependencies. Trade-off: lookups require reading files, not querying an index — acceptable at our scale. |

### 4.10 Branching and Merge

When the bridge detects a concurrent read-modify-write race on a memory file, it writes the racing conversation's changes to a "branch" file instead of overwriting the base file. This preserves data from all concurrent conversations. See [Chapter 3, Section 3.12](stateful-agent-design-chapter3.md#312-branching) for the branch file naming convention, detection mechanism, and merge process details.


**Branch files are transient.** They exist only until a merge process reconciles them with the base file. They are not referenced by `index.md` (which always uses canonical filenames) and are not part of the permanent memory structure.

**`index.md` interaction:** The `Updated` column in `index.md` always reflects the most recent modification to a file *or any of its branches*. This ensures that index-based relevance decisions account for recent branch activity. File names in the `Block` column are always canonical (non-branched) names.

**Merge semantics:** Merges are *semantic*, not textual. A merge sub-agent reads the base file and all its branches, understands the meaning of each version's content, and produces a single unified file that preserves important information from all versions. This is necessary because memory files are prose markdown — a line-based three-way merge (as in `git merge`) would produce incoherent results when two conversations independently rewrite the same paragraph.

**Example scenario:**

1. Conversation A reads `core.md` (which lists Project X as "in progress").
2. Conversation B also reads `core.md`.
3. Conversation A updates `core.md` to mark Project X as "completed" and adds Project Y.
4. Conversation B attempts to update `core.md` to add a new preference. The bridge detects the race (file modified since B's read) and writes B's version to `core.branch-20260313T1423-a1b2.md`.
5. Later, a merge sub-agent reads both versions. It produces a merged `core.md` that marks Project X as "completed" (from A), includes Project Y (from A), and includes the new preference (from B). The branch file is deleted.

---

## 5. Memory Skill

### 5.1 Skill Packaging

The memory skill is a Claude Desktop skill packaged as a .zip file containing a single `SKILL.md` file. It does not contain scripts (all operations use existing MCP tools). The .zip is uploaded via Claude Desktop > Settings > Capabilities.

```
stateful-memory.zip
└── SKILL.md           # Instructions for Layer 2 memory lifecycle
```

**Why no scripts?** All memory read/write operations are performed via the bridge's MCP tools (`safe_read_file`, `safe_write_file`, `safe_append_file`), with `Filesystem:search_files` available as an interim search fallback (see [OQ#13](stateful-agent-design-chapter11.md)). No Python or shell scripts are needed. This eliminates dependency management and makes the skill trivially portable.

### 5.2 SKILL.md Content

The SKILL.md below is the complete skill instruction file. It is the primary artifact that controls Claude's memory behavior.

```markdown
# Stateful Agent Memory Skill

You have access to a persistent memory system stored as markdown files on the local
filesystem. This memory persists across conversations and gives you deep context
about the user, their projects, and your shared history.

## CRITICAL: Use the Correct Tools for Memory Operations

All memory file reads and writes MUST go through the bridge's memory tools. These
tools provide session tracking, race detection, and branching to prevent concurrent
conversations from overwriting each other's updates.

1. **Session initialization:** Call `Bridge:memory_session_start` once at the start
   of every conversation. This returns a `session_id` that you MUST pass to all
   subsequent memory tool calls. Store this ID and use it consistently.

2. **Reading memory files:** Use `Bridge:safe_read_file(path, session_id)`.
   This records the file version so the bridge can detect races on later writes.
   If branched versions of the file exist (from a prior concurrent write race),
   their content will be included in the response, annotated as branches.

3. **Writing memory files:** Use `Bridge:safe_write_file(path, content, session_id)`
   for full file replacement, or `Bridge:safe_append_file(path, text, session_id)`
   for appending (primarily for episodic logs). If the bridge detects that another
   conversation modified the file since you last read it, your write is automatically
   redirected to a branch file — no data is lost.

4. **Searching memory files:** Use `Filesystem:search_files` on the memory directory.
   The bridge does not yet have a dedicated search tool (planned for v1.1), so
   searching via the Filesystem extension is the accepted v1 workaround.
   **Important:** If a search result hits a `.branch-*` file (e.g.,
   `core.branch-20260313T1423-a1b2.md`), do NOT read the branch file directly.
   Instead, call `Bridge:safe_read_file` on the corresponding base file (e.g.,
   `core.md`), which will return both the base content and all branch content in
   a properly annotated structure.

NEVER use `Filesystem:read_file`, `Filesystem:write_file`, or `Filesystem:edit_file`
for memory files — those bypass session tracking, race detection, and branching.
`Filesystem:search_files` is the one exception, permitted only for search (not for
reading file content). After finding a file via search, always read it through
`Bridge:safe_read_file`.

NEVER use cloud VM tools (`bash_tool`, `create_file`, `str_replace`) for persistent data.
The cloud VM filesystem is ephemeral and resets between sessions.

Memory files live at `C:\franl\.claude-agent-memory\` — always access them via the
bridge memory tools listed above.

## Memory Directory

Location: C:\franl\.claude-agent-memory\

Structure:
- core.md — Your identity summary and active project list. Always load this first.
- index.md — Table mapping block filenames to summaries. Always load after core.md.
- blocks\ — Individual content files. Load on demand based on conversation topic.
- *.branch-*.* — Temporary branch files from concurrent write races (if any exist).

## Session Start Protocol

At the start of every conversation, BEFORE responding to the user's first message:

1. Call `Bridge:memory_session_start` to get a session_id. Store it for the session.
   If the response includes `branches_exist: true`, note this — you may want to
   trigger a merge later (or mention it to the user).
2. Read core.md via `Bridge:safe_read_file(path, session_id)`
3. Read index.md via `Bridge:safe_read_file(path, session_id)`
4. Scan the index for blocks relevant to the user's opening message
5. If a relevant block exists, read it via `Bridge:safe_read_file(path, session_id)`
6. Now respond to the user, informed by your loaded context

If core.md does not exist, this is a first-run scenario. Create the memory directory
structure and seed core.md with basic information from Layer 1 (your built-in memory)
and the current conversation.

## Handling Branches

If `safe_read_file` returns branches for a file (the `has_branches` field is true),
this means another conversation's changes were saved to a branch file during a
concurrent write race. The branch content represents changes that haven't been
merged yet.

When you encounter branches:
- Consider ALL versions (base + branches) when answering questions about the topic.
- The base file is the "main line" and branches contain divergent changes.
- You can offer to merge branches by spawning a sub-agent, or mention to the user
  that unmerged branches exist.
- Do NOT manually rewrite the base file to include branch content — use the merge
  process instead (spawn a sub-agent with merge instructions).

## During the Conversation

### When to Read Blocks
- When the conversation shifts to a topic listed in index.md that you haven't loaded
- When the user asks "what do you remember about X?" and X matches a block
- When you need project context to give an informed answer
- Always use `Bridge:safe_read_file(path, session_id)` — never `Filesystem:read_file`

### When to Search Memory
If you need to find content in memory but the index doesn't clearly identify which
block contains it (e.g., the user asks about a specific term or decision and the
index summaries are too terse to match):

1. Use `Filesystem:search_files` on the memory directory (`C:\franl\.claude-agent-memory\`)
2. Review the search results. If any hit is on a `.branch-*` file, note the
   corresponding base filename (e.g., `core.branch-20260313T1423-a1b2.md` → `core.md`)
3. Call `Bridge:safe_read_file(path, session_id)` on the base file — this returns
   both the base content and any branch content in a properly annotated structure
4. Never read a branch file directly via `Filesystem:read_file` — always go through
   `safe_read_file` on the base file

### When to Write Memory
Write memory updates incrementally as significant information emerges. Do NOT
accumulate changes and batch-write at session end — sessions can end abruptly.

**Write to core.md** (via `Bridge:safe_write_file(path, content, session_id)`) when:
- A new project starts or an existing project's status changes significantly
- Key facts about the user change (role, location, preferences)
- Keep core.md under ~1,000 tokens. Move detailed content to blocks.
- Provide the COMPLETE updated file content (safe_write_file does full replacement)

**Write to index.md** (via `Bridge:safe_write_file(path, content, session_id)`) when:
- You create a new block (add a row)
- A block's summary needs updating (edit the Summary column)
- A block's content changes (update the Updated column)
- Provide the COMPLETE updated file content

**Write to blocks** (via `Bridge:safe_write_file(path, content, session_id)`) when:
- Significant project decisions are made
- Technical details worth remembering emerge
- The user shares information that will be useful in future sessions
- Provide the COMPLETE updated file content

**Append to episodic log** (via `Bridge:safe_append_file(path, text, session_id)`) when:
- Periodically during long sessions (every 30–60 minutes)
- At natural breakpoints in the conversation
- Before the session ends (if you sense the user is wrapping up)
- Format: `## YYYY-MM-DD — Brief Title\nSummary paragraph.\n\n`
- Target file: `blocks\episodic-YYYY-MM.md` (current month)

### When to Create New Blocks
If a conversation introduces a significant new project or topic that doesn't fit
into existing blocks, create a new block file:
- Projects: project-<name>.md
- Reference material: reference-<topic>.md
- Always add a corresponding row to index.md
- Do NOT create blocks for trivial or one-off topics — those go in the episodic log

### Memory Quality Guidelines
- Be concise. Memory files are loaded into your context window — every token counts.
- Prefer facts and decisions over process narrative. "Chose Go for single-binary
  deployment" is better than "We discussed several languages and eventually decided
  on Go because..."
- Date-stamp significant decisions and status changes.
- When updating a file with `Bridge:safe_write_file`, provide the COMPLETE updated
  content. The tool does a full file replacement (it does not do surgical edits).
  Read the file first via `Bridge:safe_read_file` if you don't already have its
  content in context. Always include your session_id in every tool call.
- If a write returns `branch_created: true`, this means the file was modified by
  another conversation since you last read it. Your changes were saved to a branch
  file. This is normal — the branch will be merged later.

## Session End

If the user says goodbye, thanks you, or the conversation is clearly winding down:

1. Persist any pending memory updates (core.md, index.md, relevant blocks)
2. Append an entry to the current month's episodic log summarizing the session
3. You do not need to announce that you're saving memory — just do it

## Handling User Questions About Memory

If the user asks "what do you remember about X?":
1. Check index.md for blocks related to X
2. If the index clearly identifies a relevant block, read it via
   `Bridge:safe_read_file(path, session_id)`
3. If the index doesn't clearly match (summaries are too terse), fall back to
   `Filesystem:search_files` on the memory directory to find which files mention X.
   If search hits a `.branch-*` file, read the corresponding base file via
   `safe_read_file` instead.
4. If any loaded blocks have branches, consider all versions
5. Combine with any Layer 1 (built-in) memory you have
6. Respond naturally, as if recalling from your own knowledge

If the user asks to correct or delete a memory:
1. Read the file via `Bridge:safe_read_file`, make the correction, and write via
   `Bridge:safe_write_file(path, content, session_id)`
2. Acknowledge the correction

If the user asks to see their memory files:
1. You can show them the contents of specific files
2. Remind them that the files are plain markdown at `C:\franl\.claude-agent-memory\`
   and can be edited with any text editor
```

### 5.3 Session Lifecycle

Detailed sequence of operations at each session phase:

```
Session Start
│
├─ 1. Skill instructions loaded into context (automatic, ~500 tokens)
├─ 2. Layer 1 memory loaded into context (automatic, ~500–2,000 tokens)
├─ 3. Call Bridge:memory_session_start → receive session_id (store for session)
│     If branches_exist is true, note for potential merge
├─ 4. Read core.md (Bridge:safe_read_file with session_id, ~500–1,000 tokens)
├─ 5. Read index.md (Bridge:safe_read_file with session_id, ~300–800 tokens)
├─ 6. Evaluate user's first message against index entries
├─ 7. Read relevant blocks if any match (Bridge:safe_read_file, varies)
└─ 8. Respond to user's first message
│
Session Active
│
├─ On topic change → Check index, load relevant blocks (Bridge:safe_read_file)
├─ On significant information → Update relevant block or core.md (Bridge:safe_write_file)
├─ On new project/topic → Create new block + update index.md (Bridge:safe_write_file)
├─ On decision made → Update decisions.md or project block (Bridge:safe_write_file)
├─ Every 30–60 minutes → Append episodic log entry (Bridge:safe_append_file)
├─ On context pressure → Summarize verbose blocks to free tokens
├─ On branch_created response → Note that branching occurred (merge needed later)
└─ On branches_exist at session start → Optionally trigger merge via sub-agent
│     (All write/append calls include session_id)
│
Session End (if detectable)
│
├─ 1. Write pending updates to core.md, index.md, blocks (Bridge:safe_write_file)
├─ 2. Append episodic log entry summarizing the session (Bridge:safe_append_file)
└─ 3. (No announcement needed — just persist silently)
```

### 5.4 Memory Write Triggers

The skill should write memory when these conditions are met:

| Trigger | What to write | Where |
|---------|---------------|-------|
| New project started | Project name, initial description, goals | New `project-<name>.md` + `index.md` row + `core.md` update |
| Significant decision made | Decision, rationale, date | `decisions.md` or relevant project block |
| Project status change | New status, what changed | `core.md` (summary) + project block (detail) |
| User shares key fact | The fact, context | `core.md` (if high-level) or relevant block |
| Technical pattern discovered | The pattern, when to use it | `reference-<topic>.md` |
| Session in progress (periodic) | Brief summary of what's happened so far | `episodic-YYYY-MM.md` (via `safe_append_file`) |
| Session ending | Session summary | `episodic-YYYY-MM.md` (via `safe_append_file`) |

### 5.5 Memory Read Triggers

| Trigger | What to read | Why |
|---------|--------------|-----|
| Session start (always) | `core.md`, `index.md` | Establish identity and awareness of available context |
| User mentions a project | The project's block | Load detailed context for informed responses |
| User asks "what do you remember" | Relevant blocks based on the topic | Provide comprehensive recall |
| User references a past decision | `decisions.md` or relevant project block | Provide accurate rationale |
| Planning future work | Relevant project blocks + `decisions.md` | Inform planning with historical context |

### 5.6 Reconciliation with Layer 1

Periodically (monthly, or when the user requests it), the primary agent should reconcile Layer 1 and Layer 2:

**Step 1:** Spawn a sub-agent with `allow_memory_read: true` to read all Layer 2 files and produce a structured digest:
```
spawn_agent(
  task: "Read all files in C:\franl\.claude-agent-memory\ and produce a structured 
         digest listing: active projects, completed projects, key facts,
         recent decisions, and any stale or contradictory content.",
  allow_memory_read: true,
  model: "sonnet"  // Routine analysis task
)
```

**Step 2:** The primary agent (which has Layer 1 in context automatically) compares both layers and identifies:
- **Gaps:** Important Layer 2 facts that Layer 1 should summarize
- **Contradictions:** Layer 1 says a project is active, Layer 2 says it's completed
- **Stale entries:** Layer 1 references outdated information

**Step 3:** The primary agent applies fixes:
- **Layer 1 fixes:** Add steering edits via `memory_user_edits` tool. These are incorporated by Anthropic's nightly regeneration (~24-hour lag).
- **Layer 2 fixes:** Edit files directly via `Bridge:safe_write_file` (immediate effect).


---

## 6. Sub-Agent System

### 6.1 Command Construction

The bridge constructs a `claude -p` command from `spawn_agent` parameters. Here is the exact mapping:

```
claude
  --print                                    # Always: non-interactive pipe mode
  --output-format text                       # Always: plain text output (not JSON)
  --system-prompt "<preamble + system_prompt>" # Always: full system prompt replacement
  [--model <model>]                          # If model parameter provided
  [--add-dir <memory_dir>]                   # If allow_memory_read is true
  [--add-dir <dir1>] [--add-dir <dir2>] ... # For each additional_dirs entry
```

The `task` string is piped to the subprocess's stdin.

**Working directory:** Set via `proc.Dir` in Go's `exec.Cmd`. This also activates Claude Code's directory sandbox — the sub-agent cannot access files outside this directory (or explicitly granted `--add-dir` directories).

### 6.2 Default System Preamble

This preamble is injected into every sub-agent invocation. Because `--system-prompt` replaces Claude Code's entire default behavioral prompt (empirically confirmed), this is the sole set of behavioral instructions the sub-agent receives.

```
You are a sub-agent performing a focused task on behalf of a primary Claude conversation.

Rules:
- Complete the assigned task and return your findings as text output.
- Be concise and structured. Prefer markdown formatting for readability.
- Keep your response under 2,000 words unless the task requires more detail. Your output
  will be truncated if it exceeds a token budget, so prioritize the most important findings.
- Do NOT modify files under C:\franl\.claude-agent-memory\. This directory is read-only for you.
- Do NOT commit to Git or push to any remote repository unless the task explicitly asks for it.
- If you cannot complete the task with the information provided, return a clear explanation
  of what additional information or context you need.
- Do NOT engage in open-ended exploration. Stay focused on the assigned task.
```

### 6.3 System Prompt Assembly

The final system prompt passed to `--system-prompt` is assembled as:

```
[DEFAULT_PREAMBLE]

[caller's system_prompt, if provided]
```

Example: If the primary agent calls `spawn_agent` with `system_prompt: "Return your analysis as a markdown list. Each finding should have a severity (high/medium/low)."`, the sub-agent receives:

```
You are a sub-agent performing a focused task on behalf of a primary Claude conversation.

Rules:
- Complete the assigned task and return your findings as text output.
- Be concise and structured. Prefer markdown formatting for readability.
- [... rest of default preamble ...]

Return your analysis as a markdown list. Each finding should have a severity (high/medium/low).
```

### 6.4 Directory Sandbox Behavior

Claude Code's directory sandbox is enforcement-level security provided by Claude Code's own infrastructure:

| Scenario | `working_directory` | `allow_memory_read` | `additional_dirs` | Sub-agent can access |
|----------|--------------------|--------------------|-------------------|---------------------|
| Minimal | `C:\franl\projects\foo` | false | none | Only `C:\franl\projects\foo\**` |
| With memory | `C:\franl\projects\foo` | true | none | `C:\franl\projects\foo\**` + `C:\franl\.claude-agent-memory\**` (read) |
| Multi-repo | `C:\franl\projects\foo` | false | `[C:\franl\projects\bar]` | `C:\franl\projects\foo\**` + `C:\franl\projects\bar7**` |
| Memory + multi-repo | `C:\franl\projects\foo` | true | `[C:\franl\projects\bar]` | All three directories |

**Important:** The sandbox blocks reads, not just writes. If `allow_memory_read` is `false`, the sub-agent cannot even `cat` a memory file — Claude Code will refuse the operation.

**Write protection for memory files** is preamble-based (compliance), not enforced by the sandbox. If `allow_memory_read` is `true`, the sub-agent could technically write to the memory directory. The preamble instructs against this. For additional hardening, the bridge could launch the subprocess with the memory directory mounted read-only at the OS level (platform-specific).

### 6.5 CLAUDE.md Recommendations

The file `C:\Users\flitt\.claude\CLAUDE.md` is loaded into every Claude Code invocation automatically (including sub-agents), independent of `--system-prompt`. It should be optimized for the sub-agent use case:

**Target size:** Under 500 tokens (~400 words).

**Should include:**
- OS environment (Windows 11 + Cygwin, shell behavior, pathname conventions)
- Available tools (compilers, package managers, utilities)
- Source code conventions (line width, comments, encoding, newlines)

**Should NOT include:**
- Credentials (API tokens, passwords — use environment variables instead)
- Interactive instructions ("confirm with the user")
- Service-specific instructions (Bluesky conventions, GitHub profile)
- Niche build instructions (GUI flags, specific project configs)

Recommended `CLAUDE.md` content:

```markdown
# OS Environment

- This is a Windows 11 system with Cygwin installed.
- Bash commands are executed by the Cygwin Bash shell.
- Most Linux commands are available: cd, cat, ls, grep, find, cp, mv, sed, awk, git, python, etc.
- To execute `rm`, use the full pathname `/bin/rm` (avoids a wrapper script's confirmation prompt).
- Cygwin symlinks for drive letters exist: /c -> /cygdrive/c, /d -> /cygdrive/d, etc.
  Native Windows apps cannot follow Cygwin symlinks.

## Pathname Conventions

- Cygwin apps: use forward slashes. Absolute paths start with /c/ (drive letter).
  Example: /c/franl/git/project/file.txt
- Native Windows apps: use backslashes, single-quoted to escape.
  Example: 'C:\franl\git\project\file.txt'
- If a pathname contains spaces or shell metacharacters, always single-quote it.

## Available Tools

- Compilers/runtimes: gcc, g++, go, rustc, cargo, python, node, npm, npx.
- Package managers: uv, uvx (Python), npm/npx (Node.js).
- Utilities: git, gh (GitHub CLI).
- Do not install additional tools without explicit task instructions to do so.

# Source Code Conventions

- Line width: under 100 columns.
- Use meaningful variable/loop names (not single characters).
- Newlines: UNIX-style (LF) for new files. Match existing convention when editing.
- Encoding: UTF-8 for new files. Match existing encoding when editing.
- Comments: write well-commented code. Aim for nearly as many comment lines as code lines.
  Comments should explain purpose and rationale, not restate what the code does.
  Place comments on the line above the code they reference.
- Prefer Python and Bash for scripts. Use PEP 723 metadata in Python scripts.
- Bash variables: UPPERCASE for globals, _UPPERCASE for function locals.
- When building executables, always use .exe extension (Windows).
```

### 6.6 Sub-Agent Memory Access Rules

| Layer | Access | Enforcement | Notes |
|-------|--------|-------------|-------|
| Layer 1 (Anthropic built-in) | None | Platform | `claude -p` does not receive built-in memory. Platform limitation. |
| Layer 2 (supplementary) | Read-only (optional) | Sandbox (read) + preamble (write) | Controlled by `allow_memory_read`. Default: false. |
| CLAUDE.md | Auto-loaded | None (automatic) | Loaded by Claude Code startup, cannot be suppressed. Keep credentials out. |

**Why no write access?** Allowing sub-agents to write to Layer 2 would break the single-writer model and reintroduce concurrent write problems. The primary agent is the sole writer. Sub-agents return findings in their text response; the primary agent decides what to persist.

---

## 7. Build and Deployment

### 7.1 Build the Bridge

```bash
# Clone the repo
cd C:\franl\git
git clone https://github.com/fpl9000/mcp-bridge

# Build (produces single static binary)
cd mcp-bridge
go build -o mcp-bridge.exe .

# Verify
./mcp-bridge.exe --version
```

No CGO, no external dependencies. The binary is self-contained.

Install the bridge with these Bash commands:

```bash
$ mkdir -p ~/.claude-agent-memory/bin
$ cp mcp-bridge.exe ~/.claude-agent-memory/bin
```

### 7.2 Claude Desktop Configuration

Edit Claude Desktop's MCP configuration file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **MacOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json` (no official support for Claude Desktop on Linux)

Add the bridge server entry:

```json
{
  "mcpServers": {
    "mcp-bridge": {
      "command": "C:\\franl\\.claude-agent-memory\\bin\\mcp-bridge\\mcp-bridge.exe",
      "args": ["--config", "C:\\franl\\.claude-agent-memory\\bridge-config.yaml"]
    }
  }
}
```

The Desktop App will launch the bridge as a subprocess on startup, communicating via stdio.

**Note:** The Filesystem extension does **not** appear in `claude_desktop_config.json` and should **not** be added there. It is a first-party Claude Desktop extension developed by Anthropic and distributed through Claude Desktop's built-in extensions gallery (Settings > Extensions). It is installed, enabled, and configured entirely through the Claude Desktop UI — not via the config JSON file. Claude Desktop manages its configuration for first-party extensions through a separate internal store. See the resolution of Open Question #6 for details.

### 7.3 Filesystem Extension Configuration

The Filesystem extension is enabled and configured via Claude Desktop's Extensions UI (Settings > Extensions > Filesystem > Configure). The allowed directories (e.g., `C:\franl`, `C:\temp`, `C:\apps`) are set there, not in `claude_desktop_config.json`.

The memory directory (`C:\franl\.claude-agent-memory`) is covered because it is a subdirectory of `C:\franl`, which is already an allowed directory. No additional configuration is needed.

### 7.4 Memory Directory Setup

Create the directory structure:

```bash
mkdir -p C:/franl/.claude-agent-memory/blocks
```

Create the bridge configuration file (`bridge-config.yaml`) with the schema defined in [Section 3.2](#32-configuration).

### 7.5 Initial Memory Seeding

The first time the memory system is used, Claude will find an empty memory directory (no `core.md`, no `index.md`). The skill instructions handle this: "If core.md does not exist, this is a first-run scenario."

However, it's better to pre-seed the files with initial content derived from existing knowledge. This avoids a cold-start problem where Claude's first session has no Layer 2 context.

**Seeding approach:**

1. Manually create `core.md` with basic identity and project information (copy from Layer 1 memory or from conversation history).
2. Create `index.md` with an empty table header:
   ```markdown
   # Index

   | Block | Summary | Updated |
   |-------|---------|---------|
   ```
3. Optionally create initial project blocks for active projects.
4. The episodic log will be created automatically on the first session.

Alternatively, ask Claude in an initial conversation to seed the memory from its Layer 1 knowledge: "Please create the initial core.md and index.md for the memory system, using what you know about me from your built-in memory."

### 7.6 Skill Installation

1. Create the `SKILL.md` file with the content from [Section 5.2](#52-skillmd-content).
2. Create a .zip file containing only `SKILL.md`:
   ```bash
   zip stateful-memory.zip SKILL.md
   ```
3. Upload via Claude Desktop > Settings > Capabilities > Add Skill.

### 7.7 CLAUDE.md Update

Replace the current `C:\Users\flitt\.claude\CLAUDE.md` with the lean sub-agent-optimized version described in [Section 6.5](#65-claudemd-recommendations) and the proposal. Move credentials to environment variables. Move service-specific instructions to `spawn_agent` system_prompt parameters.

---

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
| Unknown session_id | Valid path + content + invalid session | Error: "Unknown session_id" |
| Race detection → branch | Read file, external write, then safe_write_file | branch_created: true, path is branch file |
| No race → normal write | Read file, no external changes, then safe_write_file | branch_created: false, path is base file |

#### 8.1.1a safe_append_file Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Append to new file | Path to non-existent file + text | File created with text content |
| Append to existing file | Path to existing file + text | Text appended after existing content |
| Path outside memory dir | Path under `C:\temp\` | Error: "restricted to memory directory" |
| Path traversal attempt | Path with `..` escaping memory dir | Error: path validation rejects it |
| Empty text | Valid path + empty string | Success (no-op write, 0 bytes) |
| Parent dir creation | Path where parent dir doesn't exist | Parent directories created, file written |
| Unknown session_id | Valid path + text + invalid session | Error: "Unknown session_id" |
| Race detection → branch | Read file, external write, then safe_append_file | branch_created: true, branch contains base + appended text |

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

#### 8.1.5 memory_session_start Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Basic session creation | No params | Returns unique session_id (8 chars), started_at timestamp |
| Session ID uniqueness | Create 100 sessions | All IDs are distinct |
| Session ID format | Create session | ID matches `ses-[0-9a-f]{4}` pattern |
| Max sessions eviction | Create max_sessions + 1 | Oldest session evicted, newest created successfully |
| Branches exist flag (no branches) | Clean memory dir | Returns `branches_exist: false` |
| Branches exist flag (with branches) | Create a branch file in memory dir | Returns `branches_exist: true` |

#### 8.1.6 safe_read_file Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Read existing file | Valid path + session_id | Returns content, records ModTime in session tracker |
| Read non-existent file | Path to missing file | Error: "File does not exist" |
| Path outside memory dir | Path under `C:\temp\` | Error: "restricted to memory directory" |
| Unknown session_id | Valid path + invalid session_id | Error: "Unknown session_id" |
| Read file with no branches | File has no branch files | `has_branches: false`, empty branches array |
| Read file with branches | File has 2 branch files | `has_branches: true`, branches array has 2 entries with content |
| Branch chronological order | File has branches from different times | Branches sorted by creation timestamp |
| ModTime tracking | Read file, check session tracker | Tracker has correct ModTime for the file |
| Path traversal attempt | Path with `..` escaping memory dir | Error: path validation rejects it |

#### 8.1.7 Branching Tests

| Test Case | Setup | Expected Behavior |
|-----------|-------|-------------------|
| No race (normal write) | Session reads file, no other writes, session writes | Write succeeds to base file, `branch_created: false` |
| Race detected → branch created | Session A reads, Session B writes, Session A writes | Session A's write goes to branch file, `branch_created: true` |
| Branch naming format | Trigger a branch | Branch filename matches `<stem>.branch-<timestamp>-<hex4>.<ext>` |
| Branch creation timestamp | Trigger a branch | Timestamp in filename matches current time |
| Append with race → branch | Session A reads, Session B writes, Session A appends | Append creates branch with base content + appended text |
| Branching disabled | Set `branching.enabled: false`, trigger race | Last-writer-wins behavior, `branch_created: false` |
| First write (no prior read) | Session writes to file it never read | No race possible, write to base file |
| New file creation | Session writes to non-existent path | File created normally, no branching |
| Multiple branches same file | Three sessions race on same file | Two branch files created alongside unchanged base |

#### 8.1.8 Job Lifecycle Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Cleanup goroutine runs | After job_expiry_seconds, uncollected jobs are removed |
| Graceful shutdown | All active subprocesses are killed, bridge exits cleanly |
| Job ID uniqueness | 1000 sequential job IDs are all unique |
| Mixed job sources | Jobs from both spawn_agent and run_command coexist in job manager |

#### 8.1.9 MCP Integration Tests

These tests verify the bridge works correctly as an MCP server. Use the `mcp-go` SDK's test utilities or send raw JSON-RPC messages over a pipe.

| Test Case | Expected Behavior |
|-----------|-------------------|
| MCP initialization handshake | Bridge responds with capabilities and tool list |
| Tool listing | Returns memory_session_start, safe_read_file, safe_write_file, safe_append_file, spawn_agent, check_agent, run_command |
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
4. Verify (via bridge log) that Claude called `memory_session_start` first.
5. Verify that Claude read `core.md` and `index.md` via `safe_read_file` (not `Filesystem:read_file`).
6. Verify Claude's response incorporates content from the memory files.

**Pass criteria:** Claude calls `memory_session_start` first, reads both files via `safe_read_file` before its first response, and integrates the content naturally.

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
1. Monitor the bridge log and Claude Desktop's tool usage during a memory session.
2. Verify that `memory_session_start` was called before any memory reads or writes.
3. Verify that all reads of memory files use `Bridge:safe_read_file` (not `Filesystem:read_file`).
4. Verify that all writes to memory files use `Bridge:safe_write_file` or `Bridge:safe_append_file`.
5. Verify that all memory tool calls include a valid `session_id`.
6. Verify that no memory operations use `Filesystem:read_file`, `Filesystem:write_file`, `Filesystem:edit_file`, `bash_tool`, `create_file`, or `str_replace`.

**Pass criteria:** All memory operations go through the bridge's session-tracked tools. No Filesystem extension or cloud VM tools used for memory files.

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
| AC1 | Bridge starts and registers all 7 tools with Claude Desktop | MCP integration test |
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
| AC14 | No memory operations use cloud VM tools or Filesystem extension | Skill test 8.2.6 |
| AC15 | memory_session_start returns unique session IDs and branches_exist flag | memory_session_start tests 8.1.5 |
| AC16 | safe_read_file returns content with branch annotations when branches exist | safe_read_file tests 8.1.6 |
| AC17 | safe_write_file detects races and creates branches instead of overwriting | Branching tests 8.1.7 |
| AC18 | Memory skill calls memory_session_start before any memory reads/writes | Skill test 8.2.1 |

---

## 10. References

1. **Proposal document:** [stateful-agent-proposal.md](../../docs/stateful-agent-proposal.md) — Requirements, architecture evaluations, 27 open question resolutions, rationale for all major decisions.
2. **Previous skill design (superseded):** [agent-memory-design.md](../../docs/agent-memory-design.md) — Earlier design for a standalone skill without MCP bridge. Concepts carried forward; implementation approach replaced.
3. **Tim Kellogg's Strix architecture:** [Memory Architecture for a Synthetic Being](https://timkellogg.me/blog/2025/12/30/memory-arch) — Three-tier hierarchical memory model that inspired our core/index/blocks structure.
4. **claude_life_assistant:** [GitHub](https://github.com/lout33/claude_life_assistant) — Luis Fernando's minimal stateful agent demonstrating the core concept.
5. **mark3labs/mcp-go:** [GitHub](https://github.com/mark3labs/mcp-go) — Go SDK for the Model Context Protocol.
6. **MCP specification:** [modelcontextprotocol.io](https://modelcontextprotocol.io) — Protocol specification for tool registration, stdio transport, and Streamable HTTP transport.
7. **Claude Code system prompts:** [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts) — Community-maintained extraction of Claude Code's default system prompt fragments.
8. **Anthropic Filesystem extension:** [@modelcontextprotocol/server-filesystem](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem) — Official MCP server providing 11 filesystem tools.

---

## 11. Open Questions

1. **Race condition with memory writes** — MCP bridge tools `safe_write_file` and `safe_append_file` serialize file writes using a Go mutex, however this only prevents torn writes. It doesn't solve the problem where concurrent conversations race via read-modify-write.  For instance, if conversation A reads `core.md` and conversation B reads `core.md`, then after each is modified in-context, whichever conversation writes `core.md` last overwrites the other's changes.  Would it help to add a `safe_edit_file` tool that uses the same mutex?

   - *Resolution (v1):* We initially decided that last-writer-wins was the accepted concurrency model for v1. A `safe_edit_file` tool would not solve the race because it is about stale reads, not unprotected writes.

   - *Resolution (v2 — current):* The last-writer-wins model has been replaced with a **session-tracked branching** system. Two new tools (`memory_session_start` and `safe_read_file`) enable the bridge to track which version of a file each conversation has seen. When `safe_write_file` or `safe_append_file` detects that a file was modified by another conversation since the current session last read it, the write is redirected to a "branch" file (e.g., `core.branch-20260313T1423-a1b2.md`) instead of overwriting. The original file is left unmodified. Branch files are later reconciled via a **semantic merge** process (not a textual merge) performed by a sub-agent. This approach preserves all data from concurrent conversations at the cost of deferred merge complexity. See [Chapter 3, Section 3.11](stateful-agent-design-chapter3.md#311-write-mutex-and-session-tracking) for session tracking, [Chapter 3, Section 3.12](stateful-agent-design-chapter3.md#312-branching) for branching and merge details, and [Chapter 4, Section 4.10](stateful-agent-design-chapter4.md#410-branching-and-merge) for the memory system perspective.

2. **Need a tool to run commands** — Section 2.3, "What the Bridge Does NOT Do", says the bridge will not have a `run_command` tool, but using a sub-agent to run a simple `curl` command or Bash script is a waste of valuable tokens (that cost money).  Let's change the design to include implmenting the `run_command` tool.

   - *Resolution:* The `run_command` tool has been added to the bridge as a first-class tool (see [Chapter 3, Section 3.6](stateful-agent-design-chapter3.md#36-tool-run_command)). It executes shell commands via Cygwin bash (`C:\apps\cygwin\bin\bash.exe -c "<command>"`) with no LLM inference involved, making it dramatically cheaper than `spawn_agent` for simple operations. Key design decisions: (a) uses the same hybrid sync/async model as `spawn_agent` via the shared async executor ([Chapter 3, Section 3.13](stateful-agent-design-chapter3.md#313-async-executor)), so long-running commands like recursive `grep` are handled correctly; (b) default output limit is 50 KB (~12,500 tokens) to avoid context window bloat; (c) middle-truncation preserves both head and tail of output; (d) no command restrictions for v1 (primary agent already has equivalent access via `spawn_agent`); (e) all commands are logged for auditability. Section 2.3 has been updated to remove `run_command` from the "does NOT do" list. The bridge now provides seven tools total.

3. **Bridge configuration question** — What exactly are the semantics of bridge configuration parameter `job_expiry_seconds`?

   - *Resolution:* `job_expiry_seconds` (default: 600) defines how long the bridge's job lifecycle manager will retain a completed-but-uncollected async job before discarding it. The expiry clock starts from `job.StartedAt` (not from when the process finished). When the cleanup goroutine's 30-second sweep detects that `now > job.StartedAt + job_expiry_seconds`, it kills the process if it is still running, logs a warning, and removes the job from the map.

     The parameter exists to prevent memory leaks from orphaned jobs — async jobs whose `job_id` was returned to the primary agent but never retrieved via `check_agent`. This can happen if the user closes Claude Desktop mid-conversation, the agent forgets to poll, or the agent hits a context limit and loses track of the job_id. Without expiry, those jobs would accumulate indefinitely in the job manager, holding process handles and output buffers (up to 50 KB each for `run_command`, up to the token limit for `spawn_agent`).

     The default of 600 seconds (10 minutes) is intentionally generous. In normal operation, the primary agent polls `check_agent` within seconds or minutes of receiving a `job_id`. The 10-minute window provides ample time for the agent to return to polling even after a distraction or brief interruption, while still ensuring the bridge doesn't accumulate stale jobs across a long Claude Desktop session. No change to the design or default value is needed.

4. **UNIX Signals on Windows** — Chapter 3, Section 3.17, "Graceful Shutdown", mentions SIGINT and SIGTERM, but do those signals exist on Windows?  How does the Go runtime deal with UNIX signals on Windows?

   - *Resolution:* SIGTERM does not exist as a native inter-process signal on Windows — it is only a software-level constant defined within the Windows CRT and cannot be sent from one external process to another. SIGINT exists in a limited form (Ctrl+C in a console window triggers a `CTRL_C_EVENT` that Go maps to `syscall.SIGINT`), but since the bridge runs as a background stdio subprocess with no attached console, it is not reliably deliverable either. Go's `os/signal` package maps these console events to signal constants, but that is of no help for a headless subprocess.

     The correct shutdown mechanism for an MCP stdio server on Windows is **stdin EOF detection**. When Claude Desktop exits or kills the bridge, it closes the stdin pipe. The `mcp-go` SDK's stdio read loop detects this EOF and exits naturally, giving the bridge an opportunity to clean up. Chapter 3, Section 3.17 has been updated accordingly: UNIX signal handling has been removed, the shutdown trigger is now stdin EOF, and subprocess termination uses `Process.Kill()` (which calls Windows `TerminateProcess` directly) rather than a SIGTERM-then-SIGKILL escalation sequence.

5. **Read-only mounts** — In section 6.4, "Directory Sandbox Behavior", the design states "For additional hardening, the bridge could launch the subprocess with the memory directory mounted read-only at the OS level (platform-specific)."  Is this possible on Windows 11?

   - *Resolution:* OS-level read-only mounting of a directory into a specific subprocess's namespace is not supported on Windows 11 without disproportionate complexity. The options considered were: (a) **ACL manipulation** — temporarily removing write permissions on the memory directory before launching the subprocess and restoring them after; this is globally visible (affects all processes, not just the sub-agent), introduces a TOCTOU race window, and is fragile if the bridge crashes before restoring permissions; (b) **Job Objects with restricted tokens** — Windows Job Objects can constrain CPU and memory but offer no directory-level read/write access control; (c) **App Containers / Win32 app isolation** — available since Windows 10 1903, but require setting up security capabilities and are far too complex to invoke from a Go binary for this use case. The design already provides the correct level of protection via Claude Code's own directory sandbox: when `allow_memory_read` is `false`, the sandbox blocks all access to the memory directory entirely; when `allow_memory_read` is `true`, the preamble-based write prohibition is the appropriate mechanism. No OS-level read-only hardening will be added in v1.

6. **Filesystem extension question** — In section 7.2, "Claude Desktop Configuration", the design says the existing Filesystem extension entry should already be present in `%APPDATA%\Claude\claude_desktop_config.json`, but on my Windows 11 machine that file contains only the below contents. Could the Filesystem extension be configured some other way? This is not really a problem, given that I know the Filesystem extension works in Claude Desktop, but I'm curious why it doesn't appear in that JSON file.

   ```
   {
     "globalShortcut": "Alt+Ctrl+Enter",
     "preferences": {
       "coworkScheduledTasksEnabled": false,
       "sidebarMode": "chat"
     }
   }
   ```

   - *Resolution:* The Filesystem extension does not appear in `claude_desktop_config.json` because it is not an MCP server configured by the user — it is a **first-party Claude Desktop extension** developed and distributed by Anthropic through Claude Desktop's built-in extensions gallery (Settings > Extensions). First-party extensions are installed, enabled, and configured entirely through the Claude Desktop UI. Claude Desktop manages their configuration through a separate internal store, not through `claude_desktop_config.json`.

     The `claude_desktop_config.json` file is only for **third-party MCP servers** that the user manually registers — i.e., servers that Claude Desktop does not know about natively and must be told how to launch. The `mcp-bridge` server we are building belongs in that file. The Filesystem extension does not.

     The screenshot of the Filesystem extension's detail screen in Claude Desktop confirms this: it shows an "Enabled" toggle and a "Configure" button (for setting allowed directories), consistent with a UI-managed extension. It also shows "Developed by Anthropic" and notes that it uses `@modelcontextprotocol/server-filesystem` under the hood — Anthropic has bundled the npm package but manages its lifecycle internally.

     **Impact on the design:** Section 7.2 has been corrected to remove the incorrect note and the example JSON that showed a `"filesystem"` entry in `claude_desktop_config.json`. Section 7.3 has been updated to describe configuring allowed directories via the UI instead of via command-line arguments. No `"filesystem"` entry should be added to `claude_desktop_config.json`.

7. **Claude Code CLI for implemenation** — Once this design stabilizes, do you see any issues with using Claude Code CLI with Sonnet 4.6 to implement it?

   - *Resolution:* Claude Code CLI with Claude Sonnet 4.6 is an appropriate choice for implementing the MCP bridge. Sonnet is Anthropic's recommended model for Claude Code and is well-suited to this kind of work: translating a detailed design document into Go code within a well-defined module structure. Note that `spawn_agent` and other bridge tools are unavailable during the bridge's own implementation — Claude Code CLI must be used directly for that phase. Once the bridge is built and deployed, it becomes available for all subsequent work.

8. **Slash commands** — Claude Code CLI has a slash command corresponding to each loaded skill.  Does the Claude Desktop also have these?  If so, can we use them to trigger memory writes?

   - *Resolution:* Slash commands are a Claude Code CLI terminal interface feature — the user types `/skill-name` in the interactive CLI session to explicitly invoke a skill. Claude Desktop has no equivalent mechanism; there is no input field where a user would type a slash command. Skills uploaded to Claude Desktop are invoked exclusively through the description-driven auto-invocation mechanism: Claude decides when to load a skill based on whether its description matches the current conversation context.

     In any case, slash commands would not be useful for triggering memory writes. A memory write requires Claude to call a tool (`Bridge:safe_write_file` or `Bridge:safe_append_file`), which happens in response to conversational context — not in response to a user-typed command. The memory skill's compliance-based instructions already cover when to write: on significant new information, on project status changes, at session end, etc. There is no gap here that slash commands would fill.

9. **Terms of Service question** — Given the news reported by PC World at https://www.pcworld.com/article/3068842/whats-behind-the-openclaw-ban-wave.html about Anthropic banning some automated use of Claude Code CLI, do Anthropic's consumer terms of service at https://www.anthropic.com/legal/consumer-terms or their Acceptable Use Policy at https://www.anthropic.com/legal/aup prevent using Claude Code CLI as a sub-agent?

   - *Resolution:* The design is compliant with Anthropic's Terms of Service. The `spawn_agent` tool invokes the official `claude -p` CLI binary as a subprocess — it does not extract, transfer, or reuse OAuth tokens, and it does not make direct Anthropic API calls. The bridge never touches authentication at all; the Claude Code CLI manages its own auth lifecycle internally. The Consumer ToS prohibition on automated access contains an explicit exception for use cases "where we otherwise explicitly permit it," and Anthropic explicitly permits scripted and automated use of the `claude` CLI — their official documentation demonstrates piping, scripting, and CI/CD pipelines as intended patterns.

     The account bans reported in January–February 2026 targeted a specific and narrow behavior: third-party harnesses (OpenCode, OpenClaw, Cline, Roo Code, etc.) that intercepted Claude's OAuth authentication flow, extracted the subscriber's OAuth token, and used it to make direct Anthropic API calls while forging the HTTP headers that the real Claude Code CLI sends — effectively spoofing the official client to gain flat-rate subscription access at API-level volume. Anthropic's formal prohibition, published February 17–19, 2026, reads: *"Using OAuth tokens obtained through Claude Free, Pro, or Max accounts in any other product, tool, or service — including the Agent SDK — is not permitted."* This design does none of that. The critical distinction is: **calling `claude -p` (the real CLI binary) = allowed; extracting OAuth tokens to use in a third-party API client = banned.**

     The "ordinary, individual usage" language added to Anthropic's February 2026 documentation refers to preventing subscription arbitrage at scale (e.g., multi-tenant bots running overnight autonomous swarms on a flat-rate plan, which would cost $1,000+/month at API prices). It does not apply to a single developer running personal project work from their own machine — which is the intended use case for a Max subscription and the exact scenario this design targets.

10. **Shell invocation to minimize quoting issues** — Section 3.6, "Tool: run_command", says that commands will be executed by Bash as follows: `C:\apps\cygwin\bin\bash.exe -c "<command>"`, but that can cause problems when `<command>` contains complex combinations of single and double quotes. Can the MCP server spawn Bash using `bash -s` so it reads the `<command>` from stdin, which simplifies the quoting issues in the command?

    - *Resolution:* Keep the `-c` approach. The question was based on a mistaken assumption: that the `bash -c <command>` invocation is itself parsed by a shell, which would require the command string to be shell-escaped. In fact, Go's `exec.Command` bypasses any intermediate shell entirely — it calls `CreateProcess` (on Windows) directly, passing the command string as a single, literal argument to Bash's `-c` flag. No shell metacharacter expansion occurs at the Go level; the raw string is delivered to Bash as-is.

      The genuine quoting challenge — complex single/double quote combinations in the command string — is a property of Bash parsing the command, not of how the string is delivered to Bash. Whether Bash receives the string via `-c` or via stdin (`-s`), it parses the same shell syntax identically. Switching to `bash -s` would not eliminate this challenge.

      The `-s` approach would have one narrow, genuine advantage: avoiding the Windows `CreateProcess` command-line length limit (~32 KB). For the command types `run_command` is intended for (`grep`, `curl`, `git`, `find`, short pipelines, etc.), this limit will never be approached in practice.

      Accordingly, the implementation uses `exec.Command(shellPath, append(shellArgs, params.Command)...)` as specified in [Chapter 3, Section 3.6](stateful-agent-design-chapter3.md#36-tool-run_command), where `shellArgs` defaults to `["-c"]`. This is correct, sufficient, and requires no change.

11. **Multiple home directories** — Sections 3.4, "Tool: spawn_agent", and 3.6, "Tool: run_command", say that the default value of the working directory parameter is my home directory, but there's an ambiguity: my Windows home directory is `C:\Users\flitt\` and my Cygwin home directory is `C:\franl\`.  Is there any issue with changing those sections to explicity specify `C:\franl\` as the default working directory for commands `spawn_agent` and `run_command`?

    - *Resolution:* No issue. `C:\franl\` is the correct default and `os.UserHomeDir()` would be wrong here for two reasons: (a) on Windows it returns `C:\Users\flitt\` (from `USERPROFILE`), not the Cygwin home; and (b) both `run_command` (which runs via Cygwin bash) and `spawn_agent` (which spawns a sub-agent doing real work) expect to start in the Cygwin-rooted environment where all projects and tools live. Using `C:\Users\flitt\` as the default would be consistently wrong.

      Rather than hardcoding `C:\franl\` as a compile-time constant, the design has been updated to add a `default_working_directory` field to the bridge config (see [Chapter 3, Section 3.2](stateful-agent-design-chapter3.md#32-configuration)), defaulting to `C:\franl\`. This keeps it configurable without a recompile if the filesystem layout ever changes, and is consistent with how the rest of the config handles machine-specific paths. Sections 3.4 and 3.6 have been updated to reference `config.DefaultWorkingDirectory` instead of `os.UserHomeDir()`.

12. **Claude.ai SKILL.md contents needed** — [Chapter 9, Future Enhancements, Section 9.5](stateful-agent-design-chapter9.md#95-github-relay-claudeai-to-local-bridge-communication), "GitHub Relay: Claude.ai to Local Bridge Communication", needs to include the contents of the skill, including the `SKILL.md` file and the names of any scripts.

    - *Resolution:* The relay functionality is split across two skills to maintain a clean separation between the transport protocol and the operational semantics:

      **(a) GitHub skill** (`ai-skills/github/`) — Gains three new scripts (`relay_common.py`, `relay_send.py`, `relay_receive.py`) and a new SKILL.md section covering the relay *transport protocol*: message format, HMAC signing and verification, polling strategy, and error handling. The transport layer is operation-agnostic — it treats the `operation` and `arguments` fields as opaque payloads.

      **(b) AI Messaging skill** (`ai-skills/ai-messaging/`) — A new skill containing only a `SKILL.md` file (no scripts). Covers the *semantic layer*: the three relay operations (`memory_query`, `shell_command`, `claude_prompt`), when to choose each one, what arguments they expect, and how to interpret results. This skill depends on the github skill's relay scripts for actual message transport. The dependency is explicit and one-directional (ai-messaging → github, never the reverse).

      This separation avoids mixing two distinct concerns in a single skill: the mechanical details of how messages are signed, delivered, and verified (transport) vs. the domain-specific knowledge of what operations are available and when to use each one (semantics). It also prevents the github skill's description from needing to serve two very different trigger patterns ("create a PR" vs. "read my local memory"), which could degrade auto-invocation accuracy.

      The `RELAY_HMAC_SECRET` environment variable value is stored in the user's Claude.ai personal instructions (the `<userPreferences>` block), alongside the existing `GITHUB_TOKEN` and Bluesky credentials. These instructions are shared by both Claude Desktop and Claude.ai, so both environments have access to the secret.

      See [Chapter 9, Future Enhancements, Section 9.5.10](stateful-agent-design-chapter9.md#9510-relay-script-inventory) for the script specifications, [Section 9.5.11](stateful-agent-design-chapter9.md#1511-github-skill-relay-transport-additions) for the github skill SKILL.md additions, and [Section 9.5.12](stateful-agent-design-chapter9.md#9512-ai-messaging-skill) for the ai-messaging skill's complete SKILL.md.

13. **Memory search tool** — Do we need a tool to search memory files?  The Filesystem extension's search tool does not respect the Go mutex and cannot annotate branched memory files the way `safe_read_file` does.

    - *Resolution:* Deferred to v1.1. The mutex bypass is a non-issue for search specifically: the mutex exists to make the `Stat()` + `Read()` pair atomic for session-tracking purposes, but a search is a read-only informational query that doesn't establish a baseline for a future write. If Claude finds relevant content via search, it will then call `safe_read_file` on the specific file, which goes through the mutex and registers the read in the session tracker. The search result is just a pointer to the right file; the session-tracked read happens afterward.

      The branch-awareness gap is more substantive — `Filesystem:search_files` would return hits on branch files (e.g., `core.branch-20260313T1423-a1b2.md`) without semantic context about what a branch file is. The v1 workaround is acceptable: Claude can use `Filesystem:search_files` on the memory directory as a best-effort fallback, and the skill instructions should include guidance such as "if search returns a hit on a `.branch-*` file, call `safe_read_file` on the corresponding base file instead." This covers the branch-awareness gap without adding a new bridge tool.

      When a `safe_search_file` tool is implemented in v1.1, it should: (a) accept a search string and `session_id`; (b) search across all base files *and* their branches in the memory directory; (c) return results annotated with whether each hit is from a base file or a branch; and (d) *not* register reads in the session tracker (search results are informational, not baselines for writes — Claude will call `safe_read_file` on specific files afterward). It should acquire the mutex only briefly to get a consistent snapshot of the file list, then release it before performing text matching (which could be slow on many files and should not block writes).

14. **Memory edit tool** — Some memory blocks are written in their entirety using `safe_write_file`. Is there value in having a `safe_edit_file` that enables sub-string replacement within a memory file?

    - *Resolution:* No `safe_edit_file` for v1. The rationale is that surgical edits interact poorly with the branching system and provide insufficient benefit given expected file sizes.

      The core problem is branching semantics. When `safe_write_file` detects a race, it redirects the complete file content to a branch — the branch is a self-contained, independently readable document. If `safe_edit_file` detected a race, it would face an awkward choice: (a) apply the edit to the *stale* version Claude has in context and write the full result to the branch (silently rebasing onto an outdated snapshot), or (b) store the edit operation itself in a structured format and have the merge sub-agent apply it (adding complexity to the merge process). Neither is clean.

      There is also a correctness issue. Claude formulates an edit by identifying a substring based on content it read earlier via `safe_read_file`. If another conversation has modified the file since that read, the substring might no longer exist, or might exist in a different context. `safe_write_file` sidesteps this entirely: Claude produces a complete, coherent document representing its intended state, and the bridge either accepts it (no race) or branches it (race). The merge sub-agent then reconciles two complete documents, which is a well-defined semantic task.

      The one concern is output token cost for large blocks. If a block grows to 5,000 tokens and Claude only needs to change one paragraph, full rewrite costs ~5,000 output tokens. But this is self-correcting: the design already prescribes size budgets for files (`core.md` at 500–1,000 tokens, blocks at manageable sizes), and blocks that grow too large should be split. If that discipline is maintained, full-file replacement remains cheap. This can be revisited if memory files grow larger than anticipated in practice.

15. **Error in section 4.1** — Section 4.1, "Two-layer Memory Model", has an error in the "Update mechanism" row of the table. That row shows this text in the "Layer 2 (Supplementary)" column: "Direct via Filesystem:write_file, edit_file, Bridge:append_file", but the Filesystem extension's tools are not used to access Layer 2 memory files.

    - *Resolution:* Fixed. The text in section 4.1's "Update mechanism" row for "Layer 2 (Supplementary)" has been corrected from "Direct via Filesystem:write_file, edit_file, Bridge:append_file" to "Direct via Bridge:safe_write_file, safe_append_file". The original text was written before the session-tracked branching system (OQ#1 v2 resolution), which moved all memory file operations to the bridge's safe tools. The Filesystem extension tools (`write_file`, `edit_file`) are not used for memory files because they bypass the write mutex and session tracking. The reference to `edit_file` has also been removed, consistent with the OQ#14 resolution (no `safe_edit_file` for v1).

---

## 12. Appendix: mark3labs/mcp-go SDK Reference

This appendix documents the subset of the `mark3labs/mcp-go` SDK used by the MCP Bridge Server. All content is drawn directly from the library source and README. It is included here so that the implementer (Claude Sonnet running in Claude Code CLI) has an accurate, targeted reference and does not need to rely on training data, which may reflect an earlier API version.

**Repository:** https://github.com/mark3labs/mcp-go<br/>
**Import paths:** `github.com/mark3labs/mcp-go/mcp` and `github.com/mark3labs/mcp-go/server`

### 12.1 Installation

```bash
go get github.com/mark3labs/mcp-go
```

The `go.mod` file will gain a `require` line like:

```
require github.com/mark3labs/mcp-go v0.x.x
```

No CGO is required. The library is pure Go.

### 12.2 Minimal Complete Example

The following is a complete, working MCP server with one tool, demonstrating the full pattern the bridge uses. Read this first — the subsequent sections break it down piece by piece.

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/mark3labs/mcp-go/mcp"
    "github.com/mark3labs/mcp-go/server"
)

func main() {
    // Create the MCP server.
    //   - "mcp-bridge" is the server name reported during MCP initialization.
    //   - "1.0.0" is the version string.
    //   - WithToolCapabilities(false): advertises tool support; false means the
    //     tool list does NOT change at runtime (no dynamic tool registration
    //     after startup). The bridge registers all tools once at startup.
    //   - WithRecovery(): adds middleware that catches panics in tool handlers
    //     and returns them as MCP tool errors instead of crashing the server.
    s := server.NewMCPServer(
        "mcp-bridge",
        "1.0.0",
        server.WithToolCapabilities(false),
        server.WithRecovery(),
    )

    // Define a tool with one required string parameter.
    tool := mcp.NewTool("hello_world",
        mcp.WithDescription("Say hello to someone"),
        mcp.WithString("name",
            mcp.Required(),
            mcp.Description("Name of the person to greet"),
        ),
    )

    // Register the tool with its handler function.
    s.AddTool(tool, helloHandler)

    // Start the stdio server. This function:
    //   - Reads JSON-RPC messages from os.Stdin (one per line).
    //   - Writes JSON-RPC responses to os.Stdout.
    //   - Blocks until stdin is closed (EOF) or SIGTERM/SIGINT is received.
    //     On Windows, SIGTERM/SIGINT are not reliably deliverable from external
    //     processes (see Section 3.14), but stdin EOF works correctly.
    //   - Returns nil on clean EOF shutdown, non-nil error on I/O failure.
    //
    // CRITICAL: Do NOT write anything to os.Stdout before or during ServeStdio.
    // The MCP protocol uses stdout exclusively for JSON-RPC messages. Any stray
    // write (e.g., fmt.Println, log.Println with the default logger) will corrupt
    // the protocol stream. Use a log file (see Section 3.12) for all output.
    if err := server.ServeStdio(s); err != nil {
        fmt.Fprintf(os.Stderr, "ServeStdio error: %v\n", err)
    }

    // ServeStdio has returned (stdin EOF). Perform graceful shutdown here:
    // kill active subprocesses, flush logs, etc. (see Section 3.14).
}

// helloHandler is a tool handler. Its signature is fixed by the SDK.
//
// Return convention (critical — read this carefully):
//   - Tool execution errors (bad input, operation failed, etc.) MUST be returned
//     as *mcp.CallToolResult with IsError=true, using mcp.NewToolResultError or
//     similar. Return nil Go error in this case.
//   - Return a non-nil Go error ONLY for unexpected infrastructure failures where
//     the handler cannot produce any meaningful result at all. The SDK converts
//     a non-nil Go error into an MCP protocol-level error response, which Claude
//     cannot see or self-correct from.
func helloHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    // RequireString extracts a required string argument. Returns an error if
    // the argument is absent or not a string.
    name, err := request.RequireString("name")
    if err != nil {
        // Tool-level error: return as CallToolResult, not as Go error.
        return mcp.NewToolResultError(err.Error()), nil
    }

    return mcp.NewToolResultText(fmt.Sprintf("Hello, %s!", name)), nil
}
```

### 12.3 Tool Definition

Tools are created with `mcp.NewTool` using a variadic list of `ToolOption` functions:

```go
// NewTool creates a tool with an object-type JSON Schema input schema.
// The name must match exactly the name used in s.AddTool.
func NewTool(name string, opts ...ToolOption) Tool
```

Example:

```go
tool := mcp.NewTool("safe_write_file",
    mcp.WithDescription("Atomically write content to a memory file."),
    mcp.WithString("path",
        mcp.Required(),
        mcp.Description("Absolute path to the file (must be within memory directory)"),
    ),
    mcp.WithString("content",
        mcp.Required(),
        mcp.Description("Complete file content to write"),
    ),
)
```

### 12.4 Parameter Declarations

Each parameter is declared with a typed `With*` `ToolOption` function. The parameter name (first argument) must match the key string used in handler extraction calls (Section 12.6).

**String parameters:**

```go
mcp.WithString("param_name",
    mcp.Required(),                    // Marks the parameter required in the JSON Schema
    mcp.Description("What it does"),   // Human-readable parameter description
    mcp.DefaultString("default_val"),  // Default value when parameter is omitted
    mcp.Enum("val1", "val2"),          // Restrict to enumerated string values
    mcp.MinLength(1),                  // Minimum string length
    mcp.MaxLength(255),                // Maximum string length
    mcp.Pattern("^[a-z]+$"),           // Regex the value must match
)
```

**Numeric parameters:**

```go
// mcp-go has no WithInteger — all numeric parameters use WithNumber (JSON type "number").
// Use GetInt / RequireInt in the handler to receive an int; the SDK handles
// the float64 → int conversion automatically.
mcp.WithNumber("timeout_seconds",
    mcp.Description("Timeout in seconds"),
    mcp.Min(1),    // Minimum value (float64)
    mcp.Max(300),  // Maximum value (float64)
)
```

**Boolean parameters:**

```go
mcp.WithBoolean("allow_memory_read",
    mcp.Description("Grant read access to the memory directory"),
    mcp.DefaultBool(false),
)
```

**Array-of-strings parameters:**

```go
mcp.WithArray("additional_dirs",
    mcp.Description("Extra directories to grant access via --add-dir"),
    mcp.WithStringItems(),  // Declares array elements as strings
)
```

**`PropertyOption` functions** (used inside `With*` parameter declarations):

| Function | Purpose |
|----------|---------|
| `mcp.Required()` | Adds the parameter name to the tool's `required` list |
| `mcp.Description(s)` | Sets the parameter's description |
| `mcp.DefaultString(s)` | Default value for string parameters |
| `mcp.DefaultBool(b)` | Default value for boolean parameters |
| `mcp.Enum(vals...)` | Restricts a string parameter to enumerated values |
| `mcp.MinLength(n)` | Minimum length for string parameters |
| `mcp.MaxLength(n)` | Maximum length for string parameters |
| `mcp.Pattern(re)` | Regex constraint for string parameters |
| `mcp.Min(f)` | Minimum value for numeric parameters |
| `mcp.Max(f)` | Maximum value for numeric parameters |
| `mcp.WithStringItems()` | Constrains array items to type string |

### 12.5 Tool Registration

```go
// AddTool registers a tool and its handler. Must be called before ServeStdio.
// Registering two tools with the same name silently overwrites the first.
s.AddTool(tool, handlerFunc)

// Handler signature — must match exactly:
func handlerName(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error)

// Anonymous function form (equally valid):
s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    // ...
    return mcp.NewToolResultText("result"), nil
})
```

### 12.6 Argument Extraction

`mcp.CallToolRequest` provides typed accessor methods. There are two patterns:

- **`Require*`** — returns `(T, error)`; the error is non-nil if the argument is absent or has the wrong type. Use for parameters declared `mcp.Required()`.
- **`Get*`** — returns `T`; returns a caller-supplied default if the argument is absent. Use for optional parameters.

```go
// String
str, err := request.RequireString("key")        // (string, error)
str      := request.GetString("key", "default") // string

// Integer  (JSON numbers are float64; SDK auto-converts)
n,   err := request.RequireInt("key")            // (int, error)
n        := request.GetInt("key", 0)             // int

// Float64
f,   err := request.RequireFloat("key")          // (float64, error)
f        := request.GetFloat("key", 0.0)         // float64

// Boolean
b,   err := request.RequireBool("key")           // (bool, error)
b        := request.GetBool("key", false)        // bool

// String slice  (for WithArray + WithStringItems parameters)
ss,  err := request.RequireStringSlice("key")    // ([]string, error)
ss       := request.GetStringSlice("key", nil)   // []string

// Escape hatch: raw map access (avoid if typed accessors suffice)
args := request.GetArguments() // map[string]any
```

### 12.7 Result Constructors

All tool handlers return `*mcp.CallToolResult`. The bridge uses these constructors:

```go
// Successful result containing a plain text string.
// Use this for all successful tool outputs. The bridge returns JSON-encoded
// strings (e.g., marshaled structs) as the text argument.
mcp.NewToolResultText(text string) *mcp.CallToolResult

// Error result — sets IsError: true in the MCP response.
// Claude sees this as a tool error and can self-correct.
// Use for all tool-level failures (invalid input, operation failed, etc.).
mcp.NewToolResultError(text string) *mcp.CallToolResult

// Error result, appending ": <err.Error()>" to the message text.
// Equivalent to NewToolResultError(fmt.Sprintf("%s: %v", text, err)).
mcp.NewToolResultErrorFromErr(text string, err error) *mcp.CallToolResult

// Error result with printf-style formatting.
mcp.NewToolResultErrorf(format string, a ...any) *mcp.CallToolResult
```

**Return convention summary:**

| Situation | What to return |
|-----------|---------------|
| Success | `mcp.NewToolResultText(...)`, `nil` |
| Tool-level error (bad input, op failed) | `mcp.NewToolResultError(...)`, `nil` |
| Infrastructure failure (handler cannot run at all) | `nil`, `fmt.Errorf(...)` |

The third case causes the SDK to send an MCP protocol-level error — Claude cannot see the message and cannot self-correct. Reserve it for truly unexpected failures (e.g., the job manager is in an invalid state).

### 12.8 Server Creation Options

```go
s := server.NewMCPServer(
    name    string,           // Server name (reported during MCP handshake)
    version string,           // Server version string
    opts    ...ServerOption,  // Zero or more option functions (see below)
)
```

**Options used by the bridge:**

```go
// Advertise tool support in the server's capability declaration.
// listChanged=false: the tool list is static after startup.
// listChanged=true:  the server may send tool-list-changed notifications.
// The bridge uses false — all tools are registered before ServeStdio.
server.WithToolCapabilities(listChanged bool) ServerOption

// Add panic-recovery middleware to all tool handlers.
// A panic in any handler is caught and returned as a NewToolResultError
// instead of crashing the bridge process.
server.WithRecovery() ServerOption
```

### 12.9 Starting the Stdio Server

```go
// ServeStdio wraps the MCPServer in a StdioServer and calls Listen(ctx, os.Stdin, os.Stdout).
// Signature:
func ServeStdio(server *MCPServer, opts ...StdioOption) error

// Useful StdioOptions:
//   server.WithErrorLogger(logger *log.Logger)  — redirect SDK internal error output
//   server.WithWorkerPoolSize(n int)             — concurrent tool call workers (default: 5)
//   server.WithQueueSize(n int)                  — tool call queue depth (default: 100)

// Bridge usage (no options needed — defaults are fine):
if err := server.ServeStdio(s); err != nil {
    // Log to file — NEVER to stdout.
    bridgeLog.Printf("ServeStdio returned: %v", err)
}
// Reaches here when stdin is closed (EOF) → begin graceful shutdown.
```

**Shutdown behavior of `ServeStdio`:**
- Returns `nil` when `os.Stdin` reaches EOF (the expected case when Claude Desktop exits).
- Also sets up `signal.Notify` for `syscall.SIGTERM` and `syscall.SIGINT` internally. On Windows these signals are not reliably deliverable from external processes (see Section 3.14), but the `signal.Notify` call compiles and runs without error; stdin EOF remains the authoritative shutdown trigger.
- After `ServeStdio` returns, `main()` should call `jobManager.KillAll()` and exit (see Section 3.14).

### 12.10 Key Implementation Notes

1. **stdout is reserved for MCP protocol traffic.** Any write to `os.Stdout` outside the SDK (including `fmt.Print*`, `log.Print*` with the default logger, or any library that writes to stdout) will corrupt the JSON-RPC stream. Configure the bridge logger to write to a file before calling `ServeStdio`, and never use the default `log` package (which writes to stderr by default — stderr is safe, but a dedicated log file is preferred per Section 3.12).

2. **Tool names must be globally unique.** `s.AddTool` stores tools by name. A second `AddTool` call with an existing name silently replaces the first handler.

3. **Handlers run concurrently.** The `StdioServer` uses a worker pool (default 5 workers) for tool calls. Two tool calls can arrive and execute simultaneously. This is exactly why `safe_write_file` and `safe_append_file` share a `sync.Mutex` — without it, two concurrent write calls would race on the same file.

4. **JSON numbers are `float64`.** The JSON protocol encodes all numbers as `float64`. The `GetInt` / `RequireInt` accessors perform the `float64 → int` conversion (via truncation) automatically. The correct pattern for integer tool parameters is `mcp.WithNumber(...)` in the tool definition and `request.GetInt(...)` / `request.RequireInt(...)` in the handler. There is no `mcp.WithInteger` function in this SDK.

5. **`Required()` in the schema is advisory, not enforced by the SDK.** The `mcp.Required()` property option adds the parameter name to the JSON Schema `required` array, which is conveyed to Claude. However, the SDK does not validate incoming requests against this schema before calling the handler. The handler is responsible for validating its own inputs — which is why `RequireString`, `RequireInt`, etc. exist and should be used for required parameters.

---
## 9. Future Enhancements

These are planned upgrades that are deliberately deferred from the initial implementation. Each addresses a limitation documented in the proposal. This document references terms and concepts from *[Stateful Agent Design](stateful-agent-design.md)* without definition, so please read that design first.

This document was previously section 9, "Future Enhancements", in that design.

### 9.1 FTS5 Search Index (Option 3)

**Trigger:** When the number of blocks exceeds ~50 and filename-based retrieval from `index.md` becomes cumbersome.

**Design:** Add a SQLite FTS5 full-text search index alongside the markdown files. The index is a derived artifact — it can be rebuilt from the markdown files at any time.

```
C:\franl\.claude-agent-memory\
├── core.md
├── index.md
├── blocks\
│   └── ...
└── .search-index.db     # SQLite FTS5 (in .gitignore)
```

**New tool:** `memory_search(query: string, max_results: int) → [{file, snippet, score}]`

**Implementation:** Use `modernc.org/sqlite` (pure Go, no CGO) or `mattn/go-sqlite3` for the SQLite driver. Maintain the FTS5 index via a post-write hook: whenever the bridge detects a write to the memory directory (via `append_file` or by observing file modification times), re-index the changed file.

Also investigate semantic memory storage and search technologies such as:

- [engram](https://github.com/mirrorfields/engram)\
  *Memories are stored in SQLite alongside their vector embeddings and a full-text search index. Search combines cosine similarity (via sqlite-vec) with keyword matching (via FTS5), merged using reciprocal rank fusion — so you get both semantic understanding and exact-term recall. Collections are just string namespaces. Existing memories are migrated into the FTS index automatically on first run.*

- [MCP Memory Service](https://github.com/doobidoo/mcp-memory-service)\
  *Probably the most mature and featureful. It's a local MCP server with semantic search (using vector embeddings), a knowledge graph, a web dashboard, and REST API. Works with Claude Desktop, LangGraph, CrewAI, AutoGen, and 13+ other AI clients. Privacy-first / local-first design, optional Cloudflare cloud sync. Written in Python with SQLite-vec for fast local vector storage. Very actively maintained (10.16.x as of recently).*

- [agentic-mcp-tools/memora](https://github.com/agentic-mcp-tools/memora)\
  *Lightweight local MCP server with semantic memory, knowledge graphs, conversational recall, RAG-powered chat panel, and inter-agent event notifications. Supports both local embeddings (offline, ~2GB PyTorch) and cloud. Works via stdio MCP. Bonus: optional Cloudflare D1 cloud backend. Pretty impressive feature set for its size.*

- [tristan-mcinnis/claude-code-agentic-semantic-memory-system-mcp](https://github.com/tristan-mcinnis/claude-code-agentic-semantic-memory-system-mcp)\
  *Specifically designed for Claude Code. TypeScript MCP server using PostgreSQL + pgvector for semantic search. Supports project namespaces, knowledge graph relations, local embeddings (no external API needed), and intent-based natural language triggers. More opinionated/Claude-specific than the others.*

### 9.2 Memory-Aware Tools

**Trigger:** When compliance-based memory management via the skill proves insufficient — Claude frequently forgets to update `index.md`, corrupts YAML frontmatter, or uses incorrect naming conventions.

**Candidate tools:**

| Tool | Purpose |
|------|---------| 
| `update_memory_block(block, content)` | Write block content, auto-update `index.md` summary/date, validate YAML frontmatter |
| `create_memory_block(name, content)` | Create block with validated name, add `index.md` row, generate YAML frontmatter |
| `append_episodic_log(entry)` | Append entry to current month's episodic file, create file if needed, update `index.md` |

These tools trade skill simplicity (fewer instructions needed) for bridge complexity (more code to maintain). They also provide the "unambiguous tool names" benefit described in proposal Open Question #22 — reducing the risk of Claude using cloud VM tools for memory operations.

### 9.3 Architecture B2 Upgrade

**Trigger:** If Claude Desktop App's UI limitations or stability issues become a persistent problem.

**Steps:**
1. Add Streamable HTTP transport to the bridge (the `mcp-go` SDK supports both stdio and HTTP).
2. Configure a secure tunnel (Cloudflare Tunnel recommended — free for personal use).
3. Add the tunnel URL as a custom connector in Claude.ai (Settings > Connectors).
4. Optionally add OAuth 2.1 authentication.

The bridge codebase, memory directory, and skill are all unchanged. Only the transport layer changes.

### 9.4 GitHub Backup Automation

**Trigger:** After the system is stable and the memory directory has valuable content.

**Design:** A cron job or Windows Task Scheduler task that periodically commits the memory directory to a GitHub repo:

```
Pseudo-code for backup-memory.sh (runs every 4 hours):

cd C:\franl\.claude-agent-memory
git add -A
git diff --cached --quiet && exit 0  # Nothing to commit
git commit -m "Memory backup $(date -Iseconds)"
git push origin main
```

The `.search-index.db` file (if it exists) should be in `.gitignore`.


### 9.5 Remote Access: Mobile-to-Local Communication

**Trigger:** When mobile or web access to the local stateful agent is desired — e.g., using the Claude app on a phone to invoke tools on the home machine.

**Problem:** The primary agent runs in Claude Desktop on a local Windows 11 machine. When away from that machine, there is currently no way to read Layer 2 memory, run local commands, or delegate tasks to the stateful agent system. Three approaches to solving this problem are evaluated below, in order of preference.

#### 9.5.1 Dispatch Integration (Preferred Path)

In March 2026, Anthropic launched **Dispatch** as a research preview — a Cowork feature that allows a user to control a Mac-based, sandboxed Cowork session from a mobile device. Dispatch pairs a desktop Claude session with the Claude mobile app via QR code, enabling remote prompting from a phone. This is conceptually identical to the relay's `claude_prompt` operation: send a task to the local Claude instance, let it use whatever tools are available, and get back the result.

**Current limitations preventing adoption:**

| Limitation | Impact |
|-----------|--------|
| **Mac-only.** Dispatch requires the Claude Mac app; our system runs on Windows 11. | Blocking. No Windows support means Dispatch cannot be used at all. |
| **Cowork, not Claude Desktop.** Dispatch drives a Cowork session (sandboxed folder, Agent SDK). Our bridge is an MCP server that speaks stdio to Claude Desktop — a different runtime. | Blocking. Dispatch has no access to bridge tools (`safe_read_file`, `spawn_agent`, `run_command`, etc.). |
| **No MCP bridge access.** Cowork sessions do not currently expose user-configured MCP servers. | Blocking. Even on Mac, Dispatch wouldn't reach the bridge's memory mutex, session tracking, or sub-agent system. |
| **Research preview maturity.** Early testing reports ~50% success rate, slow performance, inability to interact with most apps. | Non-blocking but concerning. Expected to improve. |
| **No programmatic API.** Dispatch is a human-facing UI, not an API. Cannot be driven by automation, webhooks, or other agents. | Non-blocking for the primary use case (human on phone), but limits future integration. |

**Action items:**

1. **Monitor Dispatch GA and platform expansion.** If Anthropic releases Dispatch for Windows and/or adds MCP server access within Cowork sessions, re-evaluate. Both conditions must be met for Dispatch to replace the relay.
2. **Monitor Cowork + MCP convergence.** Anthropic may eventually allow Cowork sessions to connect to user-configured MCP servers (the way Claude Desktop does today). This would resolve the second and third limitations above.
3. **Do not implement the relay preemptively.** If Dispatch reaches our requirements within a reasonable timeframe (6–12 months), the relay design is unnecessary.

#### 9.5.2 GitHub Relay (Fallback)

If Dispatch does not gain Windows support and MCP bridge access within a reasonable timeframe, the **GitHub Relay** protocol remains a viable fallback. The relay uses a private GitHub repository as an asynchronous message bus, leveraging the fact that both Claude.ai (via the GitHub skill) and the local MCP bridge can read/write to the GitHub REST API.

**Architecture summary:**

```
┌──────────────────┐       ┌──────────────┐       ┌──────────────────────┐
│  Claude.ai       │       │   GitHub     │       │  Local Machine       │
│  (phone/web)     │       │   Private    │       │  (Windows 11)        │
│                  │  PUT  │   Repo       │  GET  │                      │
│  GitHub skill ───────────▶ requests/   ─────────▶  MCP Bridge         │
│                  │       │              │       │    │                 │
│                  │  GET  │              │  PUT  │    ├─ memory_query   │
│  GitHub skill ◀─────────── responses/ ◀──────────   ├─ shell_command  │
│                  │       │              │       │    └─ claude_prompt  │
└──────────────────┘       └──────────────┘       └──────────────────────┘
```

**Three operations, two execution paths:**

- **`memory_query`** — Reads a memory file from the Layer 2 directory. Handled directly by the bridge (no inference). Fast, deterministic.
- **`shell_command`** — Executes a shell command locally via Cygwin bash. Handled directly by the bridge (no inference). Equivalent to the bridge's `run_command` tool.
- **`claude_prompt`** — Forwards a prompt to Claude Desktop for full agent-loop processing. Claude Desktop performs whatever tool calls it deems appropriate, then returns its response via a `relay_respond` MCP tool. Requires an AutoHotkey-based prompt injection mechanism (design TBD).

**Security:** Bidirectional HMAC-SHA256 authentication via shared-secret signing of all messages. Both request and response payloads are signed using relay skill scripts (`relay_send.py`, `relay_receive.py`) that run via `uv run`. Replay prevention via ±5-minute timestamp validation. Operation allowlisting, rate limiting, and audit logging in the bridge.

**Typical round-trip latency:** 15–60 seconds for bridge-local operations (`memory_query`, `shell_command`); 30 seconds to 5+ minutes for `claude_prompt` (depends on task complexity and Claude Desktop inference time).

**Detailed specification:** The full protocol design — message format, HMAC protocol, bridge relay integration, Claude.ai workflow, script inventory, relay transport additions to the GitHub skill, and the AI Messaging skill — is preserved in [Appendix: GitHub Relay Detailed Specification](stateful-agent-design-chapter9-appendix-relay.md).

**Implementation trigger:** Implement the relay if, 6–12 months after Dispatch GA, any of the following remain true:
- Dispatch does not support Windows.
- Cowork sessions cannot access user-configured MCP servers.
- Dispatch lacks a programmatic API and automation is required.

#### 9.5.3 Architecture B2 as Long-Term Solution

Section 9.3 describes adding Streamable HTTP transport to the MCP bridge via a Cloudflare Tunnel. If implemented, this would give Claude.ai (or any remote client) **direct MCP access** to the bridge — bypassing both Dispatch and the GitHub relay entirely. This is the architectural endgame because:

1. **No intermediary.** Claude.ai connects directly to the bridge's MCP tools (memory, sub-agents, commands) over HTTPS. No polling, no relay repo, no message signing overhead.
2. **Real-time.** Latency drops from 15–60 seconds (relay) to sub-second (direct HTTP).
3. **Full tool access.** All bridge tools are available — `memory_session_start`, `safe_read_file`, `safe_write_file`, `safe_append_file`, `spawn_agent`, `check_agent`, `run_command` — with the same session tracking and mutex protection as local use.
4. **Platform-independent.** Works from any Claude client (web, mobile, API) with custom MCP connector support, regardless of OS.

The B2 upgrade is deferred because it requires Cloudflare Tunnel setup and OAuth 2.1 authentication — operational complexity that isn't justified until the base system is stable and proven. But it should be the preferred path once the system matures, rendering both the relay and Dispatch integration moot.

**Relationship between the three approaches:**

| Approach | Prerequisites | Latency | Tool access | Status |
|----------|--------------|---------|-------------|--------|
| **Dispatch** | Windows support, MCP in Cowork | ~seconds | Cowork tools only | Monitor (research preview) |
| **GitHub Relay** | Relay repo, HMAC secret, bridge relay goroutine | 15 sec–5 min | Full bridge tools (via relay) | Spec complete, deferred |
| **Architecture B2** | Cloudflare Tunnel, OAuth 2.1, Streamable HTTP | Sub-second | Full bridge tools (direct MCP) | Deferred (long-term) |

### 9.6 Proposed Solution to Concurrent Read-Modify-Write Race Condition

The current Layer 2 memory system design has a race condition: when multiple concurrent
conversations read the same memory file (e.g., `core.md`), modify it in-context, then write back the
modified version, the last write will overwrite the earlier ones, causing memory data to be lost.

Previously, we considered implementing optimistic concurrency control for memory files using
timestamps. If a memory file needed to be updated, but it had been modified by another conversation
after the current conversation last read the file, Claude would know to re-read, re-modify, and
re-write the file. This unacceptably increases token and context usage. It also depends on Claude's
compliance to instructions, which can fail unexpectedly.

This section proposes the following alternative approach:

1. The MCP tools that write memory data (currently `safe_write_file`, `safe_append_file`, and any
   added in the future) will implement optimistic concurrency control via timestamps.

2. When a concurrent read-modify-write race is detected by an MCP tool for a given file (e.g.,
   `core.md`), the bridge "branches" the memory file by writing the memory data to a filename
   uniquely associated with that conversation (e.g., `core-a1b2c3d4.md`).  The original memory file
   remains unmodified.

3. Later, during off-hours wake up periods, Claude Desktop or a sub-agent detects these "branched"
   memory files based on their names, and merges the branched files. This preserves memories from
   all branches.

4. If branched versions of files exist when memory is read or searched, results from all branches
   will be included in the results, suitably annotated to indicate that branching happened.

5. File names that appear in `index.md` do not change. `index.md` continues to reference memory
   files by non-branched names (e.g., `core.md` and `decisions.md`). The date stamp in `index.md`
   will always indicate the date of the most recent write to the listed file, including any of its
   branches.

Branched files are expected to be rare, as they are only created when multiple concurrent
conversations update the same memory file.

Advantages of this approach include:

- The race condition is solved.
- Claude is never involved in the optimistic concurrency control logic, which is faster and saves
  token and context usage.

Disadvantages of this system include:

- Merges cost tokens if Claude does it, though simple merges could be done by a cheaper model
  (Sonnet or Haiku).
- When reading memories from branched files, more memory data is returned (until a merge happens),
  which uses more tokens and context.

**QUESTIONS:**

1. How should the "timestamps" described above be implemented?  Should it be:

   - The hash of the file's contents.  **Issue:** This does not capture the temporal aspect of
     modifications, which would be valuable during merges.

   - The filesystem modification times of the memory files.

   - An internal mapping of memory file versions, tracked on each read and updated on each write.

   - A custom timestamp field stored in the memory file content (e.g., YAML front matter).<br/>
     **Issue:** Absent a `safe_edit_file` tool, this requires episodic memory files to be completely
     re-written via `safe_write_file` whenever the frontmatter changes.

   - What other options exist?

2. Is there any value in tracking the time of creation of a brancg (in addition to its time of last
   modification) as an aid to merging?<br/> **Issue:** The bridge would have to persist this
   somewhere in the filesystem, so it survives restarts.

2. How do the bridge tools know which conversation is reading/writing a given memory file? Does it
   need to be passed as a parameter to the tools — or can it be inferred by the tools somehow?

3. What is the exact file naming convention for branched files?

### 9.7 Importance Scoring on Blocks and Episodic Entries

**Inspiration:** The [HermitClaw](https://github.com/brendanhogan/hermitclaw) agent, which implements the memory architecture from [Park et al., 2023](https://arxiv.org/abs/2304.03442), assigns every memory object an importance score (1–10, LLM-evaluated) at write time. This score is then combined with recency and semantic relevance at retrieval time to rank memories. Computing importance eagerly at write time is cheap; recomputing it at every retrieval would be expensive.

**Motivation:** Claude currently makes block-loading decisions by matching the current conversation's topic against the one-line summaries in `index.md`. This handles *relevance* well, but *importance* is invisible — two blocks might both match the current topic, while one contains a critical architectural decision and the other contains a routine note. Without importance scores, Claude has no principled way to prioritize.

**Trigger:** When block count grows to the point where `index.md` topic-matching alone produces ambiguous or low-confidence loading decisions.

**Design:** Add an `importance` field (integer, 1–10) to the YAML frontmatter of all content blocks. The memory skill's write instructions include a single additional step: before closing a block write, assign an importance score using this scale:

| Score | Meaning |
|-------|---------|
| 1–3 | Routine notes, transient context, easily reconstructed information |
| 4–6 | Useful project context, preferences, resolved questions |
| 7–8 | Significant decisions, design constraints, hard-won knowledge |
| 9–10 | Foundational decisions that affect the entire system; rarely changes |

```yaml
---
created: 2026-02-15
updated: 2026-05-02
importance: 8          # 1=routine notes, 10=foundational/system-wide decision
tags: [project, go, mcp]
---
```

For episodic log entries, importance is recorded as a parenthetical annotation on the section heading, keeping the cost to a single added token cluster per entry:

```markdown
## 2026-05-02 — Branching race condition resolved (importance: 9)
Merged PR #27. HMAC authentication protocol for relay finalized. ...
```

The `index.md` table may optionally surface an `Importance` column to make the signal available at the index scan stage, before any block is loaded:

```markdown
| Block | Summary | Importance | Updated |
|-------|---------|------------|---------|
| project-mcp-bridge.md | MCP bridge server: Go implementation, tool design | 7 | 2026-05-01 |
| decisions.md | Cross-project architectural decisions and rationale | 9 | 2026-05-02 |
```

**Implementation cost:** Low. No bridge changes required. The change is purely additive to the file format and skill instructions. Existing blocks can be back-filled with importance scores during any routine memory maintenance session.

**Relationship to Section 9.1 (FTS5 Search):** If a search index is later added, the `importance` field becomes a first-class filter and sort key in search queries — e.g., `memory_search("race condition", min_importance=7)`.

### 9.8 Reflection Synthesis for Episodic Logs

**Inspiration:** HermitClaw's reflection mechanism (inherited from Park et al., 2023) periodically synthesizes raw memory observations into higher-level insight statements — "reflections" — which are stored back into the memory stream as first-class objects. Over time, reflections accumulate at increasing levels of abstraction, capturing patterns that no individual memory entry makes explicit.

**Motivation:** Episodic log files (`episodic-YYYY-MM.md`) accumulate entries indefinitely. An aging month's file is unlikely to be loaded in a typical session, yet it may contain *implicit insights* — patterns about effective approaches, recurring mistakes and corrections, stable preferences confirmed by experience — that are never extracted and promoted to where they'd actually be useful. The episodic log faithfully records *what happened*; reflection synthesis extracts *what was learned*.

**Trigger:** When a month's episodic file is 3+ months old and therefore unlikely to be loaded in normal sessions. This can be checked opportunistically at the start of off-hours maintenance cycles.

**Process:**

1. A maintenance sub-agent reads the aging episodic file in full.
2. It identifies any content that has become a *persistent fact* — likely to remain relevant beyond that specific month. Categories:
   - Behavioral preferences confirmed by experience (→ `core.md`)
   - Project decisions whose rationale should survive the project context (→ `decisions.md`)
   - Patterns or lessons that apply across conversations (→ `reflections.md`, see Section 9.9)
   - Significant technical discoveries relevant to an active project block (→ that project block)
3. The identified content is promoted to its target location using the normal block-write path (with importance scoring per Section 9.7).
4. The episodic file is condensed in place: prose entries are replaced by one-sentence structural summaries, preserving the date/title scaffold as an audit trail while dramatically reducing token cost if the file is ever loaded again.

**Example — before condensation:**

```markdown
## 2026-02-19 — Proposal session 9: Hybrid sync/async execution
Discovered Claude Desktop's 60-second MCP timeout. Redesigned spawn_agent with hybrid
sync/async model. Resolved Open Questions #18 (system prompt), #4 (layer reconciliation),
#10 (concurrent writes), #9 (layer boundary), #19 (CLAUDE.md optimization). The 25-second
sync window was chosen to stay under Claude Desktop's ~30-second reliability threshold.
```

**After condensation:**

```markdown
## 2026-02-19 — Proposal session 9: Hybrid sync/async execution *(condensed)*
Resolved OQs #4, #9, #10, #18, #19. Key outcome: hybrid sync/async spawn_agent design.
See decisions.md for rationale.
```

**Promoted to `decisions.md`:**

```markdown
## 2026-02-19 — Hybrid sync/async execution model (importance: 9)
spawn_agent uses a 25-second sync window chosen to stay under Claude Desktop's ~30-second
reliability threshold. Tasks completing within the window return results directly; longer
tasks return a job_id for async polling. Rationale: simpler than progress tokens, no
protocol extensions needed, enables parallel sub-agents as natural extension.
```

**Implementation cost:** Medium. Requires a maintenance sub-agent capable of reading an episodic file, classifying content, writing to multiple target files, and condensing the source file — all in a single pass. The bridge's existing `safe_write_file` and `safe_append_file` tools are sufficient; no new bridge tools are needed. The primary cost is authoring the sub-agent prompt and skill instructions carefully enough that the classification step is reliable.

**Relationship to Section 9.6 (Race Condition):** The condensation write to the episodic file is a full rewrite (`safe_write_file`), which means it is subject to the branching race detection mechanism. Since maintenance runs are typically off-hours with no concurrent conversations, this is unlikely to be a problem in practice.

### 9.9 A `reflections.md` Block Type

**Inspiration:** HermitClaw's depth-1 and depth-2 reflections capture *meta-level* insights about how the agent operates — not facts about specific projects, but patterns in how it thinks, what approaches consistently succeed, and what failure modes recur. These reflections are distinct from decisions (which are project-scoped), references (which are domain knowledge), and episodic logs (which are chronological records). They form a separate category: *learned operational patterns*.

**Motivation:** The current block taxonomy — `project-*.md`, `reference-*.md`, `episodic-YYYY-MM.md`, `decisions.md` — covers what work was done and what was decided, but has no natural home for meta-level patterns. Examples of content that belongs in this category but currently has no clear destination:

- *"When a session ends mid-task on a Go project, the next session works best if it reads the relevant project block before any other context — resuming without it consistently causes repeated groundwork."*
- *"Fran's approach to ambiguous architectural questions reliably starts with the minimal-viable option, not the optimal one. Proposals that lead with the ideal design tend to stall."*
- *"Reflection synthesis passes (Section 9.8) should not be triggered mid-session — the token cost of reading a full episodic file competes with the active task."*

**Design:** Add a single `reflections.md` block in the `blocks/` directory. Unlike other blocks, it is not created directly during conversations — it is populated exclusively by reflection synthesis passes (Section 9.8) and periodic maintenance. The block uses the standard YAML frontmatter format with a high default importance score (since operational patterns are broadly applicable), organized by theme:

```markdown
---
created: 2026-05-01
updated: 2026-05-15
importance: 8
tags: [reflections, meta, operational]
---

# Operational Reflections

## Session Continuity
- Starting a session that resumes a Go project without first reading the project block
  consistently causes repeated groundwork. Always load the relevant project block before
  responding on first turn. *(derived: 2026-05 from episodic-2026-02, episodic-2026-03)*

## Architectural Approach
- Fran's default problem-solving mode leads with the minimal-viable option before the
  optimal one. Proposals structured the other way tend to stall at the review stage.
  *(derived: 2026-05 from episodic-2026-02, episodic-2026-04)*

## Maintenance Scheduling
- Reflection synthesis passes should not run mid-session; the full episodic file read
  competes with the active task's context budget. Schedule for off-hours only.
  *(derived: 2026-05)*
```

The `*(derived: ...)` annotation records the source episodic files from which the reflection was extracted, providing an audit trail analogous to HermitClaw's `references` field on reflection memory objects.

**`index.md` entry:**

```markdown
| reflections.md | Learned operational patterns derived from episodic synthesis | 8 | 2026-05-15 |
```

**Loading behavior:** `reflections.md` should be loaded opportunistically — when the session involves meta-level questions about how to work effectively, when beginning a new project phase, or when the skill detects that `core.md` does not already address the relevant pattern. It should *not* be loaded by default on every session start, as its content is already incorporated into `core.md` for the most stable patterns.

**Implementation cost:** Low, contingent on Section 9.8 being implemented first. The block format requires no new bridge tooling. The main investment is the synthesis prompt that correctly identifies meta-level patterns versus project-specific decisions during the episodic condensation pass.
