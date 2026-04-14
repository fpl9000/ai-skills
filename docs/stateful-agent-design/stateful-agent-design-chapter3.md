# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Contents

- [3. MCP Bridge Server](#3-mcp-bridge-server)
  - [3.1 Go Module Structure](#31-go-module-structure)
  - [3.2 Configuration](#32-configuration)
  - [3.3 Tool Summary](#33-tool-summary)
  - [3.4 Tool: spawn_agent](#34-tool-spawn_agent)
  - [3.5 Tool: check_agent](#35-tool-check_agent)
  - [3.6 Tool: run_command](#36-tool-run_command)
  - [3.7 Tool: memory_session_start](#37-tool-memory_session_start)
  - [3.8 Tool: safe_read_file](#38-tool-safe_read_file)
  - [3.9 Tool: safe_write_file](#39-tool-safe_write_file)
  - [3.10 Tool: safe_append_file](#310-tool-safe_append_file)
  - [3.11 Write Mutex and Session Tracking](#311-write-mutex-and-session-tracking)
  - [3.12 Branching](#312-branching)
  - [3.13 Async Executor](#313-async-executor)
  - [3.14 Job Lifecycle Manager](#314-job-lifecycle-manager)
  - [3.15 Logging](#315-logging)
  - [3.16 Error Handling](#316-error-handling)
  - [3.17 Graceful Shutdown](#317-graceful-shutdown)

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
