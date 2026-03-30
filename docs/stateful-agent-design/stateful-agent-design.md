# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>
**Companion document:** [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

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
- [3. MCP Bridge Server](stateful-agent-design-chapter3.md)
- [4. Memory System (Layer 2)](stateful-agent-design-chapter4.md)
- [5. Memory Skill](stateful-agent-design-chapter5.md)
- [6. Sub-Agent System](stateful-agent-design-chapter6.md)
- [7. Deployment](stateful-agent-design-chapter7.md)
- [8. Testing Strategy](stateful-agent-design-chapter8.md)
- [9. Future Enhancements](stateful-agent-design-chapter9.md)
- [10. References](#10-references)
- [11. Open Questions](stateful-agent-design-chapter11.md)
- [12. Appendix: mark3labs/mcp-go SDK Reference](stateful-agent-design-chapter12.md)

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
| MCP Bridge Server<br/>(aka "the bridge") | Go binary | `C:\franl\.claude-agent-memory\bin\mcp-bridge.exe` | Sub-agent spawning, mutex-protected memory reads/writes. Source code located in `C:\franl\git\mcp-bridge\` |
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

See [Stateful Agent System: Detailed Design – Chapter 3](stateful-agent-design-chapter3.md).

---

## 4. Memory System (Layer 2)

See [Stateful Agent System: Detailed Design – Chapter 4](stateful-agent-design-chapter4.md).

---

## 5. Memory Skill

See [Stateful Agent System: Detailed Design – Chapter 5](stateful-agent-design-chapter5.md).

---

## 6. Sub-Agent system

See [Stateful Agent System: Detailed Design – Chapter 6](stateful-agent-design-chapter6.md).

---

## 7. Build and Deployment

See [Stateful Agent System: Detailed Design – Chapter 7](stateful-agent-design-chapter7.md).

---

## 8. Testing Strategy

See [Stateful Agent System: Detailed Design – Chapter 8](stateful-agent-design-chapter8.md).

---

## 9. Future Enhancements

See [Stateful Agent System: Detailed Design – Chapter 9](stateful-agent-design-chapter9.md).

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

See [Stateful Agent System: Detailed Design – Chapter 11](stateful-agent-design-chapter11.md).

---

## 12. Appendix: mark3labs/mcp-go SDK Reference

See [Stateful Agent System: Detailed Design – Chapter 12](stateful-agent-design-chapter12.md).
