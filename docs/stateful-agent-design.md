# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>
**Companion document:** [Stateful Agent Proposal](stateful-agent-proposal.md) — architecture evaluation, rationale, and open question resolutions.

## Contents

- [1. Overview](#1-overview)
  - [1.1 What We're Building](#11-what-were-building)
  - [1.2 Component Inventory](#12-component-inventory)
  - [1.3 Design Principles](#13-design-principles)
  - [1.4 Terminology](#14-terminology)
- [2. System Architecture](#2-system-architecture)
  - [2.1 Component Diagram](#21-component-diagram)
  - [2.2 Data Flow](#22-data-flow)
  - [2.3 What the Bridge Does NOT Do](#23-what-the-bridge-does-not-do)
- [3. MCP Bridge Server](#3-mcp-bridge-server)
  - [3.1 Go Module Structure](#31-go-module-structure)
  - [3.2 Configuration](#32-configuration)
  - [3.3 Tool Summary](#33-tool-summary)
  - [3.4 Tool: spawn_agent](#34-tool-spawn_agent)
  - [3.5 Tool: check_agent](#35-tool-check_agent)
  - [3.6 Tool: append_file](#36-tool-append_file)
  - [3.7 Job Lifecycle Manager](#37-job-lifecycle-manager)
  - [3.8 Logging](#38-logging)
  - [3.9 Error Handling](#39-error-handling)
  - [3.10 Graceful Shutdown](#310-graceful-shutdown)
- [4. Memory System (Layer 2)](#4-memory-system-layer-2)
  - [4.1 Two-Layer Memory Model](#41-two-layer-memory-model)
  - [4.2 Three-Tier File Structure](#42-three-tier-file-structure)
  - [4.3 File Format: core.md](#43-file-format-coremd)
  - [4.4 File Format: index.md](#44-file-format-indexmd)
  - [4.5 File Format: Content Blocks](#45-file-format-content-blocks)
  - [4.6 File Format: Episodic Logs](#46-file-format-episodic-logs)
  - [4.7 File Format: decisions.md](#47-file-format-decisionsmd)
  - [4.8 Block Naming Conventions](#48-block-naming-conventions)
  - [4.9 Why Markdown (Not JSON, SQLite, or YAML)](#49-why-markdown-not-json-sqlite-or-yaml)
- [5. Memory Skill](#5-memory-skill)
  - [5.1 Skill Packaging](#51-skill-packaging)
  - [5.2 SKILL.md Content](#52-skillmd-content)
  - [5.3 Session Lifecycle](#53-session-lifecycle)
  - [5.4 Memory Write Triggers](#54-memory-write-triggers)
  - [5.5 Memory Read Triggers](#55-memory-read-triggers)
  - [5.6 Reconciliation with Layer 1](#56-reconciliation-with-layer-1)
- [6. Sub-Agent System](#6-sub-agent-system)
  - [6.1 Command Construction](#61-command-construction)
  - [6.2 Default System Preamble](#62-default-system-preamble)
  - [6.3 System Prompt Assembly](#63-system-prompt-assembly)
  - [6.4 Directory Sandbox Behavior](#64-directory-sandbox-behavior)
  - [6.5 CLAUDE.md Recommendations](#65-claudemd-recommendations)
  - [6.6 Sub-Agent Memory Access Rules](#66-sub-agent-memory-access-rules)
- [7. Deployment](#7-deployment)
  - [7.1 Build the Bridge](#71-build-the-bridge)
  - [7.2 Claude Desktop Configuration](#72-claude-desktop-configuration)
  - [7.3 Filesystem Extension Configuration](#73-filesystem-extension-configuration)
  - [7.4 Memory Directory Setup](#74-memory-directory-setup)
  - [7.5 Initial Memory Seeding](#75-initial-memory-seeding)
  - [7.6 Skill Installation](#76-skill-installation)
  - [7.7 CLAUDE.md Update](#77-claudemd-update)
- [8. Testing Strategy](#8-testing-strategy)
  - [8.1 MCP Bridge Server Tests](#81-mcp-bridge-server-tests)
  - [8.2 Memory Skill Tests](#82-memory-skill-tests)
  - [8.3 Sub-Agent Tests](#83-sub-agent-tests)
  - [8.4 Integration Tests](#84-integration-tests)
  - [8.5 Acceptance Criteria](#85-acceptance-criteria)
- [9. Future Enhancements](#9-future-enhancements)
  - [9.1 FTS5 Search Index (Option 3)](#91-fts5-search-index-option-3)
  - [9.2 Memory-Aware Tools](#92-memory-aware-tools)
  - [9.3 Architecture B2 Upgrade](#93-architecture-b2-upgrade)
  - [9.4 GitHub Backup Automation](#94-github-backup-automation)
- [10. References](#10-references)

---

## 1. Overview

### 1.1 What We're Building

The stateful agent system consists of three components that together give Claude persistent memory, local machine access, and task delegation capabilities:

1. **MCP Bridge Server** — A Go binary that runs locally, providing sub-agent spawning and file-append capabilities to the Claude Desktop App via the MCP protocol over stdio.

2. **Memory System (Layer 2)** — A directory of markdown files on the local filesystem that stores deep project context, episodic recall, decision history, and technical notes. This supplements Anthropic's built-in memory (Layer 1), which is limited to ~500–2,000 tokens.

3. **Memory Skill** — A Claude Desktop skill (.zip file) containing instructions that teach Claude how to manage the Layer 2 memory lifecycle: when to read files, when to write updates, how to structure content, and when to create new blocks.

### 1.2 Component Inventory

| Component | Type | Location | Purpose |
|-----------|------|----------|---------|
| MCP Bridge Server | Go binary | `C:\franl\git\mcp-bridge\mcp-bridge.exe` | Sub-agent spawning, file append |
| Anthropic Filesystem Extension | MCP server (npm) | Installed via Claude Desktop | Basic filesystem tools (read, write, edit, list, search) |
| Memory directory | Markdown files | `C:\franl\.claude-agent-memory\` | Layer 2 persistent storage |
| Memory skill | .zip file | Uploaded via Claude Desktop Settings | Instructions for memory lifecycle |
| CLAUDE.md | Markdown file | `C:\Users\franl\.claude\CLAUDE.md` | Sub-agent environment context |
| Bridge config | YAML file | `C:\franl\.claude-agent-memory\bridge-config.yaml` | Bridge runtime settings |

### 1.3 Design Principles

These principles are inherited from the proposal and govern all design decisions:

1. **Transparency.** All memory is stored in human-readable, human-editable markdown files. No opaque databases, no binary formats. The user can open any file in a text editor, review it, correct it, or delete it.

2. **Simplicity.** Start with the simplest approach that works. Add complexity (search indexes, memory-aware tools, parallel sub-agents) only when the simple approach proves insufficient in practice.

3. **Single binary.** The MCP bridge compiles to a single static Go binary with no runtime dependencies. Installation is copying the `.exe` file.

4. **Lean bridge.** The bridge provides only capabilities that the existing Anthropic Filesystem extension lacks: `spawn_agent`, `check_agent`, and `append_file`. All basic filesystem operations (read, write, edit, list, search) are handled by the Filesystem extension. This is "Path A" from the proposal.

5. **Compliance-based memory management.** Claude's memory updates are guided by skill instructions (compliance), not enforced by tool constraints. This is pragmatic — the alternative (a dedicated memory server with structured CRUD) is more complex and can be added later if compliance proves insufficient.

6. **Single-writer model.** Only the primary Claude Desktop agent writes to Layer 2 memory. Sub-agents are read-only. This eliminates concurrent write issues for the B1 single-instance architecture.

### 1.4 Terminology

| Term | Definition |
|------|-----------|
| **Primary agent** | The Claude instance running in Claude Desktop App. Has Layer 1 memory, MCP tools, and the memory skill. |
| **Sub-agent** | An ephemeral Claude Code CLI instance (`claude -p`) spawned by the bridge. One-shot, stateless, no Layer 1 memory. |
| **Layer 1** | Anthropic's built-in memory. Auto-generated summary (~500–2,000 tokens) injected into every conversation. Influenced indirectly via `memory_user_edits` steering instructions. ~24-hour lag for updates. |
| **Layer 2** | Our supplementary memory system. Markdown files at `~/.claude-agent-memory/`. Under our full control. Updates are immediate. |
| **MCP bridge** | The Go binary that serves as an MCP server, providing `spawn_agent`, `check_agent`, and `append_file` tools. |
| **Filesystem extension** | Anthropic's official `@modelcontextprotocol/server-filesystem` MCP server. Provides `read_file`, `write_file`, `edit_file`, etc. |
| **Memory skill** | The .zip file uploaded to Claude Desktop containing SKILL.md — instructions for managing Layer 2 memory. |
| **Sync window** | The 25-second window during which `spawn_agent` waits for the sub-agent to complete before switching to async mode. Sized to stay safely under Claude Desktop's ~30-second reliability threshold. |
| **Block** | An individual markdown file in the `blocks/` directory. Each block covers a project, topic, or time period. |
| **Block reference** | A row in `index.md` mapping a block filename to its summary and last-updated date. |

---

## 2. System Architecture

### 2.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    Claude Desktop App                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Claude LLM (Anthropic servers)                            │  │
│  │                                                            │  │
│  │  Layer 1 memory (auto-injected, ~500–2,000 tokens)         │  │
│  │  Memory skill instructions (from SKILL.md)                 │  │
│  │  Cloud VM tools (bash_tool, create_file — DO NOT USE       │  │
│  │    for persistent data; ephemeral, resets between sessions) │  │
│  └──────────────┬─────────────────────┬───────────────────────┘  │
│                 │ MCP (stdio)         │ MCP (stdio)              │
│                 ▼                     ▼                          │
│  ┌──────────────────────┐  ┌──────────────────────────────┐     │
│  │  MCP Bridge Server   │  │  Anthropic Filesystem Ext.   │     │
│  │  (our Go binary)     │  │  (@modelcontextprotocol/     │     │
│  │                      │  │   server-filesystem)         │     │
│  │  Tools:              │  │                              │     │
│  │  • spawn_agent       │  │  Tools:                      │     │
│  │  • check_agent       │  │  • read_file                 │     │
│  │  • append_file       │  │  • write_file                │     │
│  │       │              │  │  • edit_file                  │     │
│  │       │ subprocess   │  │  • list_directory             │     │
│  │       ▼              │  │  • search_files               │     │
│  │  ┌────────────┐      │  │  • ... (11 tools total)      │     │
│  │  │ claude -p  │      │  │                              │     │
│  │  │ (sub-agent)│      │  │  Allowed dirs:               │     │
│  │  └────────────┘      │  │  • C:\franl                  │     │
│  └──────────────────────┘  │  • C:\temp                   │     │
│                            │  • C:\apps                   │     │
│                            └──────────────────────────────┘     │
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

**Memory read (session start):**
```
Claude LLM
  → calls Filesystem:read_file("C:\franl\.claude-agent-memory\core.md")
  → calls Filesystem:read_file("C:\franl\.claude-agent-memory\index.md")
  → (optionally) calls Filesystem:read_file for relevant blocks
```

**Memory write (during session):**
```
Claude LLM
  → calls Filesystem:write_file (for core.md, index.md, or block updates)
  → calls Filesystem:edit_file (for surgical edits to blocks)
  → calls Bridge:append_file (for episodic log entries)
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

### 2.3 What the Bridge Does NOT Do

The bridge is deliberately minimal. It does **not** provide:

- Basic filesystem tools (read, write, edit, list, search) — handled by the Filesystem extension.
- Network request tools (http_get, http_post) — deferred. Sub-agents can perform network operations directly. Can be added to the bridge later if needed.
- Command execution tools (run_command, run_script) — deferred. Sub-agents provide this capability. A direct `run_command` tool can be added later.
- Memory-aware tools (update_memory_block, memory_search) — deferred to future enhancement. See [Section 9.2](#92-memory-aware-tools).

This keeps the initial bridge very small: three tool handlers plus the job lifecycle manager.

---

## 3. MCP Bridge Server

### 3.1 Go Module Structure

```
mcp-bridge/
├── go.mod                    # Module: github.com/fpl9000/mcp-bridge
├── go.sum
├── main.go                   # Entry point: loads config, registers tools, starts stdio server
├── config.go                 # Configuration loading and validation
├── tools.go                  # Tool handler registration
├── spawn.go                  # spawn_agent tool handler + subprocess management
├── check.go                  # check_agent tool handler
├── append.go                 # append_file tool handler
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
3. Default: `~/.claude-agent-memory/bridge-config.yaml`

**Configuration schema:**

```yaml
# bridge-config.yaml

# Sub-agent defaults
sub_agent:
  sync_window_seconds: 25         # How long spawn_agent waits before going async
                                  # Must be < 30 (Claude Desktop reliability threshold)
  default_timeout_seconds: 300    # Max subprocess runtime (kills after this)
  default_max_output_tokens: 4000 # Truncation threshold (chars/4 heuristic)
  max_concurrent_agents: 5        # Cap on simultaneous running sub-agents
  job_expiry_seconds: 600         # Uncollected jobs cleaned up after this

# Memory directory (used by append_file for path validation)
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
    //   - sync_window_seconds < 30
    //   - memory.directory exists (or create it)
    //   - logging.file parent directory exists
    //   - claude_cli.path is executable
    // Return validated config
```

### 3.3 Tool Summary

| Tool | MCP Name | Purpose |
|------|----------|---------|
| `spawn_agent` | `spawn_agent` | Launch a sub-agent (`claude -p`) with a task. Returns result (sync) or job_id (async). |
| `check_agent` | `check_agent` | Poll a running sub-agent by job_id. Returns status and result. |
| `append_file` | `append_file` | Atomically append text to a file. Primary use: episodic log entries. |

### 3.4 Tool: spawn_agent

This is the most complex tool in the bridge. It manages the hybrid sync/async execution model required by Claude Desktop's ~60-second MCP timeout.

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
  working_directory:  string, optional  — CWD and sandbox root (default: user's home)
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
func HandleSpawnAgent(params SpawnAgentParams) SpawnAgentResult:

    // 1. Check concurrent agent cap
    if jobManager.ActiveCount() >= config.MaxConcurrentAgents:
        return error("Maximum concurrent sub-agents reached ({config.MaxConcurrentAgents}). 
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

    // 4. Launch the subprocess
    startedAt = time.Now()
    proc = exec.Command(config.ClaudeCLI.Path, args...)
    proc.Dir = params.WorkingDirectory or os.UserHomeDir()
    proc.Stdin = strings.NewReader(params.Task)  // Task goes to stdin

    // Capture stdout and stderr
    outputBuffer = new ConcurrentBuffer()
    proc.Stdout = outputBuffer
    proc.Stderr = outputBuffer  // Merge stderr into output for visibility

    err = proc.Start()
    if err:
        return error("Failed to start sub-agent: " + err)

    // 5. Start the sync window timer
    syncDeadline = startedAt.Add(config.SyncWindowSeconds * time.Second)
    processTimeout = startedAt.Add(params.TimeoutSeconds * time.Second)

    // 6. Wait for completion OR sync window expiry
    done = make(chan error, 1)
    go func():
        done <- proc.Wait()

    select:
        case err = <-done:
            // Sub-agent completed within sync window
            output = outputBuffer.String()
            output = truncateIfNeeded(output, params.MaxOutputTokens)

            if err != nil:
                return {
                    status: "complete",
                    job_id: null,
                    result: "Sub-agent exited with error: " + err + "\nOutput:\n" + output,
                    started_at: startedAt.Format(ISO8601)
                }

            return {
                status: "complete",
                job_id: null,
                result: output,
                started_at: startedAt.Format(ISO8601)
            }

        case <-time.After(time.Until(syncDeadline)):
            // Sync window expired — go async
            jobID = jobManager.Register(proc, outputBuffer, startedAt, processTimeout, 
                                         params.MaxOutputTokens, done)

            log.Info("Sub-agent exceeded sync window, assigned job_id=%s", jobID)

            return {
                status: "running",
                job_id: jobID,
                result: null,
                started_at: startedAt.Format(ISO8601)
            }
```

### 3.5 Tool: check_agent

**MCP tool definition:**

```
Name:        "check_agent"
Description: "Check the status of a running sub-agent by job ID.
             Returns the current status and result if complete."

Input Schema:
  job_id:  string, required  — Job ID from spawn_agent

Output Schema:
  status:          "running" | "complete" | "failed" | "timed_out"
  result:          string | null
  error:           string | null
  started_at:      string (ISO 8601)
  elapsed_seconds: number
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
            output = truncateIfNeeded(output, job.MaxOutputTokens)

            // Mark job as collected (will be cleaned up by lifecycle manager)
            jobManager.MarkCollected(params.JobID)

            if err != nil:
                return {
                    status: "failed",
                    result: output,
                    error: err.String(),
                    started_at: job.StartedAt.Format(ISO8601),
                    elapsed_seconds: elapsed
                }

            return {
                status: "complete",
                result: output,
                error: null,
                started_at: job.StartedAt.Format(ISO8601),
                elapsed_seconds: elapsed
            }

        default:
            // Still running — check if we've exceeded the timeout
            if time.Now().After(job.Deadline):
                job.Process.Kill()
                output = job.OutputBuffer.String()
                output = truncateIfNeeded(output, job.MaxOutputTokens)
                jobManager.MarkCollected(params.JobID)

                return {
                    status: "timed_out",
                    result: output,
                    error: "Sub-agent exceeded timeout of " + job.TimeoutSeconds + "s",
                    started_at: job.StartedAt.Format(ISO8601),
                    elapsed_seconds: elapsed
                }

            // Still running and within timeout
            return {
                status: "running",
                result: null,
                error: null,
                started_at: job.StartedAt.Format(ISO8601),
                elapsed_seconds: elapsed
            }
```

### 3.6 Tool: append_file

This tool atomically appends text to a file. Its primary use case is adding entries to episodic log files (`episodic-YYYY-MM.md`), but it works with any file within the memory directory.

The Anthropic Filesystem extension does not provide an append operation — only full read, full write, and find-and-replace edit. For append-only patterns (episodic logs, activity trails), `append_file` avoids the read-modify-write cycle and the risk of clobbering concurrent changes to the same file.

**MCP tool definition:**

```
Name:        "append_file"
Description: "Atomically append text to a file. Creates the file if it doesn't exist.
             The text is appended exactly as provided — add leading newlines if needed."

Input Schema:
  path:  string, required  — Absolute path to the file
  text:  string, required  — Text to append

Output Schema:
  success: boolean
  bytes_written: integer
```

**Handler pseudo-code:**

```
func HandleAppendFile(params AppendFileParams) AppendFileResult:

    // Validate that the path is within the memory directory
    absPath = filepath.Abs(params.Path)
    if !strings.HasPrefix(absPath, config.Memory.Directory):
        return error("append_file is restricted to the memory directory: " + 
                      config.Memory.Directory)

    // Ensure parent directory exists
    os.MkdirAll(filepath.Dir(absPath))

    // Open file for append (create if needed), write, close
    // Uses O_APPEND for atomicity at the OS level
    f = os.OpenFile(absPath, O_WRONLY|O_APPEND|O_CREATE, 0644)
    n, err = f.Write([]byte(params.Text))
    f.Close()

    if err:
        return error("Failed to append: " + err)

    return { success: true, bytes_written: n }
```

**Why not just use Filesystem:write_file?** Two reasons: (a) `write_file` overwrites the entire file, so appending requires a read-modify-write cycle that can lose data if two sessions write simultaneously; (b) `append_file` restricted to the memory directory provides a safety boundary — it cannot accidentally overwrite system files. (See proposal Open Question #22, strategy (b): unambiguous tool names.)

### 3.7 Job Lifecycle Manager

The job manager is a background goroutine that tracks active sub-agent jobs and cleans up expired ones.

**Data structures:**

```
type Job struct {
    ID             string
    Process        *os.Process
    OutputBuffer   *ConcurrentBuffer   // Thread-safe buffer capturing stdout+stderr
    StartedAt      time.Time
    Deadline       time.Time           // StartedAt + TimeoutSeconds
    MaxOutputTokens int
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
            expiryTime = job.StartedAt.Add(config.JobExpirySeconds * time.Second)
            if now.After(expiryTime):
                // If process is still running, kill it
                if !job.ProcessDone():
                    job.Process.Kill()
                log.Warn("Job %s expired without being collected", id)
                delete(jm.jobs, id)

        jm.mu.Unlock()
```

**Job ID generation:** Use a short, human-readable ID composed of a prefix and random suffix, e.g., `job-a1b2c3`. The prefix makes log entries easy to grep. Use `crypto/rand` for the random component.

### 3.8 Logging

All bridge operations are logged to a file for auditability and debugging. Logging does **not** go to stdout/stderr (those are reserved for MCP stdio transport).

**What to log:**

| Event | Level | Fields |
|-------|-------|--------|
| Bridge started | info | config path, version |
| Tool call received | info | tool name, abbreviated params |
| spawn_agent: subprocess launched | info | job_id (if async), model, working_dir |
| spawn_agent: sync completion | info | elapsed time, output size |
| spawn_agent: async handoff | info | job_id, elapsed time at handoff |
| check_agent: status poll | debug | job_id, status, elapsed |
| check_agent: result collected | info | job_id, status, elapsed, output size |
| append_file: write | info | path, bytes written |
| Job expired | warn | job_id, reason |
| Sub-agent killed (timeout) | warn | job_id, elapsed |
| Error (any) | error | tool name, error details |
| Bridge shutdown | info | active jobs killed |

**Format:** Structured JSON lines (one JSON object per log line). This is easy to parse, grep, and pipe into log aggregation tools.

```json
{"ts":"2026-02-21T14:30:00Z","level":"info","msg":"spawn_agent: subprocess launched","job_id":"job-a1b2c3","model":"sonnet","working_dir":"C:\\franl\\git\\mcp-bridge"}
```

### 3.9 Error Handling

The bridge should never crash from a tool call. All errors are caught and returned as MCP tool errors.

**Error categories:**

| Category | Example | Behavior |
|----------|---------|----------|
| Configuration error | Missing config file, invalid YAML | Bridge fails to start with clear error message |
| Tool input validation | Missing required param, invalid path | Return MCP tool error immediately |
| Subprocess launch failure | `claude` not found, permission denied | Return MCP tool error with details |
| Subprocess timeout | Sub-agent exceeds `timeout_seconds` | Kill process, return `timed_out` status via `check_agent` |
| Subprocess crash | `claude -p` exits with non-zero | Return output + exit code via `result` field |
| File I/O error | Permission denied, disk full | Return MCP tool error with OS error details |
| Concurrent agent cap reached | 5 sub-agents already running | Return MCP tool error suggesting the user wait or check existing jobs |

### 3.10 Graceful Shutdown

When the bridge receives a shutdown signal (Claude Desktop closes, SIGINT, SIGTERM):

1. Stop accepting new tool calls.
2. Kill all running sub-agent subprocesses (send SIGTERM, wait 5 seconds, then SIGKILL).
3. Log the shutdown and number of jobs terminated.
4. Exit cleanly.

**Pseudo-code:**

```
func main():
    // ... setup ...
    
    // Handle shutdown signals
    sigCh = signal.Notify(SIGINT, SIGTERM)
    go func():
        <-sigCh
        log.Info("Shutdown signal received, killing %d active jobs", jobManager.ActiveCount())
        jobManager.KillAll()
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
| **Update mechanism** | Indirect via `memory_user_edits` steering instructions | Direct via Filesystem:write_file, edit_file, Bridge:append_file |
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
    └── episodic-2026-03.md      #   March 2026 conversation log
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
The bridge is a single Go binary that registers three MCP tools via the mcp-go SDK.
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
proposal. Design document written to C:\franl\git\ai-skills\docs\stateful-agent-design.md.

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

| Format | Rejected because |
|--------|-----------------|
| **JSON** | Not human-readable at scale. Requires programmatic tooling to inspect or edit. Not Git-diff-friendly for prose content. Claude reads text natively — markdown is optimal. |
| **SQLite** | Opaque binary format. Cannot be inspected in a text editor or GitHub web UI. Merge conflicts are unresolvable. Overkill for the expected data volume (dozens of files, hundreds of KB). |
| **YAML** | Fragile whitespace sensitivity. Poor for long-form prose. Acceptable for metadata (hence the optional YAML frontmatter), but not for content bodies. |
| **Markdown** | Human-readable, human-editable, Git-friendly diffs, viewable in any text editor or GitHub, Claude-native format, no parsing dependencies. Trade-off: lookups require reading files, not querying an index — acceptable at our scale. |

---

## 5. Memory Skill

### 5.1 Skill Packaging

The memory skill is a Claude Desktop skill packaged as a .zip file containing a single `SKILL.md` file. It does not contain scripts (all operations use existing MCP tools). The .zip is uploaded via Claude Desktop > Settings > Capabilities.

```
stateful-memory.zip
└── SKILL.md           # Instructions for Layer 2 memory lifecycle
```

**Why no scripts?** In the B1 architecture, all memory operations are performed via MCP tools (Filesystem extension for read/write/edit, bridge for append). No Python or shell scripts are needed. This eliminates dependency management and makes the skill trivially portable.

### 5.2 SKILL.md Content

The SKILL.md below is the complete skill instruction file. It is the primary artifact that controls Claude's memory behavior.

```markdown
# Stateful Agent Memory Skill

You have access to a persistent memory system stored as markdown files on the local
filesystem. This memory persists across conversations and gives you deep context
about the user, their projects, and your shared history.

## CRITICAL: Use Local MCP Tools for All Persistent Operations

ALWAYS use MCP Filesystem tools (Filesystem:read_file, Filesystem:write_file,
Filesystem:edit_file) or Bridge tools (Bridge:append_file) for memory operations.
NEVER use cloud VM tools (bash_tool, create_file, str_replace) for persistent data.
The cloud VM filesystem is ephemeral and resets between sessions. Memory files live
at C:\franl\.claude-agent-memory\ — always access them via MCP tools.

## Memory Directory

Location: C:\franl\.claude-agent-memory\

Structure:
- core.md — Your identity summary and active project list. Always load this first.
- index.md — Table mapping block filenames to summaries. Always load after core.md.
- blocks\ — Individual content files. Load on demand based on conversation topic.

## Session Start Protocol

At the start of every conversation, BEFORE responding to the user's first message:

1. Read core.md via Filesystem:read_file
2. Read index.md via Filesystem:read_file
3. Scan the index for blocks relevant to the user's opening message
4. If a relevant block exists, read it via Filesystem:read_file
5. Now respond to the user, informed by your loaded context

If core.md does not exist, this is a first-run scenario. Create the memory directory
structure and seed core.md with basic information from Layer 1 (your built-in memory)
and the current conversation.

## During the Conversation

### When to Read Blocks
- When the conversation shifts to a topic listed in index.md that you haven't loaded
- When the user asks "what do you remember about X?" and X matches a block
- When you need project context to give an informed answer

### When to Write Memory
Write memory updates incrementally as significant information emerges. Do NOT
accumulate changes and batch-write at session end — sessions can end abruptly.

**Write to core.md** (via Filesystem:write_file or Filesystem:edit_file) when:
- A new project starts or an existing project's status changes significantly
- Key facts about the user change (role, location, preferences)
- Keep core.md under ~1,000 tokens. Move detailed content to blocks.

**Write to index.md** (via Filesystem:edit_file) when:
- You create a new block (add a row)
- A block's summary needs updating (edit the Summary column)
- A block's content changes (update the Updated column)

**Write to blocks** (via Filesystem:write_file or Filesystem:edit_file) when:
- Significant project decisions are made
- Technical details worth remembering emerge
- The user shares information that will be useful in future sessions

**Append to episodic log** (via Bridge:append_file) when:
- Periodically during long sessions (every 30–60 minutes)
- At natural breakpoints in the conversation
- Before the session ends (if you sense the user is wrapping up)
- Format: ## YYYY-MM-DD — Brief Title\nSummary paragraph.\n\n
- Target file: blocks\episodic-YYYY-MM.md (current month)

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
- When updating blocks, use Filesystem:edit_file for surgical changes rather than
  rewriting the entire file.
- Re-read a file before writing if you haven't accessed it recently, to avoid
  overwriting changes from other sessions.

## Session End

If the user says goodbye, thanks you, or the conversation is clearly winding down:

1. Persist any pending memory updates (core.md, index.md, relevant blocks)
2. Append an entry to the current month's episodic log summarizing the session
3. You do not need to announce that you're saving memory — just do it

## Handling User Questions About Memory

If the user asks "what do you remember about X?":
1. Check index.md for blocks related to X
2. Read relevant blocks
3. Combine with any Layer 1 (built-in) memory you have
4. Respond naturally, as if recalling from your own knowledge

If the user asks to correct or delete a memory:
1. Use Filesystem:edit_file to make the correction in the relevant file
2. Acknowledge the correction

If the user asks to see their memory files:
1. You can show them the contents of specific files
2. Remind them that the files are plain markdown at C:\franl\.claude-agent-memory\
   and can be edited with any text editor
```

### 5.3 Session Lifecycle

Detailed sequence of operations at each session phase:

```
Session Start
│
├─ 1. Skill instructions loaded into context (automatic, ~500 tokens)
├─ 2. Layer 1 memory loaded into context (automatic, ~500–2,000 tokens)
├─ 3. Read core.md (Filesystem:read_file, ~500–1,000 tokens)
├─ 4. Read index.md (Filesystem:read_file, ~300–800 tokens)
├─ 5. Evaluate user's first message against index entries
├─ 6. Read relevant blocks if any match (Filesystem:read_file, varies)
└─ 7. Respond to user's first message
│
Session Active
│
├─ On topic change → Check index, load relevant blocks
├─ On significant information → Update relevant block or core.md
├─ On new project/topic → Create new block + update index.md
├─ On decision made → Update decisions.md or project block
├─ Every 30–60 minutes → Append episodic log entry
└─ On context pressure → Summarize verbose blocks to free tokens
│
Session End (if detectable)
│
├─ 1. Write pending updates to core.md, index.md, blocks
├─ 2. Append episodic log entry summarizing the session
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
| Session in progress (periodic) | Brief summary of what's happened so far | `episodic-YYYY-MM.md` (append) |
| Session ending | Session summary | `episodic-YYYY-MM.md` (append) |

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
  task: "Read all files in ~/.claude-agent-memory/ and produce a structured 
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
- **Layer 2 fixes:** Edit files directly via MCP tools (immediate effect).

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
| Minimal | `~/projects/foo` | false | none | Only `~/projects/foo/**` |
| With memory | `~/projects/foo` | true | none | `~/projects/foo/**` + `~/.claude-agent-memory/**` (read) |
| Multi-repo | `~/projects/foo` | false | `[~/projects/bar]` | `~/projects/foo/**` + `~/projects/bar/**` |
| Memory + multi-repo | `~/projects/foo` | true | `[~/projects/bar]` | All three directories |

**Important:** The sandbox blocks reads, not just writes. If `allow_memory_read` is `false`, the sub-agent cannot even `cat` a memory file — Claude Code will refuse the operation.

**Write protection for memory files** is preamble-based (compliance), not enforced by the sandbox. If `allow_memory_read` is `true`, the sub-agent could technically write to the memory directory. The preamble instructs against this. For additional hardening, the bridge could launch the subprocess with the memory directory mounted read-only at the OS level (platform-specific).

### 6.5 CLAUDE.md Recommendations

The file `~/.claude/CLAUDE.md` is loaded into every Claude Code invocation automatically (including sub-agents), independent of `--system-prompt`. It should be optimized for the sub-agent use case:

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

See the proposal's [Recommended CLAUDE.md Content for Sub-Agents](stateful-agent-proposal.md#recommended-claudemd-content-for-sub-agents) section for the complete recommended content.

### 6.6 Sub-Agent Memory Access Rules

| Layer | Access | Enforcement | Notes |
|-------|--------|-------------|-------|
| Layer 1 (Anthropic built-in) | None | Platform | `claude -p` does not receive built-in memory. Platform limitation. |
| Layer 2 (supplementary) | Read-only (optional) | Sandbox (read) + preamble (write) | Controlled by `allow_memory_read`. Default: false. |
| CLAUDE.md | Auto-loaded | None (automatic) | Loaded by Claude Code startup, cannot be suppressed. Keep credentials out. |

**Why no write access?** Allowing sub-agents to write to Layer 2 would break the single-writer model and reintroduce concurrent write problems. The primary agent is the sole writer. Sub-agents return findings in their text response; the primary agent decides what to persist.

---

## 7. Deployment

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

### 7.2 Claude Desktop Configuration

Edit Claude Desktop's MCP configuration file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the bridge server entry:

```json
{
  "mcpServers": {
    "mcp-bridge": {
      "command": "C:\\franl\\git\\mcp-bridge\\mcp-bridge.exe",
      "args": ["--config", "C:\\franl\\.claude-agent-memory\\bridge-config.yaml"]
    }
  }
}
```

The Desktop App will launch the bridge as a subprocess on startup, communicating via stdio.

**Note:** The existing Filesystem extension entry should already be present in this file. The two MCP servers run simultaneously. If the Filesystem extension is not configured, add it:

```json
{
  "mcpServers": {
    "mcp-bridge": {
      "command": "C:\\franl\\git\\mcp-bridge\\mcp-bridge.exe",
      "args": ["--config", "C:\\franl\\.claude-agent-memory\\bridge-config.yaml"]
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y", "@modelcontextprotocol/server-filesystem",
        "C:\\franl", "C:\\temp", "C:\\apps"
      ]
    }
  }
}
```

### 7.3 Filesystem Extension Configuration

Ensure the Anthropic Filesystem extension's allowed directories include the memory directory's parent. Since `C:\franl\.claude-agent-memory` is under `C:\franl`, and `C:\franl` is already an allowed directory, no changes are needed.

If the memory directory were elsewhere, it would need to be added as an argument to the filesystem server command.

### 7.4 Memory Directory Setup

Create the directory structure:

```bash
mkdir -p C:\franl\.claude-agent-memory\blocks
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

Replace the current `~/.claude/CLAUDE.md` with the lean sub-agent-optimized version described in [Section 6.5](#65-claudemd-recommendations) and the proposal. Move credentials to environment variables. Move service-specific instructions to `spawn_agent` system_prompt parameters.

---

## 8. Testing Strategy

Testing covers four levels: bridge unit tests, memory skill behavioral tests, sub-agent integration tests, and full system end-to-end tests.

### 8.1 MCP Bridge Server Tests

These are standard Go tests (`go test ./...`) that test the bridge in isolation.

#### 8.1.1 append_file Tests

| Test Case | Input | Expected Behavior |
|-----------|-------|-------------------|
| Append to new file | Path to non-existent file + text | File created with text content |
| Append to existing file | Path to existing file + text | Text appended after existing content |
| Path outside memory dir | Path under `C:\temp\` | Error: "restricted to memory directory" |
| Path traversal attempt | Path with `..` escaping memory dir | Error: path validation rejects it |
| Empty text | Valid path + empty string | Success (no-op write, 0 bytes) |
| Parent dir creation | Path where parent dir doesn't exist | Parent directories created, file written |

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

#### 8.1.4 Job Lifecycle Tests

| Test Case | Expected Behavior |
|-----------|-------------------|
| Cleanup goroutine runs | After job_expiry_seconds, uncollected jobs are removed |
| Graceful shutdown | All active subprocesses are killed, bridge exits cleanly |
| Job ID uniqueness | 1000 sequential job IDs are all unique |

#### 8.1.5 MCP Integration Tests

These tests verify the bridge works correctly as an MCP server. Use the `mcp-go` SDK's test utilities or send raw JSON-RPC messages over a pipe.

| Test Case | Expected Behavior |
|-----------|-------------------|
| MCP initialization handshake | Bridge responds with capabilities and tool list |
| Tool listing | Returns spawn_agent, check_agent, append_file |
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

#### 8.2.6 Correct Tool Usage (No Cloud VM Writes)

**Test procedure:**
1. Monitor the bridge log and Claude Desktop's tool usage during a memory-writing session.
2. Verify that all writes to memory files use `Filesystem:write_file`, `Filesystem:edit_file`, or `Bridge:append_file`.
3. Verify that no writes to the memory directory use `bash_tool`, `create_file`, or `str_replace`.

**Pass criteria:** All memory writes go through MCP tools. No cloud VM tools used for persistent data.

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
| AC1 | Bridge starts and registers all 3 tools with Claude Desktop | MCP integration test |
| AC2 | spawn_agent completes fast tasks synchronously (< 25s) | Sub-agent test 8.3.1 |
| AC3 | spawn_agent handles slow tasks asynchronously (> 25s) | Sub-agent test 8.3.4 |
| AC4 | check_agent returns correct status and results | check_agent tests 8.1.3 |
| AC5 | append_file atomically appends to files within memory dir | append_file tests 8.1.1 |
| AC6 | Memory skill loads core.md + index.md at session start | Skill test 8.2.1 |
| AC7 | Memory skill writes updates during conversation | Skill test 8.2.3 |
| AC8 | Memory skill creates episodic log entries | Skill test 8.2.4 |
| AC9 | Memory persists across conversations | Integration test 8.4.1 |
| AC10 | Sub-agent directory sandbox blocks unauthorized access | Sub-agent test 8.3.3 |
| AC11 | Both MCP servers (bridge + filesystem) work simultaneously | Integration test 8.4.3 |
| AC12 | No memory writes use cloud VM tools | Skill test 8.2.6 |

---

## 9. Future Enhancements

These are planned upgrades that are deliberately deferred from the initial implementation. Each addresses a limitation documented in the proposal.

### 9.1 FTS5 Search Index (Option 3)

**Trigger:** When the number of blocks exceeds ~50 and filename-based retrieval from `index.md` becomes cumbersome.

**Design:** Add a SQLite FTS5 full-text search index alongside the markdown files. The index is a derived artifact — it can be rebuilt from the markdown files at any time.

```
~/.claude-agent-memory/
├── core.md
├── index.md
├── blocks/
│   └── ...
└── .search-index.db     # SQLite FTS5 (in .gitignore)
```

**New tool:** `memory_search(query: string, max_results: int) → [{file, snippet, score}]`

**Implementation:** Use `modernc.org/sqlite` (pure Go, no CGO) or `mattn/go-sqlite3` for the SQLite driver. Maintain the FTS5 index via a post-write hook: whenever the bridge detects a write to the memory directory (via `append_file` or by observing file modification times), re-index the changed file.

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

---

## 10. References

- **Proposal document:** [stateful-agent-proposal.md](stateful-agent-proposal.md) — Architecture evaluation, 27 open question resolutions, rationale for all major decisions.
- **Previous skill design (superseded):** [stateful-agent-skill-design.md](stateful-agent-skill-design.md) — Earlier design for a standalone skill without MCP bridge. Concepts carried forward; implementation approach replaced.
- **Tim Kellogg's Strix architecture:** [Memory Architecture for a Synthetic Being](https://timkellogg.me/blog/2025/12/30/memory-arch) — Three-tier hierarchical memory model that inspired our core/index/blocks structure.
- **claude_life_assistant:** [GitHub](https://github.com/lout33/claude_life_assistant) — Luis Fernando's minimal stateful agent demonstrating the core concept.
- **mark3labs/mcp-go:** [GitHub](https://github.com/mark3labs/mcp-go) — Go SDK for the Model Context Protocol.
- **MCP specification:** [modelcontextprotocol.io](https://modelcontextprotocol.io) — Protocol specification for tool registration, stdio transport, and Streamable HTTP transport.
- **Claude Code system prompts:** [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts) — Community-maintained extraction of Claude Code's default system prompt fragments.
- **Anthropic Filesystem extension:** [@modelcontextprotocol/server-filesystem](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem) — Official MCP server providing 11 filesystem tools.
