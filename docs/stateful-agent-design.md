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
  - [3.6 Tool: run_command](#36-tool-run_command)
  - [3.7 Tool: safe_write_file](#37-tool-safe_write_file)
  - [3.8 Tool: safe_append_file](#38-tool-safe_append_file)
  - [3.9 Write Mutex](#39-write-mutex)
  - [3.10 Async Executor](#310-async-executor)
  - [3.11 Job Lifecycle Manager](#311-job-lifecycle-manager)
  - [3.12 Logging](#312-logging)
  - [3.13 Error Handling](#313-error-handling)
  - [3.14 Graceful Shutdown](#314-graceful-shutdown)
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
- [11. Open Questions](#11-open-questions)
- [12. Appendix: mark3labs/mcp-go SDK Reference](#12-appendix-mark3labsmcp-go-sdk-reference)

---

## 1. Overview

### 1.1 What We're Building

The stateful agent system consists of three components that together give Claude persistent memory, local machine access, and task delegation capabilities:

1. **MCP Bridge Server** — A Go binary that runs locally, providing sub-agent spawning and mutex-protected memory file writes to the Claude Desktop App via the MCP protocol over stdio.

2. **Memory System (Layer 2)** — A directory of markdown files on the local filesystem that stores deep project context, episodic recall, decision history, and technical notes. This supplements Anthropic's built-in memory (Layer 1), which is limited to ~500–2,000 tokens.

3. **Memory Skill** — A Claude Desktop skill (.zip file) containing instructions that teach Claude how to manage the Layer 2 memory lifecycle: when to read files, when to write updates, how to structure content, and when to create new blocks.

### 1.2 Component Inventory

| Component | Type | Location | Purpose |
|-----------|------|----------|---------|
| MCP Bridge Server<br/>(aka "the bridge") | Go binary | `C:\franl\git\mcp-bridge\mcp-bridge.exe` | Sub-agent spawning, mutex-protected memory writes |
| Anthropic Filesystem Extension | MCP server | Installed via Claude Desktop | Basic filesystem tools (read, write, edit, list, search) |
| Memory directory | Markdown files | `C:\franl\.claude-agent-memory\` | Layer 2 persistent storage |
| Memory skill | .zip file | Uploaded via Claude Desktop Settings | Instructions for memory lifecycle |
| CLAUDE.md | Markdown file | `C:\Users\flitt\.claude\CLAUDE.md` | Sub-agent environment context |
| Bridge config | YAML file | `C:\franl\.claude-agent-memory\bridge-config.yaml` | Bridge runtime settings |

### 1.3 Design Principles

These principles are inherited from the proposal and govern all design decisions:

1. **Transparency.** All memory is stored in human-readable, human-editable markdown files. No opaque databases, no binary formats. The user can open any file in a text editor, review it, correct it, or delete it.

2. **Simplicity.** Start with the simplest approach that works. Add complexity (search indexes, memory-aware tools, parallel sub-agents) only when the simple approach proves insufficient in practice.

3. **Single binary.** The MCP bridge compiles to a single static Go binary with no runtime dependencies. Installation is copying the `.exe` file.

4. **Lean bridge with local file access and command execution.** The bridge provides sub-agent lifecycle management tools (`spawn_agent`, `check_agent`), a direct local command execution tool (`run_command`), and mutex-protected memory file writer tools (`safe_write_file`, `safe_append_file`). The `run_command` tool executes shell commands on the local machine and returns stdout/stderr directly. The memory write tools intentionally overlap with the Filesystem extension's `write_file` — this is by design, not redundancy (see item #5 below for the rationale). All other filesystem operations (read, list, search, and non-memory writes) are handled by the Filesystem extension.

5. **Single-writer model with mutex protection.** Only the primary Claude Desktop agent writes to Layer 2 memory. Sub-agents have read-only access to Layer 2 memory. The bridge's in-process write mutex serializes all memory file writes (see open question #1 in section [Open Questions](#11-open-questions) for details).

6. **Compliance-based memory management.** Claude's memory updates are guided by skill instructions (compliance), not enforced by tool constraints. This is pragmatic — the alternative (a dedicated memory server with structured CRUD) is more complex and can be added later if compliance proves insufficient.

### 1.4 Terminology

| Term | Definition |
|------|-----------|
| **Primary agent** | The Claude instance running in Claude Desktop App. Has Layer 1 memory, MCP tools, and the memory skill. |
| **Sub-agent** | An ephemeral Claude Code CLI instance (`claude -p`) spawned by the bridge. One-shot, stateless, no Layer 1 memory. |
| **Layer 1** | Anthropic's built-in memory. Auto-generated summary (~500–2,000 tokens) injected into every conversation. Influenced indirectly via `memory_user_edits` steering instructions. ~24-hour lag for updates. |
| **Layer 2** | Our supplementary memory system. Markdown files at `C:\franl\.claude-agent-memory\`. Under our full control. Updates are immediate. |
| **MCP bridge** | The Go binary that serves as an MCP server, providing `spawn_agent`, `check_agent`, `run_command`, `safe_write_file`, and `safe_append_file` tools. |
| **Filesystem extension** | Anthropic's official `@modelcontextprotocol/server-filesystem` MCP server. Provides `read_file`, `write_file`, `edit_file`, etc. Used for reading memory files and all non-memory file operations. |
| **Write mutex** | A Go `sync.Mutex` in the bridge process that serializes all memory file writes (`safe_write_file` and `safe_append_file`). Prevents concurrent conversations from interleaving or overwriting each other's memory updates. |
| **Memory skill** | The .zip file uploaded to Claude Desktop containing SKILL.md — instructions for managing Layer 2 memory. |
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
│  │  • spawn_agent       │  │  Tools:                      │      │
│  │  • check_agent       │  │  • read_file                 │      │
│  │  • run_command       │  │  • write_file                │      │
│  │  • safe_write_file   │  │  • edit_file                 │      │
│  │  • safe_append_file  │  │  • create_directory          │      │
│  │       │              │  │  • list_directory            │      │
│  │       │ subprocess   │  │  • search_files              │      │
│  │       ▼              │  │  • search_files              │      │
│  │  ┌────────────┐      │  │  • ... (11 tools total)      │      │
│  │  │ claude -p  │      │  │                              │      │
│  │  │ (sub-agent)│      │  │  Allowed dirs:               │      │
│  │  └────────────┘      │  │  • C:\franl                  │      │
│  └──────────────────────┘  │  • C:\temp                   │      │
│                            │  • C:\apps                   │      │
│                            └──────────────────────────────┘      │
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
  → calls Bridge:safe_write_file (for core.md, index.md, or block updates)
  → calls Bridge:safe_append_file (for episodic log entries)
  Both tools acquire the bridge's write mutex before writing,
  preventing concurrent conversations from interleaving writes.
  Claude should NEVER use Filesystem:write_file or Filesystem:edit_file
  for memory files — those bypass the mutex.
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

- Basic filesystem tools (read, list, search) — handled by the Filesystem extension. The bridge provides `safe_write_file` and `safe_append_file` specifically for memory files; all non-memory file writes use the Filesystem extension.
- Network request tools (http_get, http_post) — deferred. Sub-agents or `run_command` (e.g., `run_command("curl ...")`) can perform network operations. Dedicated network tools can be added to the bridge later if needed.
- Memory-aware tools (update_memory_block, memory_search) — deferred to future enhancement. See [Section 9.2](#92-memory-aware-tools).

This keeps the initial bridge small: five tool handlers, a write mutex, the async executor, and the job lifecycle manager.

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

**What the mutex does NOT protect against:** Semantic divergence from concurrent read-modify-write sequences. If Conversation A loads `core.md`, then Conversation B also loads it, then A writes an update, then B writes a different update, B's write will atomically replace A's update. The mutex ensures neither write is corrupted (no interleaving), but B's write will not include A's changes because B was working from a stale snapshot. This is the *last writer wins* semantic, and **ait is the accepted concurrency model for v1** of this system.

A `safe_edit_file` tool (performing find-and-replace under the same mutex) would not solve this problem either, because the race condition is fundamentally about stale reads, not unprotected writes. Both conversations would still be constructing their edits from the same stale snapshot. The edit operations might not conflict textually (if they target non-overlapping regions), but when they do overlap, the second edit would either fail (if its search pattern no longer matches) or silently overwrite the first conversation's changes.

The alternatives considered were:

1. Optimistic concurrency control via version counters / ETags on each file, where `safe_write_file` rejects writes with a stale version and Claude must re-read and retry.

2. Merge-on-write, where the tool attempts a three-way merge under the mutex.

Both add significant complexity — option 1 requires retry logic in the skill instructions, and option 2 is fragile for prose content. Neither is justified given the expected usage pattern: one active conversation at a time, with occasional brief overlaps. The write mutex prevents data corruption, and last-writer-wins is an acceptable trade-off for simplicity.

If semantic divergence becomes a real problem in practice, the upgrade path is to add optimistic locking to `safe_write_file` (version-based conflict detection with retry) or to add a read-modify-write helper tool (see [Section 9.2](#92-memory-aware-tools)) that reads the current file under the mutex, applies changes, and writes back — all within a single lock acquisition.

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

## CRITICAL: Use the Correct Tools for Memory Operations

For READING memory files: use `Filesystem:read_file` (the Anthropic Filesystem extension).

For WRITING memory files: ALWAYS use `Bridge:safe_write_file` (full file replacement)
or `Bridge:safe_append_file` (append to episodic logs). These tools are mutex-protected
and scoped to the memory directory. They prevent concurrent conversations from
overwriting each other's updates.

NEVER use `Filesystem:write_file` or `Filesystem:edit_file` for memory files — those
bypass the write mutex and can cause data loss if two conversations write simultaneously.

NEVER use cloud VM tools (`bash_tool`, `create_file`, `str_replace`) for persistent data.
The cloud VM filesystem is ephemeral and resets between sessions.

Memory files live at `C:\franl\.claude-agent-memory\` — always access them via the tools above.

## Memory Directory

Location: C:\franl\.claude-agent-memory\

Structure:
- core.md — Your identity summary and active project list. Always load this first.
- index.md — Table mapping block filenames to summaries. Always load after core.md.
- blocks\ — Individual content files. Load on demand based on conversation topic.

## Session Start Protocol

At the start of every conversation, BEFORE responding to the user's first message:

1. Read core.md via `Filesystem:read_file`
2. Read index.md via `Filesystem:read_file`
3. Scan the index for blocks relevant to the user's opening message
4. If a relevant block exists, read it via `Filesystem:read_file`
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

**Write to core.md** (via `Bridge:safe_write_file`) when:
- A new project starts or an existing project's status changes significantly
- Key facts about the user change (role, location, preferences)
- Keep core.md under ~1,000 tokens. Move detailed content to blocks.
- Provide the COMPLETE updated file content (safe_write_file does full replacement)

**Write to index.md** (via `Bridge:safe_write_file`) when:
- You create a new block (add a row)
- A block's summary needs updating (edit the Summary column)
- A block's content changes (update the Updated column)
- Provide the COMPLETE updated file content

**Write to blocks** (via `Bridge:safe_write_file`) when:
- Significant project decisions are made
- Technical details worth remembering emerge
- The user shares information that will be useful in future sessions
- Provide the COMPLETE updated file content

**Append to episodic log** (via `Bridge:safe_append_file`) when:
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
  Read the file first if you don't already have its content in context.

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
1. Read the file, make the correction, and write the updated content via `Bridge:safe_write_file`
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
├─ 3. Read core.md (Filesystem:read_file, ~500–1,000 tokens)
├─ 4. Read index.md (Filesystem:read_file, ~300–800 tokens)
├─ 5. Evaluate user's first message against index entries
├─ 6. Read relevant blocks if any match (Filesystem:read_file, varies)
└─ 7. Respond to user's first message
│
Session Active
│
├─ On topic change → Check index, load relevant blocks
├─ On significant information → Update relevant block or core.md (Bridge:safe_write_file)
├─ On new project/topic → Create new block + update index.md (Bridge:safe_write_file)
├─ On decision made → Update decisions.md or project block (Bridge:safe_write_file)
├─ Every 30–60 minutes → Append episodic log entry (Bridge:safe_append_file)
└─ On context pressure → Summarize verbose blocks to free tokens
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
- **MacOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json` (no official support for Claude Desktop on Linux)

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

---

## 9. Future Enhancements

These are planned upgrades that are deliberately deferred from the initial implementation. Each addresses a limitation documented in the proposal.

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


### 9.5 GitHub Relay: Claude.ai ↔ Local Bridge Communication

**Trigger:** When mobile or web access to the local stateful agent is desired — e.g., using the Claude app on a phone to invoke tools on the home machine.

**Problem:** Claude.ai runs code in an ephemeral Linux VM with strict egress restrictions (whitelisted domains only: `github.com`, `api.github.com`, `pypi.org`, etc.). It cannot reach arbitrary IPs or custom domains. This rules out direct connections via port forwarding, Tailscale, or any custom tunnel endpoint. However, both Claude.ai (via the GitHub skill) and the local MCP bridge can read and write to GitHub's REST API — making a private GitHub repo a viable asynchronous message relay.

**Architecture overview:**

```
┌──────────────────┐       ┌──────────────┐       ┌──────────────────────────┐
│  Claude.ai       │       │   GitHub     │       │  Local Machine           │
│  (phone/web)     │       │   Private    │       │  (Windows 11)            │
│                  │  PUT  │   Repo       │  GET  │                          │
│  GitHub skill ───────────▶ requests/   ◀─────────  MCP Bridge              │
│                  │       │              │       │    │                      │
│                  │  GET  │              │  PUT  │    ├─ memory_query:       │
│  GitHub skill ◀──────────── responses/ ◀─────────  │   handled directly    │
│                  │       │              │       │    ├─ shell_command:       │
│                  │       │              │       │    │   handled directly    │
│                  │       │              │       │    └─ claude_prompt:       │
│                  │       │              │       │        inject into Claude  │
│                  │       │              │       │        Desktop via AHK     │
│                  │       │              │       │        ▼                   │
│                  │       │              │       │      Claude Desktop        │
│                  │       │              │       │        │                   │
│                  │       │              │       │        ▼ relay_respond()   │
│                  │       │              │       │      MCP Bridge            │
└──────────────────┘       └──────────────┘       └──────────────────────────┘
```

**Key design principle:** The relay logic is integrated directly into the MCP bridge — there is no separate daemon process. The bridge polls the relay repo, handles `memory_query` and `shell_command` operations locally (no inference), and delegates `claude_prompt` operations to Claude Desktop via an AutoHotkey-based prompt injection mechanism.

**Relay repository:** A dedicated private repo (e.g., `fpl9000/claude-relay`) with the following structure:

```
claude-relay/
├── README.md
├── requests/          # Claude.ai writes here
│   └── <id>.json
├── responses/         # MCP bridge writes here
│   └── <id>.json
└── .gitignore
```

#### 9.5.1 Message Protocol

Each request/response pair shares a unique message ID (a timestamp-based UUID or similar). The protocol uses a simple state machine:

**Request message** (`requests/<id>.json`):

```json
{
  "id": "20260307T143022Z-a1b2c3",
  "created_at": "2026-03-07T14:30:22Z",
  "status": "pending",
  "nonce": "a1b2c3d4e5f6...",
  "hmac": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "operation": "memory_query",
  "arguments": {
    "path": "core.md"
  },
  "context": "User asked from mobile: what's in my core memory?"
}
```

**Response message** (`responses/<id>.json`):

```json
{
  "id": "20260307T143022Z-a1b2c3",
  "completed_at": "2026-03-07T14:30:38Z",
  "status": "completed",
  "result": {
    "success": true,
    "content": "... file contents or response text ..."
  }
}
```

**Status values:**

| Status | Location | Meaning |
|--------|----------|---------|
| `pending` | `requests/` | Awaiting pickup by MCP bridge |
| `claimed` | `requests/` | Bridge has acknowledged, processing |
| `completed` | `responses/` | Result ready for Claude.ai to read |
| `failed` | `responses/` | Operation failed; `result.error` contains details |
| `expired` | `requests/` | TTL exceeded without pickup (set by cleanup) |

#### 9.5.2 Supported Operations

The relay supports exactly three operations, with a clear split: two are handled entirely by the MCP bridge (no inference), and one delegates to Claude Desktop for full agent-loop processing.

**Bridge-local operations (no inference):**

| Operation | Arguments | Behavior |
|-----------|-----------|----------|
| `memory_query` | `path` (string) | Reads the specified file from the memory directory and returns its content as UTF-8 text. Equivalent to the bridge's `safe_read_file` tool scoped to the memory directory. |
| `shell_command` | `command` (string), `timeout_seconds` (int, optional) | Executes the command locally and returns stdout/stderr as UTF-8 text. Equivalent to the bridge's `run_command` tool with the same security constraints (no interactive commands, enforced timeout). |

**Claude Desktop-delegated operation:**

| Operation | Arguments | Behavior |
|-----------|-----------|----------|
| `claude_prompt` | `prompt` (string) | Forwards the prompt to Claude Desktop for processing. Claude Desktop performs whatever tool calls it deems appropriate based on the prompt content, then returns its final response as UTF-8 text via the `relay_respond` MCP tool. |

The `claude_prompt` operation is the "full agent loop" path — it gives Claude Desktop complete autonomy to read memory, run commands, spawn sub-agents, or do anything else its tools allow. The other two operations are fast, deterministic shortcuts that bypass inference entirely.

#### 9.5.3 The `claude_prompt` Flow and `relay_respond` Tool

The `claude_prompt` operation requires a round-trip through Claude Desktop:

1. The MCP bridge picks up a `claude_prompt` request from the relay repo.
2. The bridge injects the prompt into Claude Desktop via an AutoHotkey script (mechanism TBD — see Section 9.5.7).
3. The injected prompt includes a preamble instructing Claude Desktop to call the `relay_respond` tool when it has completed the task:

   ```
   [RELAY REQUEST id=20260307T143022Z-a1b2c3]
   The following prompt was forwarded from Claude.ai via the GitHub relay.
   Process it using whatever tools you need, then call the relay_respond
   tool with your final answer.

   <relay_prompt>
   {original prompt text from Claude.ai}
   </relay_prompt>
   ```

4. Claude Desktop processes the prompt — reading memory, running commands, spawning agents, etc. as it sees fit.
5. When finished, Claude Desktop calls the `relay_respond` MCP tool provided by the bridge.
6. The bridge writes the response to `responses/<id>.json` in the relay repo.

**New MCP tool — `relay_respond`:**

```go
// Tool definition
mcp.NewTool(
    "relay_respond",
    mcp.WithDescription(
        "Submit a response for a relay request forwarded from Claude.ai. "+
        "Call this tool when you have completed processing a [RELAY REQUEST] prompt. "+
        "The response content will be delivered back to the Claude.ai session that "+
        "originated the request.",
    ),
    mcp.WithString("relay_id",
        mcp.Required(),
        mcp.Description("The relay request ID from the [RELAY REQUEST] header."),
    ),
    mcp.WithString("content",
        mcp.Required(),
        mcp.Description(
            "Your complete response to the relay request, as UTF-8 text. "+
            "Include all relevant results, summaries, and context — the "+
            "recipient cannot ask follow-up questions.",
        ),
    ),
)
```

**Handler behavior:**

1. Validate that `relay_id` matches a `claimed` request that used the `claude_prompt` operation.
2. Write `responses/<relay_id>.json` to the relay repo via the GitHub API.
3. Return success to Claude Desktop.

If Claude Desktop calls `relay_respond` with an unknown or already-completed `relay_id`, the handler returns a tool error.

#### 9.5.4 Security

The relay repo is private, but defense-in-depth applies:

1. **HMAC request authentication:** The bridge and Claude.ai share a secret key (configured in `relay-config.yaml` on the bridge side, provided to Claude.ai by the user at the start of a session or stored in the GitHub skill's environment). Each request is authenticated as follows:

   **Signing (Claude.ai side):**
   1. Generate a cryptographically random nonce (e.g., 16 hex bytes).
   2. Construct the HMAC input by concatenating: `id || operation || nonce || canonical_arguments`, where `canonical_arguments` is the JSON-serialized `arguments` object with keys sorted alphabetically.
   3. Compute HMAC-SHA256 over the input using the shared secret key.
   4. Include both `nonce` and `hmac` (hex-encoded) in the request JSON.

   **Verification (bridge side):**
   1. Recompute the HMAC from the request fields using the same shared key.
   2. Compare using constant-time comparison (`hmac.Equal` in Go) to prevent timing attacks.
   3. Check the nonce against a seen-nonces set (stored in memory, bounded by TTL) to prevent replay attacks. Reject if the nonce has been seen before.
   4. Check that `created_at` is within the acceptable time window (e.g., ±5 minutes) to bound the size of the replay-prevention set.

   **Example HMAC computation:**

   ```
   Input:  "20260307T143022Z-a1b2c3" + "memory_query" + "a1b2c3d4e5f6..." + '{"path":"core.md"}'
   Key:    <shared secret from relay-config.yaml>
   Output: HMAC-SHA256 → hex-encoded → "e3b0c44298fc1c..."
   ```

   Requests with invalid or missing HMACs are rejected and logged. Requests with replayed nonces are rejected and logged.

2. **Operation allowlist:** The bridge configuration specifies which operations are permitted via the relay. For example, `shell_command` can be disabled or restricted to specific command patterns.

3. **Rate limiting:** The bridge enforces a maximum number of requests per time window (e.g., 10 requests per minute) to limit abuse.

4. **Audit log:** All relay activity is logged to the bridge's log file, including rejected requests with the rejection reason (bad HMAC, replayed nonce, disallowed operation, rate-limited).

#### 9.5.5 Bridge Relay Integration

The relay polling loop runs as a goroutine within the MCP bridge process. Its responsibilities:

1. **Poll** the `requests/` directory in the relay repo at a configurable interval (default: 15 seconds) using the GitHub Contents API.
2. **Claim** new `pending` requests by updating their status to `claimed`.
3. **Dispatch** the operation:
   - `memory_query` → read the file directly from the memory directory and write the response.
   - `shell_command` → execute the command (reusing `run_command` logic) and write the response.
   - `claude_prompt` → inject the prompt into Claude Desktop via AutoHotkey; the response arrives asynchronously when Claude Desktop calls `relay_respond`.
4. **Clean up** expired requests and old response files beyond the configured TTL (default: 1 hour).

**Bridge configuration** (added to `relay-config.yaml` or a `[relay]` section in the bridge config):

```yaml
relay:
  enabled: false               # Off by default
  repo: fpl9000/claude-relay
  github_token_env: GITHUB_TOKEN
  poll_interval_seconds: 15
  request_ttl_minutes: 60
  claude_prompt_timeout_minutes: 5
  max_requests_per_minute: 10
  hmac_secret_env: RELAY_HMAC_SECRET   # Environment variable holding the shared key
  replay_window_minutes: 5             # Nonce replay prevention window
  allowed_operations:
    - memory_query
    - shell_command
    - claude_prompt
  ahk_script_path: C:\franl\scripts\relay-inject.ahk
  log_file: C:\franl\.claude-agent-memory\relay.log
```

#### 9.5.6 Claude.ai Workflow

From Claude.ai (web or mobile), the interaction pattern is:

1. **User** asks Claude.ai to do something that requires the local machine (e.g., "read my core memory," "ask my local Claude to summarize today's episodic log").
2. **Claude.ai** uses the GitHub skill to create `requests/<id>.json` in the relay repo.
3. **Claude.ai** polls `responses/<id>.json` at intervals (e.g., every 10 seconds, up to a timeout).
4. **Claude.ai** reads the response and presents the result to the user.

The round-trip latency depends on the operation:

| Operation | Typical latency | Bottleneck |
|-----------|----------------|------------|
| `memory_query` | 15–40 sec | Bridge poll interval + GitHub API round-trips |
| `shell_command` | 15–60 sec | Bridge poll interval + command execution time |
| `claude_prompt` | 30 sec–5 min | Bridge poll interval + Claude Desktop inference + tool calls |

**Timeout behavior:** If no response appears within a configurable timeout (default: 2 minutes for bridge-local ops, 5 minutes for `claude_prompt`), Claude.ai reports that the local machine may be offline or the operation is still in progress.

#### 9.5.7 AutoHotkey Prompt Injection (TBD)

The mechanism for injecting a prompt into Claude Desktop's UI is deferred to a future design iteration. The approach will use an AutoHotkey script that:

1. Activates the Claude Desktop window.
2. Pastes the relay-formatted prompt into the input field.
3. Sends Enter to submit.

Design considerations include: handling the case where Claude Desktop is mid-conversation, ensuring the prompt is injected cleanly (no partial sends), and dealing with Claude Desktop's window state (minimized, behind other windows, etc.).

#### 9.5.8 Cleanup and Hygiene

- The bridge deletes request files after writing the corresponding response.
- Response files are deleted after the configured TTL.
- Cleanup runs on each poll cycle as part of the relay goroutine.
- The relay repo should stay lean — it is a message queue, not a data store. The `.gitignore` should exclude any local state files.
- GitHub API rate limits (5,000 authenticated requests/hour) are more than sufficient for relay traffic at expected volumes.

#### 9.5.9 Relationship to Section 9.3 (Architecture B2 Upgrade)

If the bridge gains Streamable HTTP transport and a Cloudflare Tunnel (Section 9.3), Claude.ai could potentially connect directly — bypassing the GitHub relay entirely. The relay is the pragmatic v1 solution that works within Claude.ai's current egress restrictions. The two approaches are complementary: the relay can remain as a fallback for environments where tunnel setup is impractical.

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

---

## 11. Open Questions

1. **Race condition with memory writes** — MCP bridge tools `safe_write_file` and `safe_append_file` serialize file writes using a Go mutex, however this only prevents torn writes. It doesn't solve the problem where concurrent conversations race via read-modify-write.  For instance, if conversation A reads `core.md` and conversation B reads `core.md`, then after each is modified in-context, whichever conversation writes `core.md` last overwrites the other's changes.  Would it help to add a `safe_edit_file` tool that uses the same mutex?

   - *Resolution:* We discussed this and decided that last-writer-wins is the accepted concurrency model for v1. A `safe_edit_file` tool would not solve this because the race is about stale reads, not unprotected writes. The mutex prevents data corruption not semantic divergence from concurrent read-modify-write. The latter is accepted as rare and tolerable. Optimistic locking via version counters is the identified upgrade path if this proves insufficient. See updated [Section 3.9](#39-write-mutex).

2. **Need a tool to run commands** — Section 2.3, "What the Bridge Does NOT Do", says the bridge will not have a `run_command` tool, but using a sub-agent to run a simple `curl` command or Bash script is a waste of valuable tokens (that cost money).  Let's change the design to include implmenting the `run_command` tool.

   - *Resolution:* The `run_command` tool has been added to the bridge as a first-class tool (see [Section 3.6](#36-tool-run_command)). It executes shell commands via Cygwin bash (`C:\apps\cygwin\bin\bash.exe -c "<command>"`) with no LLM inference involved, making it dramatically cheaper than `spawn_agent` for simple operations. Key design decisions: (a) uses the same hybrid sync/async model as `spawn_agent` via the shared async executor ([Section 3.10](#310-async-executor)), so long-running commands like recursive `grep` are handled correctly; (b) default output limit is 50 KB (~12,500 tokens) to avoid context window bloat; (c) middle-truncation preserves both head and tail of output; (d) no command restrictions for v1 (primary agent already has equivalent access via `spawn_agent`); (e) all commands are logged for auditability. Section 2.3 has been updated to remove `run_command` from the "does NOT do" list. The bridge now provides five tools total.

3. **Bridge configuration question** — What exactly are the semantics of bridge configuration parameter `job_expiry_seconds`?

   - *Resolution:* `job_expiry_seconds` (default: 600) defines how long the bridge's job lifecycle manager will retain a completed-but-uncollected async job before discarding it. The expiry clock starts from `job.StartedAt` (not from when the process finished). When the cleanup goroutine's 30-second sweep detects that `now > job.StartedAt + job_expiry_seconds`, it kills the process if it is still running, logs a warning, and removes the job from the map.

     The parameter exists to prevent memory leaks from orphaned jobs — async jobs whose `job_id` was returned to the primary agent but never retrieved via `check_agent`. This can happen if the user closes Claude Desktop mid-conversation, the agent forgets to poll, or the agent hits a context limit and loses track of the job_id. Without expiry, those jobs would accumulate indefinitely in the job manager, holding process handles and output buffers (up to 50 KB each for `run_command`, up to the token limit for `spawn_agent`).

     The default of 600 seconds (10 minutes) is intentionally generous. In normal operation, the primary agent polls `check_agent` within seconds or minutes of receiving a `job_id`. The 10-minute window provides ample time for the agent to return to polling even after a distraction or brief interruption, while still ensuring the bridge doesn't accumulate stale jobs across a long Claude Desktop session. No change to the design or default value is needed.

4. **UNIX Signals on Windows** — Section 3.14, "Graceful Shutdown", mentions SIGINT and SIGTERM, but do those signals exist on Windows?  How does the Go runtime deal with UNIX signals on Windows?

   - *Resolution:* SIGTERM does not exist as a native inter-process signal on Windows — it is only a software-level constant defined within the Windows CRT and cannot be sent from one external process to another. SIGINT exists in a limited form (Ctrl+C in a console window triggers a `CTRL_C_EVENT` that Go maps to `syscall.SIGINT`), but since the bridge runs as a background stdio subprocess with no attached console, it is not reliably deliverable either. Go's `os/signal` package maps these console events to signal constants, but that is of no help for a headless subprocess.

     The correct shutdown mechanism for an MCP stdio server on Windows is **stdin EOF detection**. When Claude Desktop exits or kills the bridge, it closes the stdin pipe. The `mcp-go` SDK's stdio read loop detects this EOF and exits naturally, giving the bridge an opportunity to clean up. Section 3.14 has been updated accordingly: UNIX signal handling has been removed, the shutdown trigger is now stdin EOF, and subprocess termination uses `Process.Kill()` (which calls Windows `TerminateProcess` directly) rather than a SIGTERM-then-SIGKILL escalation sequence.

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

      Accordingly, the implementation uses `exec.Command(shellPath, append(shellArgs, params.Command)...)` as specified in [Section 3.6](#36-tool-run_command), where `shellArgs` defaults to `["-c"]`. This is correct, sufficient, and requires no change.

11. **Multiple home directories** — Sections 3.4, "Tool: spawn_agent", and 3.6, "Tool: run_command", say that the default value of the working directory parameter is my home directory, but there's an ambiguity: my Windows home directory is `C:\Users\flitt\` and my Cygwin home directory is `C:\franl\`.  Is there any issue with changing those sections to explicity specify `C:\franl\` as the default working directory for commands `spawn_agent` and `run_command`?

    - *Resolution:* No issue. `C:\franl\` is the correct default and `os.UserHomeDir()` would be wrong here for two reasons: (a) on Windows it returns `C:\Users\flitt\` (from `USERPROFILE`), not the Cygwin home; and (b) both `run_command` (which runs via Cygwin bash) and `spawn_agent` (which spawns a sub-agent doing real work) expect to start in the Cygwin-rooted environment where all projects and tools live. Using `C:\Users\flitt\` as the default would be consistently wrong.

      Rather than hardcoding `C:\franl\` as a compile-time constant, the design has been updated to add a `default_working_directory` field to the bridge config (see [Section 3.2](#32-configuration)), defaulting to `C:\franl\`. This keeps it configurable without a recompile if the filesystem layout ever changes, and is consistent with how the rest of the config handles machine-specific paths. Sections 3.4 and 3.6 have been updated to reference `config.DefaultWorkingDirectory` instead of `os.UserHomeDir()`.

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

