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
  - [3.7 Tool: safe_write_file](#37-tool-safe_write_file)
  - [3.8 Tool: safe_append_file](#38-tool-safe_append_file)
  - [3.9 Write Mutex](#39-write-mutex)
  - [3.10 Async Executor](#310-async-executor)
  - [3.11 Job Lifecycle Manager](#311-job-lifecycle-manager)
  - [3.12 Logging](#312-logging)
  - [3.13 Error Handling](#313-error-handling)
  - [3.14 Graceful Shutdown](#314-graceful-shutdown)

## 3. MCP Bridge Server

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
├── safe_write.go             # safe_write_file tool handler (mutex-protected atomic write)
├── safe_append.go            # safe_append_file tool handler (mutex-protected append)
├── writemutex.go             # Write mutex shared by safe_write_file and safe_append_file
├── jobs.go                   # Job lifecycle manager (background goroutine)
├── logging.go                # Structured logging to file
└── bridge-config.yaml        # Default configuration (embedded or external)
```

**Dependencies:**
- `github.com/mark3labs/mcp-go` — MCP SDK for Go (stdio transport, tool registration)
- Go standard library — everything else (os/exec, sync, time, encoding/json, log, filepath)

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

# Memory directory (used by safe_write_file and safe_append_file for path validation)
memory:
  directory: "C:\\franl\\.claude-agent-memory"

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
| `spawn_agent` | `spawn_agent` | Launch a sub-agent (`claude -p`) with a task. Returns result (sync) or job_id (async). |
| `check_agent` | `check_agent` | Poll a running async job by job_id. Returns status and result. Used for both `spawn_agent` and `run_command` async jobs. |
| `run_command` | `run_command` | Execute a shell command on the local machine. No LLM involved — direct subprocess execution. Uses the same hybrid sync/async model as `spawn_agent`. Far cheaper than spawning a sub-agent for simple commands. |
| `safe_write_file` | `safe_write_file` | Mutex-protected atomic write (full file replacement) for memory files. Uses temp-file-then-rename. |
| `safe_append_file` | `safe_append_file` | Mutex-protected append for memory files. Primary use: episodic log entries. |

### 3.4 Tool: spawn_agent

This is the most complex tool in the bridge. It launches a Claude Code CLI sub-agent with a task. The subprocess lifecycle (sync window, async handoff, output truncation) is managed by the shared async executor (see [Section 3.10](#310-async-executor)).

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

This tool executes a shell command on the local machine and returns its output. No LLM is involved — this is direct subprocess execution, making it dramatically cheaper than `spawn_agent` for simple operations like `curl`, `git status`, `grep`, `find`, `cat`, `ls`, directory listings, and short scripts. It uses the same hybrid sync/async model as `spawn_agent` via the shared async executor (see [Section 3.10](#310-async-executor)), so long-running commands (e.g., a recursive `grep` of a large codebase) are handled correctly without hitting the MCP timeout.

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

### 3.7 Tool: safe_write_file

This tool performs a mutex-protected, atomic full-file write. It is the primary tool for updating memory files (`core.md`, `index.md`, content blocks). It replaces the use of `Filesystem:write_file` and `Filesystem:edit_file` for all memory operations.

**Why not use the Filesystem extension's `write_file`?** Three reasons: (a) the Filesystem extension has no mutex — two concurrent conversations writing to the same memory file can interleave, with the second write silently clobbering the first; (b) `safe_write_file` is scoped to the memory directory, providing the "unambiguous tool names" benefit from proposal Open Question #22 — Claude can't accidentally use it to write to the cloud VM or to non-memory locations; (c) atomic write via temp-file-then-rename prevents partial writes from corrupting files if the process is interrupted.

**Why full-file replacement instead of surgical edits?** Full replacement is simpler and more reliable than `Filesystem:edit_file`'s find-and-replace pattern, which can fail if the search string doesn't match exactly (due to whitespace differences, prior modifications by another conversation, etc.). Claude already has the file content in context (it loaded the file to decide what to change), so providing the complete updated content is straightforward. For typical memory files (500–2,000 tokens), the output token cost of a full write is modest.

**MCP tool definition:**

```
Name:        "safe_write_file"
Description: "Atomically write content to a memory file. Acquires a write mutex
             shared with safe_append_file to prevent concurrent write conflicts.
             Uses temp-file-then-rename for atomicity. Restricted to the memory
             directory. Provide the COMPLETE file content — this is a full
             replacement, not an edit."

Input Schema:
  path:     string, required  — Absolute path to the file (must be within memory directory)
  content:  string, required  — Complete file content to write

Output Schema:
  success:       boolean
  bytes_written: integer
  path:          string   — The absolute path that was written (for confirmation)
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

    // 2. Ensure parent directory exists (handles new block creation).
    os.MkdirAll(filepath.Dir(absPath), 0755)

    // 3. Acquire the write mutex. This serializes all memory writes
    //    (both safe_write_file and safe_append_file) across all
    //    concurrent conversations in this Desktop App instance.
    writeMutex.Lock()
    defer writeMutex.Unlock()

    // 4. Write to a temp file in the same directory (same filesystem,
    //    so rename is atomic). Use the target directory, not os.TempDir(),
    //    to guarantee same-filesystem rename.
    tmpFile = os.CreateTemp(filepath.Dir(absPath), ".safe-write-*.tmp")
    _, err = tmpFile.Write([]byte(params.Content))
    tmpFile.Close()
    if err:
        os.Remove(tmpFile.Name())  // Clean up on write failure
        return error("Failed to write temp file: " + err)

    // 5. Atomic rename: replaces the target file in one operation.
    //    On Windows, os.Rename cannot overwrite an existing file.
    //    Use os.Remove + os.Rename, or the ReplaceFile Windows API.
    //    (Go's os.Rename on Windows uses MoveFileEx with
    //    MOVEFILE_REPLACE_EXISTING when possible, but behavior varies
    //    by filesystem. The safest cross-platform approach is:
    //    remove target if it exists, then rename.)
    if fileExists(absPath):
        os.Remove(absPath)
    err = os.Rename(tmpFile.Name(), absPath)
    if err:
        return error("Failed to rename temp file to target: " + err)

    return {
        success: true,
        bytes_written: len(params.Content),
        path: absPath
    }
```

**Windows rename caveat:** On Windows, `os.Rename` cannot atomically overwrite an existing file on all filesystems. The pseudo-code above uses a remove-then-rename sequence, which introduces a tiny window where the file doesn't exist. For our use case (low-frequency memory writes, mutex-serialized), this is acceptable. If true atomicity is needed later, the Windows `ReplaceFile` API can be called via `syscall`.

### 3.8 Tool: safe_append_file

This tool performs a mutex-protected append to a memory file. Its primary use case is adding entries to episodic log files (`episodic-YYYY-MM.md`), where each conversation appends a timestamped entry and a full rewrite is unnecessary.

**MCP tool definition:**

```
Name:        "safe_append_file"
Description: "Append text to a memory file. Acquires the same write mutex as
             safe_write_file to prevent concurrent write conflicts. Creates
             the file if it doesn't exist. The text is appended exactly as
             provided — include leading newlines if needed for formatting."

Input Schema:
  path:  string, required  — Absolute path to the file (must be within memory directory)
  text:  string, required  — Text to append

Output Schema:
  success:       boolean
  bytes_written: integer
```

**Handler pseudo-code:**

```
func HandleSafeAppendFile(params SafeAppendFileParams) SafeAppendFileResult:

    // 1. Validate that the path is within the memory directory.
    absPath = filepath.Abs(params.Path)
    if !strings.HasPrefix(absPath, config.Memory.Directory):
        return error("safe_append_file is restricted to the memory directory: " +
                      config.Memory.Directory)

    // 2. Ensure parent directory exists.
    os.MkdirAll(filepath.Dir(absPath), 0755)

    // 3. Acquire the SAME write mutex as safe_write_file.
    //    This means a safe_write_file and a safe_append_file to different
    //    files still serialize, but that's fine — memory writes are
    //    infrequent and fast (sub-millisecond). The simplicity of a
    //    single mutex far outweighs the negligible performance cost.
    writeMutex.Lock()
    defer writeMutex.Unlock()

    // 4. Open file for append (create if needed), write, close.
    //    O_APPEND ensures the write goes to the end even if the file
    //    was modified between open and write (belt-and-suspenders
    //    safety alongside the mutex).
    f = os.OpenFile(absPath, O_WRONLY|O_APPEND|O_CREATE, 0644)
    n, err = f.Write([]byte(params.Text))
    f.Close()

    if err:
        return error("Failed to append: " + err)

    return { success: true, bytes_written: n }
```

### 3.9 Write Mutex

The write mutex is the mechanism that serializes all memory file writes. It is a single `sync.Mutex` shared by both `safe_write_file` and `safe_append_file`.

**Why a single mutex works:** All conversations in the same Claude Desktop App instance share the same bridge process (same Go binary, same stdio pipe). Go's `sync.Mutex` provides in-process mutual exclusion — no file-locking APIs needed, no OS-specific behavior to worry about. When one conversation's tool call acquires the mutex, any other conversation's concurrent tool call blocks until the first releases it.

**Why a single mutex (not per-file mutexes):** A per-file mutex would allow concurrent writes to different files, but the added complexity isn't justified. Memory writes are infrequent (a few per session, each taking sub-millisecond I/O time) and the mutex hold time is negligible. A single mutex keeps the implementation trivial and eliminates any possibility of deadlock from lock ordering.

**What the mutex does NOT protect against:** Semantic divergence from concurrent read-modify-write sequences. If Conversation A loads `core.md`, then Conversation B also loads it, then A writes an update, then B writes a different update, B's write will atomically replace A's update. The mutex ensures neither write is corrupted (no interleaving), but B's write will not include A's changes because B was working from a stale snapshot. This is the *last writer wins* semantic, and **it is the accepted concurrency model for v1** of this system.

A `safe_edit_file` tool (performing find-and-replace under the same mutex) would not solve this problem either, because the race condition is fundamentally about stale reads, not unprotected writes. Both conversations would still be constructing their edits from the same stale snapshot. The edit operations might not conflict textually (if they target non-overlapping regions), but when they do overlap, the second edit would either fail (if its search pattern no longer matches) or silently overwrite the first conversation's changes.

The alternatives considered were:

1. Optimistic concurrency control via version counters / ETags on each file, where `safe_write_file` rejects writes with a stale version and Claude must re-read and retry.

2. Merge-on-write, where the tool attempts a three-way merge under the mutex.

Both add significant complexity — option 1 requires retry logic in the skill instructions, and option 2 is fragile for prose content. Neither is justified given the expected usage pattern: one active conversation at a time, with occasional brief overlaps. The write mutex prevents data corruption, and last-writer-wins is an acceptable trade-off for simplicity.

If semantic divergence becomes a real problem in practice, the upgrade path is to add optimistic
locking to `safe_write_file` (version-based conflict detection with retry) or to add a
read-modify-write helper tool (see [Chapter 9, Future Enhancements, Section
9.2](stateful-agent-design-chapter9.md#92-memory-aware-tools)) that reads the current file under the
mutex, applies changes, and writes back — all within a single lock acquisition.

**Implementation (writemutex.go):**

```go
package main

import "sync"

// writeMutex serializes all memory file writes across all concurrent
// conversations. Both safe_write_file and safe_append_file acquire
// this mutex before performing any I/O.
var writeMutex sync.Mutex
```

That's it. The entire write mutex implementation is a single global variable. Both tool handlers call `writeMutex.Lock()` / `defer writeMutex.Unlock()` at the start of their write operations.

### 3.10 Async Executor

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

### 3.11 Job Lifecycle Manager

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

### 3.12 Logging

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
| safe_write_file: write | info | path, bytes written |
| safe_append_file: append | info | path, bytes written |
| Job expired | warn | job_id, reason |
| Sub-agent killed (timeout) | warn | job_id, elapsed |
| Error (any) | error | tool name, error details |
| Bridge shutdown | info | active jobs killed |

**Format:** Structured JSON lines (one JSON object per log line). This is easy to parse, grep, and pipe into log aggregation tools.

```json
{"ts":"2026-02-21T14:30:00Z","level":"info","msg":"spawn_agent: subprocess launched","job_id":"job-a1b2c3","model":"sonnet","working_dir":"C:\\franl\\git\\mcp-bridge"}
```

### 3.13 Error Handling

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

### 3.14 Graceful Shutdown

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
