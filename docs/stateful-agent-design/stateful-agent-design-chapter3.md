# Stateful Agent System: Detailed Design

**Version:** 2.0 (Draft)  
**Date:** February - June 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)  
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.
- [Design Update Plan](design-update-plan.md) — the decision record for the memory-aware tools redesign incorporated into this version.

## Contents

- [3. MCP Bridge Server](#3-mcp-bridge-server)
  - [3.1 Go Module Structure](#31-go-module-structure)
  - [3.2 Configuration](#32-configuration)
  - [3.3 Tool Summary](#33-tool-summary)
  - [3.4 Tool: spawn_agent](#34-tool-spawn_agent)
  - [3.5 Tool: check_agent](#35-tool-check_agent)
  - [3.6 Tool: run_command](#36-tool-run_command)
  - [3.7 Memory-Aware Tools: Overview and Abstraction](#37-memory-aware-tools-overview-and-abstraction)
  - [3.8 Tool: memory_start_conversation](#38-tool-memory_start_conversation)
  - [3.9 Tools: memory_get_core and memory_write_core](#39-tools-memory_get_core-and-memory_write_core)
  - [3.10 Tool: memory_get_index](#310-tool-memory_get_index)
  - [3.11 Tools: memory_get_block, memory_write_block, memory_append_block](#311-tools-memory_get_block-memory_write_block-memory_append_block)
  - [3.12 Tool: memory_append_episodic](#312-tool-memory_append_episodic)
  - [3.13 Tool: memory_run_maintenance](#313-tool-memory_run_maintenance)
  - [3.14 Handle Management](#314-handle-management)
  - [3.15 Per-Handle Branching and Race Detection](#315-per-handle-branching-and-race-detection)
  - [3.16 Block File Format and Atomic Writes](#316-block-file-format-and-atomic-writes)
  - [3.17 Merge Process and Merge Mutex](#317-merge-process-and-merge-mutex)
  - [3.18 Bridge State Persistence and Recovery](#318-bridge-state-persistence-and-recovery)
  - [3.19 Error Response Convention](#319-error-response-convention)
  - [3.20 Async Executor](#320-async-executor)
  - [3.21 Job Lifecycle Manager](#321-job-lifecycle-manager)
  - [3.22 Logging](#322-logging)
  - [3.23 Error Handling](#323-error-handling)
  - [3.24 Graceful Shutdown](#324-graceful-shutdown)

## 3. MCP Bridge Server

The MCP bridge server is a Go binary that runs locally, providing Bash access, sub-agent spawning,
and memory access to be used by the Claude Desktop App via the MCP protocol. Memory access is
provided through **memory-aware tools** that operate on memory concepts (core, blocks, the index)
rather than on files — the bridge owns the entire file layout and the LLM never sees a file path,
a branch, or any other storage detail. See [Section 3.7](#37-memory-aware-tools-overview-and-abstraction)
for the abstraction model.

### 3.1 Go Module Structure

```
mcp-bridge/
├── go.mod                    # Module: github.com/fpl9000/mcp-bridge
├── go.sum
├── main.go                   # Entry point: loads config, loads persisted state, registers tools,
│                             #   starts stdio server, persists state on shutdown
├── config.go                 # Configuration loading and validation
├── tools.go                  # Tool handler registration
├── async.go                  # Shared async executor: sync window, async handoff, output truncation
│                             #   Used by both spawn_agent and run_command
├── spawn.go                  # spawn_agent tool handler: builds claude -p command, delegates to async executor
├── check.go                  # check_agent tool handler
├── run_command.go            # run_command tool handler: builds shell command, delegates to async executor
├── handles.go                # Handle minting, handle map, read baselines, retention and eviction
├── memory_core.go            # memory_get_core / memory_write_core tool handlers
├── memory_index.go           # memory_get_index tool handler: derived-view index assembly + cache
├── memory_block.go           # memory_get_block / memory_write_block / memory_append_block tool handlers
├── memory_episodic.go        # memory_append_episodic tool handler (month rotation)
├── maintenance.go            # memory_run_maintenance: merge orchestration + handle cleanup sweep
├── branching.go              # Per-handle branch creation, naming, and the lazy-adoption disk scan
├── frontmatter.go            # YAML frontmatter parsing/composition for block files
├── persistence.go            # .bridge-state.json: load, reconcile, checkpoint, shutdown write
├── memmutex.go               # Memory mutex shared by all memory tools; merge mutex semantics
├── errors.go                 # Error response convention: stable codes + natural-language messages
├── jobs.go                   # Job lifecycle manager (background goroutine)
├── logging.go                # Structured logging to file
└── bridge-config.yaml        # Default configuration (embedded or external)
```

**Dependencies:**
- `github.com/mark3labs/mcp-go` — MCP SDK for Go (see [Chapter 12, Appendix: mark3labs/mcp-go SDK Reference](stateful-agent-design-chapter12.md#12-appendix-mark3labsmcp-go-sdk-reference) for details).
- A YAML frontmatter parser — either `gopkg.in/yaml.v3` (frontmatter blocks are plain YAML) or hand-rolled parsing of the `---`-delimited header. The frontmatter schema is two fields (see [Section 3.16](#316-block-file-format-and-atomic-writes)), so the hand-rolled option is viable if the dependency is unwanted.
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

# Memory directory (the memory root; the bridge owns everything under it)
memory:
  directory: "C:\\franl\\.claude-agent-memory"
  summary_max_length: 200         # Cap on block summary length (chars); longer
                                  #   summaries are truncated with a warning

# Handle management (see Section 3.14)
handle:
  id_length: 8                    # Length of generated handles (8 lowercase alphanumerics)
  retention_days: 60              # Zero-branch handles inactive longer than this are
                                  #   evicted during the maintenance sweep

# Bridge state persistence (see Section 3.18)
persistence:
  state_file: ".bridge-state.json"        # Relative to memory.directory
  checkpoint_interval_seconds: 5          # Debounce window for checkpoint writes; state
                                          #   changes are coalesced and flushed at most
                                          #   once per interval. Branch creation always
                                          #   triggers an immediate checkpoint.

# Branching (concurrent read-modify-write race resolution; see Section 3.15)
branching:
  enabled: true                   # Debugging escape hatch: false reverts to
                                  #   last-writer-wins behavior (no branches created)

# Maintenance (see Section 3.13)
maintenance:
  max_blocks_per_call: 10         # Cap on blocks merged per memory_run_maintenance
                                  #   call, to stay under the MCP tool-call timeout.
                                  #   More pending work is signaled via more_pending.

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

Note the absence of the old `session:` block: the `max_sessions` cap from the session-era design
is gone (handle growth is bounded by the retention-based eviction policy in [Section 3.14](#314-handle-management),
not by a hard cap — a hard cap is deferred to v1.x as a backstop), and the session ID length is
replaced by `handle.id_length`.

**Pseudo-code for configuration loading:**

```
func LoadConfig(path string) Config:
    // Read YAML file
    // Apply defaults for any missing fields
    // Validate:
    //   - async.sync_window_seconds < 30
    //   - memory.directory exists (or create it)
    //   - memory.summary_max_length > 0
    //   - handle.id_length >= 8
    //   - handle.retention_days > 0
    //   - persistence.checkpoint_interval_seconds >= 1
    //   - maintenance.max_blocks_per_call >= 1
    //   - logging.file parent directory exists
    //   - claude_cli.path is executable
    //   - run_command.shell is executable
    // Return validated config
```

### 3.3 Tool Summary

The bridge registers twelve tools: three for sub-agents and local commands, and nine memory-aware tools.

| Tool                        | Purpose                                                                                                                                                                                                         |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `spawn_agent`               | Launch a sub-agent (`claude -p`) with a task. Returns result (sync) or job_id (async).                                                                                                                          |
| `check_agent`               | Poll a running async job by job_id. Returns status and result. Used for both `spawn_agent` and `run_command` async jobs.                                                                                        |
| `run_command`               | Execute a shell command on the local machine. No LLM involved — direct subprocess execution. Uses the same hybrid sync/async model as `spawn_agent`. Far cheaper than spawning a sub-agent for simple commands. |
| `memory_start_conversation` | Allocate a fresh handle for this conversation. Call once per conversation before any other memory tool, and again to recover from any handle error.                                                             |
| `memory_get_core`           | Return the core memory content. Sets this handle's read baseline for core and reports `changed_since_last_read`.                                                                                                |
| `memory_write_core`         | Replace the core memory content. Race-detected; may transparently route to a per-handle branch.                                                                                                                 |
| `memory_get_index`          | Return the derived index: a structured list of `{ name, summary, updated_at }` for every block visible to this handle. Assembled on demand from block frontmatter — not a stored file.                          |
| `memory_get_block`          | Return a block's body content (frontmatter stripped). Sets the read baseline and reports `changed_since_last_read`.                                                                                             |
| `memory_write_block`        | Replace a block's body content, optionally updating its summary. Race-detected; may transparently route to a per-handle branch. Creates the block if it doesn't exist (summary required for creation).          |
| `memory_append_block`       | Append text to a block. Serialized, never creates a branch (routes to an existing per-handle branch if one exists).                                                                                             |
| `memory_append_episodic`    | Append an entry to the current month's episodic log. The bridge handles month rotation internally.                                                                                                              |
| `memory_run_maintenance`    | Merge pending memory branches back into canonical state via sub-agents, then sweep and evict stale handles. Invoked when the user asks for memory maintenance.                                                  |

Every memory tool takes `handle` as its first, required parameter and echoes the handle back in
every response (see [Section 3.7](#37-memory-aware-tools-overview-and-abstraction)).

### 3.4 Tool: spawn_agent

This is the most complex tool in the bridge. It launches a Claude Code CLI sub-agent with a task. The subprocess lifecycle (sync window, async handoff, output truncation) is managed by the shared async executor (see [Section 3.20](#320-async-executor)).

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

This tool executes a shell command on the local machine and returns its output. No LLM is involved — this is direct subprocess execution, making it dramatically cheaper than `spawn_agent` for simple operations like `curl`, `git status`, `grep`, `find`, `cat`, `ls`, directory listings, and short scripts. It uses the same hybrid sync/async model as `spawn_agent` via the shared async executor (see [Section 3.20](#320-async-executor)), so long-running commands (e.g., a recursive `grep` of a large codebase) are handled correctly without hitting the MCP timeout.

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

### 3.7 Memory-Aware Tools: Overview and Abstraction

The bridge's memory tools operate on **memory concepts, not files**. The LLM's mental model of
the memory system consists of exactly five concepts:

| Concept | What the LLM knows about it |
|---------|------------------------------|
| **Handle** | An opaque 8-character token identifying this conversation to the bridge. Obtained from `memory_start_conversation`, passed to every memory tool, never inspected or invented. |
| **Core** | A single always-loaded prose document ("who am I and what are we working on"). Read with `memory_get_core`, replaced with `memory_write_core`. |
| **Blocks** | Named content documents (`project-foo`, `decisions`, `episodic-2026-06`, ...). Read, written, and appended to by name. |
| **Summaries** | A one-line description attached to each block, supplied via the `summary` parameter of `memory_write_block`. |
| **The index** | A structured roll-up of all blocks (`name`, `summary`, `updated_at`) returned by `memory_get_index`. The LLM calls a tool to get it; it does not read a file. |

Everything else is bridge-internal and **invisible to the LLM**: file paths, the on-disk layout,
YAML frontmatter, branches, the per-handle branch map, read baselines, the memory mutex, the merge
mutex, and the state file. From the LLM's perspective, every read returns *the* current state of a
target and every write succeeds — even when the bridge has transparently routed the operation
through a per-handle branch file (see [Section 3.15](#315-per-handle-branching-and-race-detection)).

This is the central shift from the v1 design: **correctness no longer depends on LLM compliance.**
The v1 design exposed file paths and branch content to the LLM and relied on skill instructions to
keep the index in sync, use the right tools, and interpret branch annotations. The memory-aware
design moves all of that into the bridge, where it is enforced by code. The skill (Chapter 5)
shrinks accordingly: it now teaches *when* to read and write memory, not *how* the storage works.

**The handle is echoed in every response.** Every memory tool response includes the `handle`
field, not just the initial `memory_start_conversation` response. This refreshes the handle in the
LLM's context on every memory tool call, dramatically reducing the chance that context compaction
loses it. A conversation that has made any recent memory call will have its handle present in the
surviving context.

**Abstraction discipline.** Tool responses — including error responses — must never leak
implementation details. An error message that mentions a branch filename, the merge mutex, or
frontmatter teaches the LLM about machinery it must not reason about. The error response
convention in [Section 3.19](#319-error-response-convention) enforces this.

### 3.8 Tool: memory_start_conversation

This tool allocates a fresh handle for the calling conversation. The skill instructs Claude to call
it once at the start of any conversation that will use memory, before any other memory tool, and to
call it again as the uniform recovery step whenever any memory tool returns a handle error.

**Why the bridge mints the handle (not the LLM):** If Claude composed its own identifier, it would
need to reproduce it verbatim on every subsequent tool call — and LLMs are unreliable at exact
string consistency across many calls. A bridge-minted short opaque handle is trivially
reproducible: Claude just parrots back a fixed string, and that string reappears in every memory
tool response to keep it fresh in context. Uniqueness is guaranteed by the bridge, which controls
generation and checks for collisions. An LLM-supplied handle the bridge does not recognize is
rejected with an error (see [Section 3.14](#314-handle-management)) — it is never honored or
silently substituted.

**MCP tool definition:**

```
Name:        "memory_start_conversation"
Description: "Start a memory conversation and receive a handle. Call this once
             at the start of any conversation that will use memory, before any
             other memory tool. Pass the returned handle to every subsequent
             memory tool call. If any memory tool returns a handle error, call
             this again to obtain a fresh handle and retry the operation."

Input Schema:
  (no required parameters)

Output Schema:
  handle:  string   — Opaque 8-character handle (e.g., "h7k3xy90")
```

**Handler pseudo-code:**

```
func HandleMemoryStartConversation() MemoryStartConversationResult:

    // 1. Mint a candidate handle: 8 characters from the alphabet [a-z0-9],
    //    generated by the bridge's PRNG (see Section 3.14 for the policy).
    handle = mintHandle(config.Handle.IDLength)

    // 2. Collision check against the in-memory handle map. A collision is
    //    vanishingly unlikely (~2.8e12 possibilities) but cheap to verify,
    //    making in-flight collision impossible by construction.
    while handleMap.Exists(handle):
        handle = mintHandle(config.Handle.IDLength)

    // 3. Register the handle: empty branch map, empty read baselines,
    //    last-activity = now.
    handleMap.Register(handle)

    // 4. Schedule a persistence checkpoint (debounced; see Section 3.18) so
    //    the new handle survives a bridge restart.
    persistence.MarkDirty()

    return { handle: handle }
```

Note what this response deliberately does **not** include: a `branches_exist` flag, a pending-merge
count, or any other branch surfacing. Branches are invisible to the LLM
(see [Section 3.15](#315-per-handle-branching-and-race-detection)), and pending-merge debris from
abandoned conversations is reaped by `memory_run_maintenance` on the user's schedule — there is
nothing the LLM needs to be told at conversation start.

### 3.9 Tools: memory_get_core and memory_write_core

Core memory is a single always-loaded prose document — the Layer 2 equivalent of "who am I and
what are we working on" (see [Chapter 4, Section 4.3](stateful-agent-design-chapter4.md#43-file-format-coremd)).
These two tools read and replace it. The bridge maps "core" to its on-disk location
(`<memory.directory>\core.md`); the LLM never sees that path.

**MCP tool definitions:**

```
Name:        "memory_get_core"
Description: "Return the core memory content. Call at the start of every
             conversation, after memory_start_conversation. If
             changed_since_last_read is true, the content has changed since
             you last read it — treat earlier conclusions drawn from the
             previous version as potentially stale."

Input Schema:
  handle:  string, required  — Handle from memory_start_conversation

Output Schema:
  handle:                   string  — Echoed back
  content:                  string  — The core document
  changed_since_last_read:  boolean — True only if this handle previously read
                                      core and the content has since changed
                                      without this handle writing it
```

```
Name:        "memory_write_core"
Description: "Replace the core memory content. Provide the COMPLETE document —
             this is a full replacement, not an edit. Keep core under ~1,000
             tokens; move detailed content into blocks."

Input Schema:
  handle:   string, required  — Handle from memory_start_conversation
  content:  string, required  — Complete replacement content

Output Schema:
  handle:  string   — Echoed back
  ok:      boolean  — True on success
```

**Read handler pseudo-code (shared by `memory_get_core` and `memory_get_block`):**

```
func HandleMemoryGet(handle string, target Target) MemoryGetResult:

    // 1. Validate the handle (Section 3.14 recovery procedure: known map entry,
    //    else lazy adoption from disk, else error).
    if err = handles.Validate(handle); err != nil:
        return errorResponse(err)            // INVALID_HANDLE / MALFORMED_HANDLE

    // 2. Acquire the memory mutex. Reads serialize alongside writes so the
    //    signature we record is consistent with the content we return.
    memMutex.Lock()
    defer memMutex.Unlock()

    // 3. Choose which file to read: this handle's branch of the target if one
    //    exists in the branch map, else the canonical (base) file.
    path = branchMap.PathFor(handle, target) or basePathFor(target)

    // 4. Read the file. For blocks, strip the YAML frontmatter and return only
    //    the body (Section 3.16). Core has no frontmatter.
    content = readAndStripFrontmatter(path)

    // 5. Compute the changed_since_last_read flag: true iff this handle has a
    //    recorded baseline signature for this target AND the current content's
    //    signature differs from it. The flag is false on first reads, on
    //    unchanged re-reads, and whenever the read came from this handle's own
    //    branch (the branch tracks this handle's own writes by construction).
    sig = signature(path)                    // ModTime + size (hash is a v1.x option)
    changed = baselines.Has(handle, target) && baselines.Get(handle, target) != sig

    // 6. Record the new baseline and update the handle's last-activity time.
    baselines.Set(handle, target, sig)
    handleMap.Touch(handle)
    persistence.MarkDirty()

    return { handle: handle, content: content, changed_since_last_read: changed }
```

**Write handler:** `memory_write_core` follows the shared write path described in
[Section 3.15](#315-per-handle-branching-and-race-detection): if this handle already owns a branch
of core, the write goes to that branch; otherwise the base signature is compared against this
handle's read baseline, and the write goes to the base (signatures match) or to a newly created
branch (signatures differ). The write itself is atomic per [Section 3.16](#316-block-file-format-and-atomic-writes).
In every case the tool returns `{ handle, ok: true }` — the LLM is never told which file received
the write.

**The `changed_since_last_read` flag** is the v1 mitigation for the cross-conversation visibility
of writes. v1 ships with branch-on-race-only semantics (not snapshot isolation), so when another
conversation legitimately writes core or a block (no race), this conversation's next read returns
the new content. The flag tells the LLM "your prior view is stale" without revealing *what*
changed or *who* changed it — preserving per-conversation isolation (conversation X cannot
introspect conversation Y's activity) while letting X know to re-derive anything that depended on
the earlier content. The stricter snapshot-isolation alternative (branching on every
write-while-others-have-outstanding-reads) was considered and deferred to v1.x: it would make
almost every write to a hot target branch, exploding the merge load, to prevent a surprise that is
hypothetical until observed in practice. (Decision record: update plan §3.2.)

`memory_get_index` does not carry a `changed_since_last_read` flag in v1 — per-block changes are
already signaled by the per-block read flag. It can be added later if it proves useful.

### 3.10 Tool: memory_get_index

The index is a **derived view, not a stored file**. There is no `index.md` on disk. Each block's
`summary` and `updated_at` live in YAML frontmatter inside the block file itself
(see [Section 3.16](#316-block-file-format-and-atomic-writes)), and `memory_get_index` assembles
the index on demand by walking the blocks directory.

**Why derived:** A stored index file would have to be updated on every block write, and under the
per-handle branch model that creates a leakage problem: conversation Y's summary updates would
land in a canonical index file and become visible to conversation X, even while Y's block content
was correctly isolated in a branch. (The original stored-index design had exactly this flaw —
decision record: update plan §2.8.) Deriving the index from the same files the per-block reads use
makes the leak impossible by construction: handle H's index view is assembled from H's branches
plus the bases of blocks H hasn't branched — exactly what H's per-block reads return. The index
and the blocks are guaranteed consistent because they come from the same files.

**MCP tool definition:**

```
Name:        "memory_get_index"
Description: "Return the index of memory blocks: each block's name, one-line
             summary, and last-updated time. Use it to decide which blocks are
             relevant to the current conversation, then load them with
             memory_get_block."

Input Schema:
  handle:  string, required  — Handle from memory_start_conversation

Output Schema:
  handle:  string  — Echoed back
  index:   object  — See schema below
```

**Index schema:**

```json
{
  "handle": "abc1def2",
  "index": {
    "schema_version": 1,
    "blocks": [
      { "name": "project-foo", "summary": "...", "updated_at": "2026-05-20T14:23:00Z" },
      ...
    ]
  }
}
```

Notes on the schema:

- **Ordering:** stable sort by `name`. Insertion order would be subtle to maintain across bridge
  restarts, and `updated_at` order would change on every write, which is disruptive for the LLM's
  mental model of the index.
- **Timestamp format:** `updated_at` uses *extended* ISO 8601 (`2026-05-20T14:23:00Z`). This
  intentionally differs from the *compact* form used in branch filenames
  ([Section 3.15](#315-per-handle-branching-and-race-detection)): colons are legal in JSON string
  values, so the more readable extended form is used there; the compact form is only required
  where Windows filename rules forbid colons. The two formats coexisting is deliberate.
- **Pagination:** none in v1. If the index grows past ~500 entries, revisit.

**Assembly pseudo-code:**

```
func HandleMemoryGetIndex(handle string) MemoryGetIndexResult:

    // 1. Validate the handle; acquire the memory mutex; touch last-activity.

    // 2. Enumerate block files in the blocks directory (base files only —
    //    branch files are matched to their handles separately).

    // 3. For each block name B, choose which file to read: this handle's
    //    branch of B if one exists in the branch map, else the base file.

    // 4. Extract summary and updated_at from the chosen file's frontmatter.
    //    Files with missing/damaged frontmatter get defaults (Section 3.16).

    // 5. Sort entries by name and return the assembled index.
```

**Caching:** `memory_get_index` is O(n_blocks) in the worst case. The bridge maintains an
in-memory cache of assembled index views: one per handle, invalidated when that handle writes a
block or when the blocks directory's most recent mtime changes. Steady-state cost is a cached
lookup; the walk runs only when the cache is stale.

**Debugging:** A human can inspect block metadata by opening any block file — the frontmatter is
at the top. If a human-readable index snapshot is ever wanted, a `memory_dump_index(handle, path)`
tool that writes the current derived view to a user-named file *outside* the memory directory can
be added later; it is not part of v1.

### 3.11 Tools: memory_get_block, memory_write_block, memory_append_block

Blocks are the named content documents of Layer 2 memory (`project-foo`, `decisions`,
`episodic-2026-06`, ...). The LLM addresses them by **name only** — the bridge maps a block name
to its on-disk file (`<memory.directory>\blocks\<name>.md`) and manages the YAML frontmatter
transparently. Block names may contain letters, digits, hyphens, and underscores; anything else is
rejected with `INVALID_BLOCK_NAME`. Naming conventions (which prefixes mean what) are documented
in [Chapter 4, Section 4.8](stateful-agent-design-chapter4.md#48-block-naming-conventions).

**MCP tool definitions:**

```
Name:        "memory_get_block"
Description: "Return a memory block's content by name. Block names come from
             memory_get_index. If changed_since_last_read is true, the content
             has changed since you last read it — treat earlier conclusions
             drawn from the previous version as potentially stale."

Input Schema:
  handle:      string, required  — Handle from memory_start_conversation
  block_name:  string, required  — Block name (e.g., "project-foo")

Output Schema:
  handle:                   string
  content:                  string  — The block body (metadata managed by the bridge)
  changed_since_last_read:  boolean
```

```
Name:        "memory_write_block"
Description: "Replace a memory block's content, or create a new block. Provide
             the COMPLETE content — this is a full replacement, not an edit.
             The optional summary is a one-line description shown in the index;
             it is REQUIRED when creating a new block, and preserved unchanged
             if omitted when updating an existing one."

Input Schema:
  handle:      string, required  — Handle from memory_start_conversation
  block_name:  string, required  — Block name
  content:     string, required  — Complete replacement body
  summary:     string, optional  — One-line description for the index

Output Schema:
  handle:  string
  ok:      boolean
```

```
Name:        "memory_append_block"
Description: "Append text to a memory block. The text is appended exactly as
             provided — include leading newlines if needed for formatting.
             Creates the block if it doesn't exist (a summary will be needed:
             prefer memory_write_block for first creation)."

Input Schema:
  handle:      string, required  — Handle from memory_start_conversation
  block_name:  string, required  — Block name
  content:     string, required  — Text to append

Output Schema:
  handle:  string
  ok:      boolean
```

**The `summary` parameter contract** (decision record: update plan §3.5):

- **For new blocks** (no block file with that name visible to this handle): `summary` is
  **required**. The bridge rejects the call with `SUMMARY_REQUIRED` if it is absent. A block must
  enter the index with a meaningful description.
- **For existing blocks:** `summary` is optional. If absent, the existing summary in the block's
  frontmatter is preserved unchanged. If present (including the empty string), it replaces the
  existing summary.
- **Length:** capped at `memory.summary_max_length` (default 200 characters). Longer summaries are
  truncated and the response includes a warning; alternatively the bridge may reject with
  `SUMMARY_TOO_LONG` if truncation would be misleading.

There is **no separate index-update tool** and no index-update instruction in the skill. The
summary travels with the block content in a single `memory_write_block` call, and the bridge
writes frontmatter and body together as one file ([Section 3.16](#316-block-file-format-and-atomic-writes)),
so the index can never drift out of sync with the blocks — a whole category of v1 compliance
failures is eliminated structurally.

**Read behavior:** `memory_get_block` follows the shared read path in
[Section 3.9](#39-tools-memory_get_core-and-memory_write_core): branch-or-base file selection,
frontmatter stripped, baseline recorded, `changed_since_last_read` computed. Reading a block that
does not exist (no base file and no branch for this handle) returns `BLOCK_NOT_FOUND`.

**Write behavior:** `memory_write_block` follows the shared race-detected write path in
[Section 3.15](#315-per-handle-branching-and-race-detection). Writing a block that does not exist
creates the base file (a true first creation has no race to detect — but see Section 3.15 for the
simultaneous-first-write case, which does branch).

**Append semantics — serialized, never branched** (decision record: update plan §2.11): appends
are serialized by the memory mutex and **never create a branch**. The semantic justification:
appends are commutative when the order isn't load-bearing, and for episodic logs (the primary
append use case) chronological ordering is already approximate. Race detection on appends would
produce branches that need semantic merging for no real benefit; serializing avoids the problem
entirely. Two routing details preserve consistency:

- If this handle already owns a branch of the target block (from a prior racing *write*), the
  append goes to **that branch** — otherwise the handle's next read (which routes through its
  branch) would not show the appended text, violating read-your-own-writes.
- Otherwise the append goes to the base file, regardless of baselines. The handle's read baseline
  for the block is updated to the post-append signature so the append doesn't trigger a spurious
  race on this handle's next full write.

### 3.12 Tool: memory_append_episodic

Episodic logs are a distinct file category from ordinary blocks: monthly files
(`episodic-YYYY-MM.md`) holding dated entries for significant conversations
(see [Chapter 4, Section 4.6](stateful-agent-design-chapter4.md#46-file-format-episodic-logs)).
This tool appends an entry to the **current month's** log; the bridge selects the target file
from the system clock and creates a new month's file automatically at each rollover. The LLM
never computes a filename or even a block name to append an episodic entry — this matches the
"bridge owns the file layout" principle.

**MCP tool definition:**

```
Name:        "memory_append_episodic"
Description: "Append an entry to the episodic log (the chronological record of
             significant conversations). The bridge files the entry under the
             current month automatically. Format the entry as:
             '## YYYY-MM-DD — Brief Title' followed by a 2-5 sentence summary."

Input Schema:
  handle:   string, required  — Handle from memory_start_conversation
  content:  string, required  — The entry text to append

Output Schema:
  handle:  string
  ok:      boolean
```

**Behavior details:**

- Month rotation is internal: the bridge computes `episodic-YYYY-MM` from the current local date.
  On the first append of a new month, the bridge creates the file with bridge-generated
  frontmatter (`summary: "Conversation log for <Month YYYY>"`, `updated_at` set to now) and a
  `# <Month YYYY>` heading, then appends the entry.
- Episodic files live in the blocks directory and carry frontmatter like any other block, so they
  **appear in the derived index** and are readable via `memory_get_block` (using the name shown in
  the index, e.g., `episodic-2026-06`). `memory_append_episodic` is a convenience over
  `memory_append_block` that removes the burden of computing the current month's name; it shares
  the same append semantics (serialized, never branched, branch-routed if one exists) from
  [Section 3.11](#311-tools-memory_get_block-memory_write_block-memory_append_block). Each append
  also refreshes the file's `updated_at` frontmatter so the index reflects the last entry time.

### 3.13 Tool: memory_run_maintenance

Maintenance is the manually triggered process that folds pending memory branches back into
canonical state and reaps stale handle records. v1 has **no automatic merge scheduling**: merges
happen when, and only when, the user asks for them (in any phrasing — "run memory maintenance,"
"merge memory," "consolidate your memory," etc.), which causes the LLM to call this tool. The
manual approach is correct (merges happen when asked) and operable (the user controls timing); it
sidesteps the unattended-execution problem entirely. Automated triggers (Task Scheduler +
`claude -p`, AutoHotkey, lazy merge at conversation start) are deferred to v1.x. (Decision record:
update plan §3.1, §3.9.)

**MCP tool definition:**

```
Name:        "memory_run_maintenance"
Description: "Run memory maintenance: consolidates memory that has accumulated
             from concurrent conversations back into a single canonical state.
             Call when the user asks for memory maintenance, merging, or
             consolidation. The call may take a noticeable amount of time, and
             memory operations from other concurrent conversations will briefly
             block while it runs. If more_pending is true in the response, call
             again to continue."

Input Schema:
  handle:  string, required  — Handle from memory_start_conversation

Output Schema:
  handle:          string
  ok:              boolean
  merged_blocks:   integer   — Number of blocks whose branches were merged this call
  more_pending:    boolean   — True if the per-call cap was reached and pending
                               merges remain; call again to continue
  errors:          string[]  — Optional; natural-language descriptions of any
                               per-block merge failures (the affected branches
                               are left on disk for the next maintenance run)
```

**Handler behavior:**

1. Validate the handle and acquire no long-lived locks yet.
2. **Enumerate pending work:** scan the memory directory for *all* branch files on disk —
   regardless of whether their owning handles are live. Branches from abandoned conversations are
   merged exactly like branches from active ones; from the merge's perspective, branched content
   is branched content. Group branch files by their base block.
3. **Apply the per-call cap:** process at most `maintenance.max_blocks_per_call` blocks (default
   10) in this invocation. This keeps the synchronous call comfortably under the MCP tool-call
   timeout even when many branches have accumulated (each block's semantic merge costs a sub-agent
   invocation, ~30s). If blocks remain after the cap, return `more_pending: true` and let the LLM
   call again. (Alternatives considered and rejected for v1: routing maintenance through the async
   job infrastructure of [Section 3.20](#320-async-executor) — adds polling complexity; fully
   synchronous with no cap — risks timeouts on large batches. Decision record: update plan §3.1.)
4. **For each selected block,** run the merge process of
   [Section 3.17](#317-merge-process-and-merge-mutex): acquire the merge mutex, semantically merge
   the base and all its branches via an LLM sub-agent, atomically replace the base, delete the
   branch files, clear all branch-map entries for the block, release the mutex. A per-block
   failure (sub-agent error, malformed output) leaves that block's base and branches untouched,
   records an entry in `errors`, and continues with the next block.
5. **Handle cleanup sweep** ([Section 3.14](#314-handle-management)): after the merge pass, evict
   every handle that owns zero branches and has been inactive past the retention window. Also drop
   read baselines that reference blocks which no longer exist.
6. Write a persistence checkpoint and return.

**Behavior with no pending branches:** returns `{ ok: true, merged_blocks: 0, more_pending: false }`
immediately (the cleanup sweep still runs — it is cheap).

**Partial / targeted maintenance** (merging a single named block) is not supported in v1; the call
always processes everything pending, up to the cap. A `block_name` parameter is a v1.x option if it
proves useful.

**Concurrency:** if the user triggers maintenance while other conversations are active, those
conversations' memory tool calls block on the merge mutex for the duration of each block's merge.
This is acceptable for v1 — the user chooses when to run maintenance and can pick an idle moment.
The skill mentions the brief blocking so the LLM can set expectations
([Chapter 5](stateful-agent-design-chapter5.md)). If blocking on the mutex would exceed an
acceptable wait, the bridge returns `MAINTENANCE_IN_PROGRESS` to the blocked caller rather than
hanging the tool call indefinitely; the message instructs the LLM to retry shortly.

### 3.14 Handle Management

The handle is the bridge's identifier for a conversation. It replaces the v1 session ID, and the
per-handle state replaces the v1 session tracker.

**Format.** Handles are **8 lowercase alphanumeric characters** (alphabet `[a-z0-9]`, ~2.8 × 10¹²
possibilities), e.g., `h7k3xy90`. The length costs a few tokens per response (the handle is echoed
in every memory tool response) and makes collisions astronomically unlikely even across bridge
restarts and long-lived conversations.

**Generation.** The bridge mints handles; the LLM never invents one. v1 uses a standard PRNG
(`math/rand`, seeded at bridge startup) plus the collision check in
[Section 3.8](#38-tool-memory_start_conversation). The probability of meaningful collisions with
PRNG output at this handle length is negligible for the expected workload, and an unprivileged LLM
has no way to predict or attack handle values through the MCP interface. **Future improvement:**
upgrade to a CSPRNG (`crypto/rand`) if the threat model grows to include adversarial scenarios —
e.g., if memory ever becomes accessible to untrusted parties. Noted here so it isn't forgotten.

**Per-handle state.** For each live handle the bridge tracks:

```go
type HandleState struct {
    Branches      map[string]string     // block name → branch file path (Section 3.15)
    Baselines     map[string]Signature  // block name → signature of content last
                                        //   returned to this handle (ModTime + size)
    LastActivity  time.Time             // updated on every memory tool call
}

type HandleMap struct {
    mu      sync.Mutex
    handles map[string]*HandleState     // handle → state
}
```

This state is persisted across bridge restarts in `.bridge-state.json`
([Section 3.18](#318-bridge-state-persistence-and-recovery)), so a handle issued in one Claude
Desktop session is still valid — with its full branch map and read baselines — after the app is
closed and reopened.

**Handle is a required parameter with no graceful re-init.** Every memory tool declares `handle`
as required in its MCP schema, so an omitted handle is rejected by schema validation before the
call reaches the bridge. The bridge itself rejects malformed and unrecognized handles with errors;
it never silently registers an unknown handle. The error-and-recover model keeps the bridge simple
and the semantics predictable: the SKILL teaches one uniform recovery for *any* handle problem —
**call `memory_start_conversation` to obtain a fresh handle and retry**. (Decision record: update
plan §3.3.)

**The unknown-handle procedure.** With persistence in place, a handle from a prior Claude Desktop
session is normally already in the map after the startup load — the path below is the exception,
not the rule:

1. If the handle is malformed (wrong length or character set), return `MALFORMED_HANDLE`
   immediately — no adoption attempt.
2. If the handle is well-formed but not in the in-memory map, scan the memory directory for branch
   files matching `*.branch-<handle>-*.<ext>` (**lazy adoption**, the reconciliation backstop —
   see [Section 3.18](#318-bridge-state-persistence-and-recovery)).
3. If any branch files match, reconstruct the corresponding `(handle, block) → branch path`
   entries, treat the handle as live, and proceed with the original tool call. Read baselines
   cannot be reconstructed from disk, so the handle's first read of each target sets a fresh
   baseline with `changed_since_last_read: false` (same as a brand-new handle).
4. If no branch files match, return `INVALID_HANDLE`.

**Failure modes and recovery:**

| Scenario | What happens |
|---|---|
| Handle omitted from tool call | MCP schema validation rejects; LLM calls `memory_start_conversation`, retries |
| Handle malformed | Bridge returns `MALFORMED_HANDLE`; LLM recovers the same way |
| Bridge restarted between calls (normal case) | Handle recovered from the persisted state with full branch map and read baselines; no error, no degradation |
| Bridge restarted, state file missing/corrupt, conversation had created branches | Lazy adoption recovers the branch map (baselines lost); call proceeds; degraded but functional |
| Bridge restarted, state file missing/corrupt, conversation never branched | Bridge returns `INVALID_HANDLE`; LLM recovers via `memory_start_conversation`; no data lost (base writes are visible to anyone reading the base) |
| Compaction wipes recent responses but an older response with the handle survives | No error; the handle is still valid |
| Compaction wipes every memory tool response including the original `memory_start_conversation` | LLM has no handle; calls `memory_start_conversation` on its next memory operation and continues with a fresh one |
| LLM fabricates a handle | Not in the map; lazy-adoption scan finds nothing; `INVALID_HANDLE`; LLM recovers the same way |
| Handle evicted by the cleanup policy, then presented again much later | Treated as unknown; lazy adoption finds no branches (eviction requires zero branches); `INVALID_HANDLE`; LLM recovers the same way; no data lost |

**Handle lifetime and cleanup** (decision record: update plan §3.7). With persistence, handles
live across restarts, so the persisted state file must be bounded. A handle is eligible for
eviction when **both** hold:

1. **It owns no branches** — all merged away by maintenance, or it never created any. A handle
   with live branches must never be evicted: that would orphan its branch files and break
   read-your-own-writes for its conversation.
2. **It has been inactive longer than the retention window** — `handle.retention_days`, default
   60 days since its last memory tool call. Baselines for a handle idle that long are very
   unlikely to ever be consulted again.

Cleanup runs as the final sweep of every `memory_run_maintenance` call
([Section 3.13](#313-tool-memory_run_maintenance)) — no separate timer, no background thread, the
same user-controlled cadence as merging. Eviction removes the handle's entry from the in-memory
map and from the next persisted write; it loses no data because an evictable handle had no
branches by definition. The retention window is configurable: a user running many concurrent
conversations might want it shorter; one who returns to old conversations, longer. Deferred to
v1.x: a hard LRU cap on handle count as a backstop, and incremental (append-log) persistence if
whole-file rewrites ever become a bottleneck.

### 3.15 Per-Handle Branching and Race Detection

Branching is the mechanism that resolves the concurrent read-modify-write race condition without
ever involving the LLM. When a write from one conversation would overwrite changes another
conversation made since the writer last read the target, the bridge transparently redirects the
write to a per-handle **branch file**. The base file is left unmodified; the writer's conversation
continues to see (and build on) its own writes; the other conversation's data is preserved; and a
later maintenance run semantically merges everything back together.

**Branches are invisible to the LLM.** The LLM never sees branch filenames, never participates in
race detection, and is never told a branch exists. From its perspective, every read returns *the*
current state of a target and every write succeeds. There is no `branch_created` flag in any
response, no branch content in any read, and no branch vocabulary in any error message. This is
the load-bearing abstraction of the redesign: the v1 design returned branch content to the LLM
(annotated) and relied on skill instructions to interpret it; the memory-aware design handles the
entire branch lifecycle in code.

**The per-handle branch map.** The bridge maintains, per handle, the map
`block name → branch file path` (part of `HandleState`, [Section 3.14](#314-handle-management)).
An entry `(H, B)` means handle H has diverged from the base of B and owns a private branch of it.

**Read routing** for `memory_get_*` from handle H on target B:

- If the branch map has an entry for `(H, B)`: return the contents of that branch file.
- Otherwise: return the contents of the canonical (base) file.

**Write routing** for `memory_write_*` from handle H on target B:

- If the branch map has an entry for `(H, B)`: write to that branch file. No race detection is
  needed — H already owns this branch, and nobody else writes to it.
- Otherwise, compare the base file's current signature (ModTime + size) against H's read baseline
  for B:
  - **Signatures match (no race):** write to the base file.
  - **Signatures differ (race):** create a new branch file
    (`B.branch-<H>-<timestamp>.<ext>`), record it in the branch map at `(H, B)`, trigger an
    immediate persistence checkpoint (branch-map entries are the most important state not to
    lose), and write to the branch.
  - **H has no baseline for B and the base exists:** treated as a race — another conversation
    created or modified the file since H could have seen it. This covers the simultaneous
    first-write scenario where two conversations independently create the same new block: the
    second writer branches rather than silently overwriting the first.
  - **The base does not exist:** true first-ever creation; no race is possible; create the base.

This is the mechanism by which **read-your-own-writes** is preserved: once H's write to B lands in
a branch, all subsequent reads and writes from H on B route through that branch. Other
conversations continue to see the base.

**No branches of branches.** Once a branch exists for `(H, B)`, all future operations from H on B
reuse it. A branch is never itself branched. The storage model stays flat: at any moment, a block
has zero or more *peer* branches, each owned by exactly one handle.

**Appends never create branches** — see
[Section 3.11](#311-tools-memory_get_block-memory_write_block-memory_append_block) for the
serialized-append semantics and the branch-routing rule for handles that already own a branch.

**When branching does NOT occur:** if `branching.enabled` is `false` in the config (a debugging
escape hatch), all writes use last-writer-wins semantics and no branches are created. If the
signatures match, no race has occurred and the write proceeds to the base normally.

**Branch file naming convention** (decision record: update plan §3.8):

```
<basename>.branch-<handle>-<ISO8601compact-UTC>.<ext>
```

Examples:
- `core.md` → `core.branch-h7k3xy90-20260520T142300Z.md`
- `blocks\project-mcp-bridge.md` → `blocks\project-mcp-bridge.branch-ab12cd34-20260601T091500Z.md`

The convention is designed to be:

- **Handle-embedding** — the owning handle appears in the filename, which (a) makes the
  filesystem a partial backing store for the branch map, enabling the lazy-adoption recovery
  backstop ([Section 3.18](#318-bridge-state-persistence-and-recovery)), and (b) makes branches
  attributable by inspection: a human can see which conversation owns each branch. The handle
  replaces the random hex suffix of the v1 convention with something meaningful. **Any future
  change to this convention must preserve handle-recoverability from the filename, or accept that
  lazy adoption stops working** (the persisted-state path would still function).
- **Parseable** — `*.branch-<handle>-*.<ext>` globbing identifies a handle's branches; the handle
  is the lookup key.
- **Windows-safe** — see the timestamp format below.

**The embedded timestamp — what it means and how it behaves:**

- **It is the branch's creation time** — the moment the bridge created the branch in response to
  the first racing write for that `(handle, block)` pair.
- **It is frozen at creation and never updated.** All subsequent writes by the same handle update
  the branch's *contents*, not its *filename* (no branches of branches). The embedded timestamp
  therefore means "when this conversation first diverged from the base," not "when the branch was
  last modified" — last-modified comes from the filesystem's own mtime. This split is deliberate:
  the bridge never has to rename a branch file (renaming on every write would add complexity and
  could race with a lazy-adoption scan mid-rename).
- **It is purely informational, for human debugging.** The bridge never parses or compares it;
  lazy adoption matches by handle, and uniqueness is already guaranteed by the
  `(handle, block)` pair. It is an annotation, not a key.

**Timestamp format — compact UTC with seconds and a `Z` suffix** (e.g., `20260520T142300Z`,
meaning 2026-05-20 14:23:00 UTC):

- **Compact (basic) ISO 8601**, not extended: no hyphens between date parts, no colons between
  time parts, literal `T` separator retained. Colons are illegal in Windows filenames, and the
  extended form's internal hyphens would collide — visually and programmatically — with the
  hyphens this filename uses as its own field separators (`branch` - `<handle>` - `<timestamp>`).
- **UTC with a trailing `Z`**: filename-safe (just a letter) and removes daylight-saving and
  timezone ambiguity. The small loss of at-a-glance local readability is acceptable for a debug
  annotation.
- **Seconds included**: cheap, improves debug precision, removes same-minute ambiguity.

**On-disk layout:** branches sit alongside their base files in the same directory (memory root
for core, blocks directory for blocks). The layout is bridge-internal; the skill never references
it.

**Expected frequency:** branching only occurs when two conversations are active simultaneously
*and* both modify the same target after overlapping reads. The typical usage pattern — one active
conversation at a time — produces zero branches.

### 3.16 Block File Format and Atomic Writes

**Block file format on disk.** Every block file carries YAML frontmatter holding the block's
index metadata, followed by the markdown body:

```yaml
---
summary: "Discussion of the X feature design"
updated_at: 2026-05-20T14:23:00Z
---
# Markdown body of the block goes here
...
```

The bridge manages the frontmatter transparently: `memory_get_block` strips it and returns only
the body; `memory_write_block` composes frontmatter (new or preserved `summary`, `updated_at` set
to now) plus the provided body and writes them as one file. The LLM never sees frontmatter. A
human can — the metadata is inspectable at the top of any block file in a text editor.

Core (`core.md`) is the exception: it has **no frontmatter**. It is always loaded in full and
does not appear in the index, so it needs no machine-readable metadata.

**Schema evolution:** YAML frontmatter is naturally extensible. Adding fields (e.g., `importance`
per [Chapter 9, Section 9.7](stateful-agent-design-chapter9.md#97-importance-scoring-on-blocks-and-episodic-entries))
is backwards-compatible. Removing or renaming fields requires a migration sweep at bridge startup.

**Atomic write procedure.** With the index folded into block files, the v1 problem of atomically
coordinating a block write with an index write reduces to an atomic *single-file* write — solvable
with the standard temp-and-rename approach:

1. Determine the target file: base or branch for this handle, per
   [Section 3.15](#315-per-handle-branching-and-race-detection).
2. Compose the file content: frontmatter (`updated_at` = now; `summary` = the provided value, or
   the previous summary preserved) plus the body. (For core: just the body.)
3. Write the composed content to a temp file alongside the target (e.g., `<name>.md.tmp.<random>`),
   in the same directory to guarantee a same-filesystem rename.
4. `fsync` the temp file.
5. Atomically rename temp → target.

There is no second file to keep in sync: frontmatter and body are written together, so they can
never diverge. This is materially simpler than the v1 design, which had to coordinate a block
write with an `index.md` write; the simpler invariant is easier to verify and to recover.

**Windows rename caveat:** `os.Rename` cannot atomically overwrite an existing file on all Windows
filesystems. The v1-proven approach applies: remove the target if it exists, then rename — an
acceptably tiny non-existence window given mutex-serialized, low-frequency writes. If true
atomicity is needed later, the Windows `ReplaceFile` API can be called via `syscall`.

**Crash recovery (startup sweeper):**

- Orphan temp files (`*.tmp.*`) older than a few seconds are deleted at bridge startup.
- Branch files on disk that the loaded persisted state doesn't know about are picked up by the
  startup lazy-adoption pass ([Section 3.18](#318-bridge-state-persistence-and-recovery)); branch
  files whose handles are gone entirely simply wait for the next `memory_run_maintenance`, which
  enumerates all branches on disk regardless of handle liveness. Data is preserved either way.
- Block files missing required frontmatter (e.g., hand-edited by the user without preserving it)
  get default frontmatter inserted on the next read or scheduled write — the bridge neither
  silently loses the data nor refuses to read it. The default summary is derived mechanically
  (e.g., the first heading or first line, truncated).

### 3.17 Merge Process and Merge Mutex

The merge is the maintenance-time action that folds a block's peer branches back into a single
canonical base. It runs only inside `memory_run_maintenance`
([Section 3.13](#313-tool-memory_run_maintenance)). For each block with pending branches:

1. **Select** all peer branches of base block B, along with B itself.
2. **Acquire the merge mutex**, blocking all other memory I/O for the duration of this block's
   merge (see below).
3. **Merge semantically via an LLM sub-agent.** The bridge invokes a sub-agent (a separate
   `claude -p` process, reusing the spawn machinery internally) with the base content and all
   branch contents, instructed to produce a single unified document. This is a *semantic* merge,
   not a textual three-way merge: memory files are prose markdown, and a line-based merge would
   produce incoherent results when two conversations independently rewrote the same paragraph.
   The merger identifies what is unique to each version, what is shared, and what conflicts; for
   conflicts (e.g., two different status updates for the same project), the chronologically
   latest version is authoritative, but earlier information is preserved when it contains facts
   absent from the later version. Branch creation timestamps (from filenames) and file mtimes
   establish chronology. Simple merges (e.g., different episodic additions) can use a cheaper
   model (Sonnet or Haiku); complex merges of `core.md` may warrant Opus.
4. **Regenerate frontmatter.** The merged file's `summary` is typically derived by the sub-agent
   from the merged body; `updated_at` is set to the merge time. (Core has no frontmatter.)
5. **Atomically replace** the base file with the merged result
   ([Section 3.16](#316-block-file-format-and-atomic-writes)).
6. **Delete** all branch files for B.
7. **Clear** all branch-map entries `(*, B)` so future reads from every handle see the merged
   base. Handles whose branches were merged away simply route back to the base; their read
   baselines are refreshed on their next read.
8. **Release the mutex.**

The merge work runs in sub-agents — separate LLM invocations dispatched by the bridge — not in the
calling conversation's reasoning context, so the calling LLM never reasons about merge content. But
the `memory_run_maintenance` call itself is **synchronous**: it returns only after the selected
blocks' merges complete (bounded by the per-call cap of [Section 3.13](#313-tool-memory_run_maintenance)).

Note that this preserves the **single-writer model**: the merge sub-agent produces merged
*content*, but the bridge itself performs the file replacement. Sub-agents still never write to
memory (see [Chapter 6, Section 6.6](stateful-agent-design-chapter6.md#66-sub-agent-memory-access-rules)).

**The merge mutex.** While a block's merge is in progress, the bridge holds a lock that blocks
all `memory_*` tool calls touching that block — preventing new branches from being created
mid-merge and preventing reads from observing partial merge state. For v1 simplicity, the lock is
the existing process-wide memory mutex held for the duration of each block's merge; a
finer-grained per-block lock is a future optimization. Because merges run only when the user
invokes maintenance — typically at a moment chosen for the purpose — the practical impact of
process-wide locking is small. A blocked caller that would wait unacceptably long receives
`MAINTENANCE_IN_PROGRESS` ([Section 3.19](#319-error-response-convention)) rather than hanging.

**The memory mutex (ordinary operation).** Outside of merges, all memory tool handlers serialize
on a single process-wide `sync.Mutex` (`memmutex.go`), exactly as in v1: reads acquire it so the
signature recorded for a read is consistent with the content returned; writes acquire it so
signature-compare-then-write sequences are atomic with respect to other conversations. A single
mutex (rather than per-file locks) keeps the implementation trivial and deadlock-free; memory I/O
is infrequent and sub-millisecond, so the serialization cost is negligible.

### 3.18 Bridge State Persistence and Recovery

The bridge persists its in-memory state to disk and reloads it at startup. Motivation: the bridge
is spawned by Claude Desktop over stdio and **terminates on every Claude Desktop close**
([Section 3.24](#324-graceful-shutdown)) — so in-memory-only state would be discarded routinely,
not rarely. Without persistence, every close-reopen cycle would degrade race detection and the
`changed_since_last_read` flag (read baselines are not recoverable from disk). With persistence, a
restart is transparent. (Decision record: update plan §2.12, which superseded an earlier
in-memory-only decision.)

**What is persisted** — the three pieces of per-conversation state the bridge tracks, plus the
bookkeeping needed by the eviction policy:

1. The set of live handles, each with its last-activity time
   ([Section 3.14](#314-handle-management)).
2. The per-handle branch map (`handle → block name → branch file path`).
3. The per-handle read baselines (`handle → block name → content signature`).

The branch *files* themselves remain the source of truth for branch content; the state file
records only the mapping and metadata. Because branch filenames also embed the handle
([Section 3.15](#315-per-handle-branching-and-race-detection)), the branch→handle association is
independently recoverable from disk even if the state file is lost — which is exactly what makes
lazy adoption a viable backstop.

**Storage location and format.** A single JSON file in the memory root, named
`.bridge-state.json` (leading dot so it sorts away from memory content and is visually distinct
from blocks). It is bridge-private: neither the LLM nor the SKILL ever references it, and it is
not memory content.

**Write strategy:**

- **On clean shutdown**, when the bridge detects EOF on stdin (the normal Claude Desktop close
  path — [Section 3.24](#324-graceful-shutdown)). This is the common case and captures the most
  recent state.
- **Debounced checkpoints during operation:** state-changing operations mark the state dirty;
  changes are coalesced and flushed at most once per `persistence.checkpoint_interval_seconds`
  (default 5), so a burst of writes doesn't cause a burst of disk I/O. **Branch creation triggers
  an immediate checkpoint** — the branch-map entry is the most important state not to lose, since
  losing it (plus the state file) is what creates recovery work.
- **Whole-file rewrite each time**, via the same temp-file-plus-atomic-rename pattern as block
  writes ([Section 3.16](#316-block-file-format-and-atomic-writes)), so a crash mid-write cannot
  corrupt the file. For the expected state size (at most a few hundred handles, each small) a
  whole-file JSON rewrite is well under a millisecond; incremental/append-based persistence is a
  v1.x optimization.

**Load and reconcile at startup:**

1. Load `.bridge-state.json` if present.
2. **Reconcile against the filesystem:** for each persisted branch-map entry, verify the
   referenced branch file still exists; drop entries whose files are gone (e.g., merged away by a
   maintenance run from a different bridge instance — rare in a single-bridge deployment).
3. **Run lazy adoption as a backstop:** scan the memory directory for branch files *not*
   represented in the loaded state and rebuild map entries for them from the handle embedded in
   each filename. This covers a stale state file (branch created after the last checkpoint), a
   missing one, and a corrupt one.

**Persistence is the primary recovery mechanism; lazy adoption is the reconciliation backstop.**
Lazy adoption runs in two places: the startup pass above, and the unknown-handle path of
[Section 3.14](#314-handle-management) (a well-formed handle absent from the loaded state). What
lazy adoption can recover is the branch map — the handle→branch association is in the filenames.
What it cannot recover is read baselines, which exist only in the state file; after
adoption-without-state, the affected handle's first read of each target sets a fresh baseline
(`changed_since_last_read: false`, matching a fresh handle), and its first write may miss one race
(one cross-conversation overwrite per restart per affected block — bounded and small; the stricter
alternative of always branching the first post-recovery write would produce spurious branches
every restart, costing more than it gains). The system therefore recovers full state in the normal
case and degrades gracefully — never below the pre-persistence design — when the state file is
unavailable.

**Corruption handling.** If `.bridge-state.json` is present but unparseable, the bridge logs the
problem to its server-side log, discards the corrupt file, and falls back to pure lazy adoption.
The bridge is never worse off than a lazy-adoption-only design, even in the corruption case.

**Eviction interplay:** the cleanup sweep of [Section 3.14](#314-handle-management) removes
evicted handles from the in-memory map; they disappear from the state file at its next write.

### 3.19 Error Response Convention

Traditional programming APIs tended toward terse, machine-only error codes (`ENOENT`) because the
consumer was other code that couldn't usefully act on free-form text. LLMs collapse that gap — the
error *message* itself is the recovery instruction. The bridge's memory tools therefore return
errors with both a stable machine-readable code and a natural-language message. (Decision record:
update plan §3.10.)

**Schema:**

```
{
  "handle": "abc1def2",     // echoed back if a handle was supplied and is recognized;
                            //   omitted or null if the error was a handle problem
  "ok": false,
  "error": {
    "code": "INVALID_HANDLE",         // stable identifier; never changes between bridge versions
    "message": "Handle 'xy77abcd' is not recognized. Call memory_start_conversation to obtain a fresh handle and retry.",
    "context": { "supplied_handle": "xy77abcd" }   // optional; included only when useful for diagnosis
  }
}
```

**Why both `code` and `message`:**

- The `message` gives the LLM a natural-language explanation it can act on directly, without the
  SKILL having to enumerate every error code and recovery procedure.
- The `code` stays stable across message rewordings. Tests, future tooling, and automated handling
  can rely on `INVALID_HANDLE` even if the message text is later improved, and the code is
  grep-able in server logs without false matches.

**Abstraction discipline (critical):** error messages must respect the layers established by the
design. The LLM operates on *handles*, *core*, *blocks*, *summaries*, and *the index*. Branches,
mutexes, frontmatter, file paths, the branch map, and every other implementation detail are
bridge-internal and must not appear in error messages.

Good error messages:
- ✅ `"Block 'foo' does not exist for this handle"` — speaks at the block abstraction.
- ✅ `"Handle 'xy77abcd' is not recognized. Call memory_start_conversation."` — gives the recovery path.
- ✅ `"Summary is required when creating a new block"` — explains the contract.
- ✅ `"Block name 'foo bar' contains invalid characters; use letters, digits, hyphens, and underscores"` — actionable correction.

Bad error messages (leak the design):
- ❌ `"Branch 'foo.branch-h7k3xy90-...' already exists"`
- ❌ `"Cannot acquire merge mutex; try again"`
- ❌ `"Frontmatter parse failed at line 3"`
- ❌ `"Failed to atomic-rename temp file"`

For internal errors the LLM cannot recover from (disk failure, invariant violation, sub-agent
merge failure), the message stays generic — *"An internal bridge error occurred; the operation was
not completed. Please report this to the user."* — and the technical detail goes to the
server-side log file ([Section 3.22](#322-logging)) for the user to inspect when debugging.

**Initial error code set** (a starting point, not exhaustive; new codes are added as new error
situations are identified):

| Code | Meaning |
|---|---|
| `INVALID_HANDLE` | Handle present and well-formed but not recognized by the bridge (after the lazy-adoption check) |
| `MALFORMED_HANDLE` | Handle present but the format is wrong (length, character set) |
| `BLOCK_NOT_FOUND` | Read or operation targets a block that doesn't exist for this handle |
| `INVALID_BLOCK_NAME` | Block name contains disallowed characters or violates naming rules |
| `SUMMARY_REQUIRED` | `memory_write_block` called for a new block without a `summary` argument |
| `SUMMARY_TOO_LONG` | `summary` exceeds the configured length cap |
| `MAINTENANCE_IN_PROGRESS` | The bridge is currently consolidating memory; the operation should be retried shortly (returned instead of blocking on the merge mutex past an acceptable wait) |
| `INTERNAL_ERROR` | Catch-all; the message stays generic; details go to the server log |

**Schema-validation errors:** if MCP itself rejects a call (e.g., the required `handle` parameter
omitted), the error shape is whatever MCP returns and is not under the bridge's control. The SKILL
teaches one recovery for any handle-related rejection — schema-level or bridge-issued: call
`memory_start_conversation`, retry.

### 3.20 Async Executor

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

### 3.21 Job Lifecycle Manager

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

### 3.22 Logging

All bridge operations are logged to a file for auditability and debugging. Logging does **not** go to stdout/stderr (those are reserved for MCP stdio transport).

**What to log:**

| Event | Level | Fields |
|-------|-------|--------|
| Bridge started | info | config path, version, state file loaded (yes/no), handles recovered, branches adopted at startup |
| Tool call received | info | tool name, abbreviated params |
| spawn_agent: subprocess launched | info | job_id (if async), model, working_dir |
| spawn_agent: sync completion | info | elapsed time, output size |
| spawn_agent: async handoff | info | job_id, elapsed time at handoff |
| run_command: command executed | info | command (first 200 chars), working_dir, timeout |
| run_command: sync completion | info | exit_code, elapsed time, output size, truncated |
| run_command: async handoff | info | job_id, command (first 200 chars), elapsed time at handoff |
| check_agent: status poll | debug | job_id, source, status, elapsed |
| check_agent: result collected | info | job_id, source, status, elapsed, output size |
| memory_start_conversation: handle minted | info | handle |
| memory_get_core / memory_get_block: read | info | handle, target, branch-or-base, bytes returned, changed_since_last_read |
| memory_write_core / memory_write_block: write | info | handle, target, branch-or-base, bytes written |
| Race detected → branch created | warn | handle, target, branch filename |
| memory_append_block / memory_append_episodic: append | info | handle, target, bytes appended |
| memory_get_index: assembled | debug | handle, block count, cache hit/miss |
| Lazy adoption: branches adopted | info | handle, branch filenames adopted |
| memory_run_maintenance: pass complete | info | handle, blocks merged, branches deleted, handles evicted, more_pending |
| Merge sub-agent dispatched / completed / failed | info / info / error | block, branch count, elapsed, error details on failure |
| State checkpoint written | debug | bytes, handles persisted |
| State file corrupt at startup | error | parse error details; fallback to lazy adoption |
| Job expired | warn | job_id, reason |
| Sub-agent killed (timeout) | warn | job_id, elapsed |
| Error (any) | error | tool name, error code, error details |
| Bridge shutdown | info | active jobs killed, final state checkpoint written |

Note that branch filenames, frontmatter problems, and other implementation details **do** appear
in the log — the abstraction discipline of [Section 3.19](#319-error-response-convention) applies
to tool responses, not to the server-side log, which exists precisely so the user can see the
machinery when debugging.

**Format:** Structured JSON lines (one JSON object per log line). This is easy to parse, grep, and pipe into log aggregation tools.

```json
{"ts":"2026-06-12T14:30:00Z","level":"warn","msg":"race detected: branch created","handle":"h7k3xy90","target":"project-foo","branch":"project-foo.branch-h7k3xy90-20260612T143000Z.md"}
```

### 3.23 Error Handling

The bridge should never crash from a tool call. All errors are caught and returned as MCP tool errors — memory tool errors follow the convention in [Section 3.19](#319-error-response-convention).

**Error categories:**

| Category | Example | Behavior |
|----------|---------|----------|
| Configuration error | Missing config file, invalid YAML | Bridge fails to start with clear error message |
| Tool input validation | Missing required param | MCP schema validation rejects before the bridge sees the call |
| Subprocess launch failure | `claude` not found, shell not found, permission denied | Return MCP tool error with details |
| Subprocess timeout | Sub-agent or command exceeds `timeout_seconds` | Kill process, return `timed_out` status via `check_agent` |
| Subprocess crash | `claude -p` or shell command exits with non-zero | Return output + exit code via `result` field |
| Shell not found | Configured `run_command.shell` path doesn't exist | Return MCP tool error; verify Cygwin installation |
| Handle malformed | Wrong length or character set | `MALFORMED_HANDLE` per Section 3.19 |
| Handle unknown | Not in map; lazy adoption found nothing | `INVALID_HANDLE` per Section 3.19 |
| Block not found / bad name | Read of missing block; invalid characters in name | `BLOCK_NOT_FOUND` / `INVALID_BLOCK_NAME` |
| Summary contract violation | New block without summary; over-length summary | `SUMMARY_REQUIRED` / `SUMMARY_TOO_LONG` |
| Maintenance contention | Memory call would block too long on the merge mutex | `MAINTENANCE_IN_PROGRESS`; LLM retries shortly |
| Concurrent agent cap reached | 5 sub-agents already running | Return MCP tool error suggesting the user wait or check existing jobs |
| File I/O error, merge sub-agent failure, invariant violation | Permission denied, disk full, malformed merge output | `INTERNAL_ERROR` with a generic message; details to the server log; for merge failures, the affected base and branches are left untouched |

### 3.24 Graceful Shutdown

The bridge runs as a subprocess of Claude Desktop, communicating over stdio (stdin/stdout). When Claude Desktop *exits* (not merely when a conversation is closed — the bridge persists for the full desktop session), it closes the stdin pipe. **Stdin EOF is the authoritative shutdown signal** for the bridge — it is the only shutdown mechanism that works reliably on Windows and is consistent with the MCP stdio transport model.

Note: UNIX signals are not used for shutdown. On Windows, SIGTERM does not exist as an inter-process signal, and SIGINT is only available when a console window is present (Ctrl+C). Since the bridge runs as a background stdio subprocess with no attached console, neither signal is reliably deliverable. Stdin EOF is the correct and portable mechanism.

**Shutdown sequence when stdin EOF is detected:**

1. The `mcp-go` SDK's stdio read loop detects EOF on stdin and exits naturally.
2. The bridge detects the loop exit and begins shutdown.
3. **Write the final state checkpoint** to `.bridge-state.json` (atomic temp + rename, per [Section 3.18](#318-bridge-state-persistence-and-recovery)). This is the primary persistence write — it captures the live handles, branch map, and read baselines so the next bridge instance recovers transparently.
4. Kill all running subprocesses — both sub-agents (from `spawn_agent`) and shell commands (from `run_command`) — by calling `Process.Kill()` on each active job. On Windows, this calls `TerminateProcess` immediately; there is no SIGTERM grace period. (A merge sub-agent killed mid-merge leaves its block's base and branches untouched — merges only replace the base as the final atomic step — so the merge simply reruns at the next maintenance call.)
5. Log the shutdown, the state write, and the number of jobs terminated.
6. Exit cleanly.

**Pseudo-code:**

```
func main():
    // ... setup: load config, load + reconcile persisted state (Section 3.18),
    //     run startup sweeper (Section 3.16), register tools ...

    // Start the MCP stdio server. This blocks until stdin is closed (EOF),
    // which happens when Claude Desktop exits or kills the bridge process.
    // The mcp-go SDK handles the stdio read/write loop internally.
    server.Run()  // returns when stdin closes

    // Stdin EOF received — begin graceful shutdown
    persistence.WriteFinalCheckpoint()  // atomic write of .bridge-state.json
    log.Info("Stdin EOF detected, killing %d active jobs", jobManager.ActiveCount())
    jobManager.KillAll()  // calls Process.Kill() on all running subprocesses
    os.Exit(0)
```
