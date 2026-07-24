# Stateful Agent System: Detailed Design

**Version:** 2.0  
**Date:** February - June 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)
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
  - [2.4 Supported Client Environments](#24-supported-client-environments)
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
- [13. Appendix: Implementation Ordering for Branching and Merging](stateful-agent-design-chapter13.md)

---

## 1. Overview

### 1.1 What We're Building

The stateful agent system consists of three components that together give Claude Desktop persistent memory, local machine access, and task delegation capabilities:

1. **MCP Bridge Server** — A Go binary that runs locally, providing memory-aware tools (read/write access to Layer 2 memory through a structured tool interface), Bash access, and sub-agent spawning, to be used by the Claude Desktop App via the MCP protocol over stdio. The bridge owns all memory storage details — file layout, concurrency control, branching, and indexing are handled internally and are invisible to the LLM.

2. **Memory System (Layer 2)** — A directory of markdown files on the local filesystem that stores deep project context, episodic recall, decision history, and technical notes. This supplements Anthropic's built-in memory (Layer 1), which is limited to ~500–2,000 tokens. The LLM never touches these files directly; it accesses them by name through the bridge's memory-aware tools.

3. **Memory Skill** — A Claude Desktop skill (.zip file) containing instructions that teach Claude how to manage the Layer 2 memory lifecycle: when to read blocks, when to write updates, how to structure content, and when to create new blocks. The skill teaches *when and what*; the bridge enforces *how*.

### 1.2 Component Inventory

| Component                            | Type           | Location                                           | Purpose                                                                                                            |
| ------------------------------------ | -------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| MCP Bridge Server (aka "the bridge") | Go binary      | `C:\franl\.claude-agent-memory\bin\mcp-bridge.exe` | Memory-aware tools, sub-agent spawning, local command execution. Source code located in `C:\franl\git\mcp-bridge\` |
| Anthropic Filesystem Extension       | MCP server     | Installed via Claude Desktop                       | Basic filesystem tools (read, write, edit, list, search) for **non-memory** files only                             |
| Memory directory                     | Markdown files | `C:\franl\.claude-agent-memory\`                   | Layer 2 persistent storage (managed exclusively by the bridge)                                                     |
| Bridge state file                    | JSON file      | `C:\franl\.claude-agent-memory\.bridge-state.json` | Persisted bridge state: live handles, branch map, read baselines. Survives bridge restarts.                        |
| Memory skill                         | .zip file      | Uploaded via Claude Desktop Settings               | Instructions for memory lifecycle                                                                                  |
| CLAUDE.md                            | Markdown file  | `C:\Users\flitt\.claude\CLAUDE.md`                 | Sub-agent environment context                                                                                      |
| Bridge config                        | YAML file      | `C:\franl\.claude-agent-memory\bridge-config.yaml` | Bridge runtime settings                                                                                            |

### 1.3 Design Principles

These principles are inherited from the proposal and govern all design decisions:

1. **Transparency.** All memory is stored in human-readable, human-editable markdown files. No opaque databases, no binary formats. The user can open any file in a text editor, review it, correct it, or delete it. (Transparency is for the *user* — the LLM sees blocks by name through tools, not files by path.)

2. **Simplicity.** Start with the simplest approach that works. Add complexity (search indexes, parallel sub-agents) only when the simple approach proves insufficient in practice. Future enhancements are described in [Chapter 9](stateful-agent-design-chapter9.md).

3. **Single binary.** The MCP bridge compiles to a single static Go binary with no runtime dependencies. Installation is copying the `.exe` file.

4. **Memory-aware tools with a handle protocol.** The bridge provides a family of memory-aware tools (`memory_start_conversation`, `memory_get_core`, `memory_write_core`, `memory_get_index`, `memory_get_block`, `memory_write_block`, `memory_append_block`, `memory_append_episodic`, `memory_run_maintenance`) plus sub-agent lifecycle tools (`spawn_agent`, `check_agent`) and a direct local command execution tool (`run_command`). Memory tools address blocks by *name*, not by file path. Every conversation begins by calling `memory_start_conversation`, which returns an opaque 8-character handle; the handle is a required parameter on every subsequent memory tool call and lets the bridge track each conversation's reads to detect concurrent read-modify-write races. Non-memory filesystem operations (list, search, and non-memory reads/writes) are handled by the Filesystem extension.

5. **Single-writer model with invisible per-handle branching.** Only the primary Claude Desktop agent writes to Layer 2 memory. Sub-agents have read-only access to Layer 2 memory. The bridge's in-process write mutex serializes all memory file I/O. When a concurrent read-modify-write race is detected (via per-handle read baselines), the bridge transparently routes the write to a per-handle *branch* of the block instead of overwriting the other conversation's changes — and continues routing that handle's reads and writes of that block to its branch, so each conversation sees its own consistent view. Branches are completely invisible to the LLM: tool responses never mention them. Branches are merged back into the base block by a semantic merge process when the user invokes `memory_run_maintenance` (see [Chapter 3, Section 3.15](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection) and [Section 3.17](stateful-agent-design-chapter3.md#317-merge-process-and-merge-mutex) for details).

6. **Compliance for policy, enforcement for structure.** Claude's memory *policy* — when to read, when to write, what's worth remembering — is guided by skill instructions (compliance). But memory *structure* — file layout, naming, frontmatter, index consistency, concurrency safety — is enforced by the bridge's tool interface and cannot be violated by the LLM, even accidentally. This is the key change from version 1.0, which relied on compliance for both. The version 1.0 approach (path-based `safe_*` file tools) is preserved for historical context in the [Design Update Plan](design-update-plan.md).

### 1.4 Terminology

| Term | Definition |
|------|-----------|
| **Primary agent** | The Claude instance running in Claude Desktop App. Has Layer 1 memory, MCP tools, and the memory skill. |
| **Sub-agent** | An ephemeral Claude Code CLI instance (`claude -p`) spawned by the bridge. One-shot, stateless, no Layer 1 memory. |
| **Layer 1** | Anthropic's built-in memory. Auto-generated summary (~500–2,000 tokens) injected into every conversation. Influenced indirectly via `memory_user_edits` steering instructions. ~24-hour lag for updates. |
| **Layer 2** | Our supplementary memory system. Markdown files at `C:\franl\.claude-agent-memory\`. Under our full control. Updates are immediate. Accessed only through the bridge's memory-aware tools. |
| **MCP bridge** | The Go binary that serves as an MCP server, providing the nine memory-aware tools plus `spawn_agent`, `check_agent`, and `run_command` (twelve tools total). |
| **Filesystem extension** | Anthropic's official `@modelcontextprotocol/server-filesystem` MCP server. Provides `read_file`, `write_file`, `edit_file`, etc. Used for **non-memory** file operations only. The LLM never uses it on the memory directory. |
| **Handle** | An opaque 8-character lowercase alphanumeric identifier (e.g., `h7k3xy90`) minted by the bridge when a conversation calls `memory_start_conversation`. Required parameter on every memory tool call; echoed in every response. Identifies the conversation for read tracking and branch routing. |
| **Handle map** | The bridge's in-memory per-handle state: read baselines (which version of each block this handle last read) and the branch map (which blocks this handle has been branched on, and where each branch file lives). Persisted to the bridge state file. |
| **Read baseline** | The version signature (ModTime + size) of a block recorded when a handle reads it. Compared at write time to detect concurrent read-modify-write races. |
| **Branch (memory)** | A per-handle copy of a block file, created transparently when a write races with another conversation's intervening write. Named `<basename>.branch-<handle>-<ISO8601compact-UTC>.<ext>` (e.g., `core.branch-h7k3xy90-20260520T142300Z.md`). The racing handle's subsequent reads and writes of that block are routed to its branch. Invisible to the LLM. |
| **Merge (memory)** | A semantic merge process that reconciles a branched block with its base file, performed by a bridge-invoked sub-agent during `memory_run_maintenance`. The merger reads both versions, understands the meaning of each set of changes, and produces a unified result. |
| **Derived index** | The block index returned by `memory_get_index`. Not a stored file — the bridge derives it on demand from the `summary` and `updated_at` YAML frontmatter inside each block, with a per-handle cache. |
| **Bridge state file** | `.bridge-state.json` in the memory directory. Persists live handles, branch maps, and read baselines across bridge restarts (written at shutdown and at debounced checkpoints). |
| **Write mutex** | A Go `sync.Mutex` in the bridge process that serializes all memory file I/O. Prevents concurrent conversations from interleaving or corrupting memory updates. |
| **Memory skill** | The .zip file uploaded to Claude Desktop containing SKILL.md — instructions for managing Layer 2 memory. |
| **Sync window** | The 25-second window during which `spawn_agent` and `run_command` wait for their subprocess to complete before switching to async mode. Sized to stay safely under Claude Desktop's ~30-second reliability threshold. Shared implementation via the async executor (see [Chapter 3, Section 3.20](stateful-agent-design-chapter3.md#320-async-executor)). |
| **Block** | An individual markdown file in the `blocks/` directory, addressed by the LLM via a block *name* (filename without extension). Each block covers a project, topic, or time period. |

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
│  │  Memory tools:       │  │                              │      │
│  │  • memory_start_     │  │  Tools:                      │      │
│  │      conversation    │  │  • read_file                 │      │
│  │  • memory_get_core   │  │  • write_file                │      │
│  │  • memory_write_core │  │  • edit_file                 │      │
│  │  • memory_get_index  │  │  • create_directory          │      │
│  │  • memory_get_block  │  │  • list_directory            │      │
│  │  • memory_write_     │  │  • search_files              │      │
│  │      block           │  │  • ... (11 tools total)      │      │
│  │  • memory_append_    │  │                              │      │
│  │      block           │  │  Allowed dirs:               │      │
│  │  • memory_append_    │  │  • C:\franl                  │      │
│  │      episodic        │  │  • C:\temp                   │      │
│  │  • memory_run_       │  │  • C:\apps                   │      │
│  │      maintenance     │  │  (NOT used for the memory    │      │
│  │                      │  │   directory)                 │      │
│  │  Agent tools:        │  │                              │      │
│  │  • spawn_agent       │  │                              │      │
│  │  • check_agent       │  │                              │      │
│  │  • run_command       │  │                              │      │
│  │       │              │  │                              │      │
│  │       │ subprocess   │  │                              │      │
│  │       ▼              │  │                              │      │
│  │  ┌────────────┐      │  │                              │      │
│  │  │ claude -p  │      │  │                              │      │
│  │  │ (sub-agent)│      │  │                              │      │
│  │  └────────────┘      │  │                              │      │
│  └──────────────────────┘  └──────────────────────────────┘      │
│                                                                  │
│  Local filesystem: C:\franl\.claude-agent-memory\                │
│  ├── core.md                                                     │
│  ├── .bridge-state.json     (bridge-internal state)              │
│  └── blocks\                                                     │
│      ├── project-*.md                                            │
│      ├── reference-*.md                                          │
│      ├── episodic-YYYY-MM.md                                     │
│      ├── decisions.md                                            │
│      └── *.branch-<handle>-<timestamp>.md   (transient,          │
│            bridge-internal, merged by maintenance)               │
└──────────────────────────────────────────────────────────────────┘
```

Note that there is no `index.md` — the index is derived on demand from block frontmatter (see [Chapter 4, Section 4.4](stateful-agent-design-chapter4.md#44-the-derived-index)). Branch files and `.bridge-state.json` are bridge-internal artifacts; the LLM never sees or references them.

### 2.2 Data Flow

**Conversation start:**
```
Claude LLM
  → calls Bridge:memory_start_conversation()
  → Bridge mints a unique opaque handle (e.g., "h7k3xy90")
  → Bridge registers the handle in its handle map (and checkpoints state)
  → Returns { handle, core, index } — core.md content and the derived
    index are included so conversation start is a single round trip
```

**Memory read (during conversation):**
```
Claude LLM
  → calls Bridge:memory_get_block(handle, name)
  → Bridge acquires write mutex
  → Bridge resolves name → file path; if this handle has a branch of
    this block, the branch file is read instead (invisible routing)
  → Bridge records the read baseline (ModTime + size) for this handle
  → Returns { handle, ok, content, changed_since_last_read }
  The LLM never uses Filesystem:read_file for memory — block names,
  not paths, are the only memory addresses it knows.
```

**Memory write (during conversation):**
```
Claude LLM
  → calls Bridge:memory_write_block(handle, name, content[, summary])
  → Bridge acquires write mutex
  → Bridge compares the block's current version signature against this
    handle's read baseline
  → No race: atomic write (temp file + rename) updates the base block,
    preserving/updating YAML frontmatter (summary, updated_at)
  → Race detected: write is routed to this handle's branch of the block
    (creating it if needed); base block is untouched; response is
    indistinguishable from the no-race case
  → Returns { handle, ok }
```

**Maintenance (user-triggered):**
```
User: "Please run memory maintenance."
Claude LLM
  → calls Bridge:memory_run_maintenance(handle)
  → Bridge merges pending branches (up to maintenance.max_blocks_per_call
    blocks per call) via semantic-merge sub-agents, holding the merge mutex
  → Bridge sweeps stale handles and deletes merged branch files
  → Returns { handle, ok, merged_blocks, more_pending }
  → If more_pending is true, Claude calls it again until false
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

- Non-memory filesystem tools (list, search) — handled by the Filesystem extension. The bridge's memory tools are specifically and exclusively for the memory directory; all non-memory file operations use the Filesystem extension.
- Network request tools (http_get, http_post) — deferred. Sub-agents or `run_command` (e.g., `run_command("curl ...")`) can perform network operations. Dedicated network tools can be added to the bridge later if needed.
- Memory search (`memory_search`) — deferred to a near-term enhancement. In v1, the derived index's block summaries are the search surface. See [Chapter 11, Open Question #16](stateful-agent-design-chapter11.md).
- Automatic/scheduled maintenance — `memory_run_maintenance` is user-triggered in v1. Scheduled or idle-triggered maintenance is a future enhancement ([Chapter 9](stateful-agent-design-chapter9.md)).

This keeps the initial bridge focused: twelve tool handlers, a write mutex, the handle map with read baselines and branch routing, the derived-index builder, the state persistence layer, the maintenance/merge engine, the async executor, and the job lifecycle manager.

---

### 2.4 Supported Client Environments

The component diagram above shows Claude Desktop, which was the original and for some time the only
client. The system supports two:

| Client | Bridge transport | Skill installation | Notes |
|---|---|---|---|
| Claude Desktop | stdio, spawned as a child process | Uploaded `.zip` archive | The `description` frontmatter field is subject to a 200-character product limit ([Chapter 5, Section 5.7](stateful-agent-design-chapter5.md#57-frontmatter-constraints-and-portability)) |
| Claude Code | stdio, spawned as a child process | Filesystem copy into `~/.claude/skills/` | Registered at user scope; MCP tool definitions may be deferred, and sub-agents do not inherit MCP connections |

**The bridge binary is identical for both.** Nothing about the MCP interface differs between the
clients; they are distinguished only by how they are configured
([Chapter 7, Sections 7.2 and 7.8](stateful-agent-design-chapter7.md#7-build-and-deployment)) and by
the `--client-id` value each passes.

**Both may run at once.** Because each client spawns its own copy of the binary, concurrent use
means two bridge processes against one memory root. The single-writer assumptions that the original
design could safely make — a process-wide mutex serializing all memory I/O, one owner of
`.bridge-state.json` — no longer hold in that configuration. The provisions that restore them are
specified in [Chapter 3, Section 3.25](stateful-agent-design-chapter3.md#325-multi-bridge-concurrency)
and their deployment requirements in
[Chapter 7, Section 7.9](stateful-agent-design-chapter7.md#79-running-multiple-clients-concurrently).

**A note on the diagram.** The diagram in [Section 2.1](#21-component-diagram) is drawn from the
Claude Desktop perspective and has not been redrawn per-client. The Anthropic Filesystem extension
shown there is a Claude Desktop feature specifically; Claude Code provides its own file access and
does not use it. The bridge box and every memory tool in it apply unchanged to both clients.

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
2. **Design update plan:** [design-update-plan.md](design-update-plan.md) — The plan governing the version 2.0 rewrite: memory-aware tools, the handle protocol, invisible branching, the derived index, and bridge state persistence. Includes the full rationale and the resolution of eleven open questions.
3. **Memory-aware tools analysis:** [memory-aware-tools-analysis.md](memory-aware-tools-analysis.md) — The analysis that motivated replacing path-based file tools with memory-aware tools.
4. **Previous skill design (superseded):** [agent-memory-design.md](../../docs/agent-memory-design.md) — Earlier design for a standalone skill without MCP bridge. Concepts carried forward; implementation approach replaced.
5. **Tim Kellogg's Strix architecture:** [Memory Architecture for a Synthetic Being](https://timkellogg.me/blog/2025/12/30/memory-arch) — Three-tier hierarchical memory model that inspired our core/index/blocks structure.
6. **claude_life_assistant:** [GitHub](https://github.com/lout33/claude_life_assistant) — Luis Fernando's minimal stateful agent demonstrating the core concept.
7. **mark3labs/mcp-go:** [GitHub](https://github.com/mark3labs/mcp-go) — Go SDK for the Model Context Protocol.
8. **MCP specification:** [modelcontextprotocol.io](https://modelcontextprotocol.io) — Protocol specification for tool registration, stdio transport, and Streamable HTTP transport.
9. **Claude Code system prompts:** [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts) — Community-maintained extraction of Claude Code's default system prompt fragments.
10. **Anthropic Filesystem extension:** [@modelcontextprotocol/server-filesystem](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem) — Official MCP server providing 11 filesystem tools.

---

## 11. Open Questions

See [Stateful Agent System: Detailed Design – Chapter 11](stateful-agent-design-chapter11.md).

---

## 12. Appendix: mark3labs/mcp-go SDK Reference

See [Stateful Agent System: Detailed Design – Chapter 12](stateful-agent-design-chapter12.md).

## 13. Appendix: Implementation Ordering for Branching and Merging

See [Stateful Agent System: Detailed Design – Chapter 13](stateful-agent-design-chapter13.md). This appendix sequences the implementation of the branching and merging functionality that the minimal Layer 2 build omits, for the single-bridge case. It is a companion to the normative specification in [Chapter 3, Sections 3.15 and 3.17](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection).
