# Stateful Agent System: Detailed Design – Chapter 4

**Version:** 2.0 (Draft)  
**Date:** February - June 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)  
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.

## Contents

- [4. Memory System (Layer 2)](#4-memory-system-layer-2)
  - [4.1 Two-Layer Memory Model](#41-two-layer-memory-model)
  - [4.2 Three-Tier Structure](#42-three-tier-structure)
  - [4.3 File Format: core.md](#43-file-format-coremd)
  - [4.4 The Derived Index](#44-the-derived-index)
  - [4.5 File Format: Content Blocks](#45-file-format-content-blocks)
  - [4.6 File Format: Episodic Logs](#46-file-format-episodic-logs)
  - [4.7 File Format: decisions.md](#47-file-format-decisionsmd)
  - [4.8 Block Naming Conventions](#48-block-naming-conventions)
  - [4.9 Why Markdown (Not JSON, SQLite, or YAML)](#49-why-markdown-not-json-sqlite-or-yaml)
  - [4.10 Branching and Merge](#410-branching-and-merge)

## 4. Memory System (Layer 2)

### 4.1 Two-Layer Memory Model

The full memory system has two layers with distinct characteristics:

| | Layer 1 (Anthropic built-in) | Layer 2 (Supplementary) |
|---|---|---|
| **Storage** | Anthropic's cloud (opaque) | Local markdown files |
| **Capacity** | ~500–2,000 tokens (Anthropic-managed) | Unbounded (loaded on demand) |
| **Loaded when** | Every turn (automatic) | At conversation start + on demand |
| **Update mechanism** | Indirect via `memory_user_edits` steering instructions | Direct via the bridge's memory-aware tools (`memory_write_core`, `memory_write_block`, `memory_append_block`, `memory_append_episodic`) |
| **Update lag** | ~24 hours (nightly regeneration) | Immediate |
| **Content** | Identity, preferences, high-level project list | Deep project context, episodic recall, decisions, technical notes |
| **Editable by user** | Via Claude.ai Settings > Memory | Via any text editor |
| **Visible to sub-agents** | No (platform limitation) | Optional read-only access |

Layer 1 is always present and automatic. Layer 2 is opt-in, managed by the memory skill, and provides the depth that Layer 1 cannot. Together they approximate the functionality of purpose-built agent memory systems like Letta (formerly MemGPT), while maintaining full transparency and portability.

An important property of Layer 2 under the memory-aware tool design: the LLM addresses memory by **concept** (core, block names, the index), never by file path. The file formats documented in this chapter describe what is stored *on disk* — visible to the user in a text editor and to this design — but invisible to the LLM, which interacts only through the bridge tools of [Chapter 3, Section 3.7](stateful-agent-design-chapter3.md#37-memory-aware-tools-overview-and-abstraction).

### 4.2 Three-Tier Structure

Layer 2 is organized as a three-tier hierarchy inspired by Tim Kellogg's Strix architecture. The tiers correspond to access frequency and specificity:

```
C:\franl\.claude-agent-memory\
├── bridge-config.yaml           # MCP bridge configuration (not memory content)
├── .bridge-state.json           # Bridge-private persisted state (not memory content;
│                                #   see Chapter 3, Section 3.18)
├── bridge.log                   # Bridge server log (not memory content)
├── core.md                      # Tier 1: Identity (always loaded, ~500–1,000 tokens)
└── blocks\                      # Tier 3: Content (loaded on demand)
    ├── project-mcp-bridge.md    #   Project-specific context
    ├── project-agent-memory.md  #   Another project
    ├── reference-go-patterns.md #   Persistent reference material
    ├── decisions.md             #   Cross-project architectural decisions
    ├── episodic-2026-05.md      #   May 2026 conversation log
    ├── episodic-2026-06.md      #   June 2026 conversation log
    └── *.branch-*.*             #   Branch files (transient, created by the bridge's
                                 #   race detection, merged and deleted by maintenance)
```

Tier 2 — the index — no longer exists as a file. It is a **derived view** assembled on demand by the bridge from metadata stored inside each block file (see [Section 4.4](#44-the-derived-index)). There is no `index.md`.

**Loading rules:**

| Tier | Source | Loaded when | Approximate budget |
|------|--------|-------------|-------------------|
| Tier 1 | `memory_get_core` | Every conversation start, before first response | 500–1,000 tokens |
| Tier 2 | `memory_get_index` | Every conversation start, before first response | 300–800 tokens (scales with block count) |
| Tier 3 | `memory_get_block` | On demand, when the conversation topic matches an index entry | Varies per block |

The total fixed context cost per conversation is Tier 1 + Tier 2 + skill instructions ≈ 1,500–3,000 tokens. This is a bounded, predictable cost that does not grow as the memory store expands (only the number of index entries grows; the blocks themselves are loaded selectively).

### 4.3 File Format: core.md

The core file is a compact narrative summary — the Layer 2 equivalent of "who am I and what are we working on." It is pure prose markdown with **no YAML frontmatter**: it is always loaded in full and does not appear in the derived index, so it needs no machine-readable metadata. (This makes core the one Layer 2 file without frontmatter — see [Section 4.5](#45-file-format-content-blocks) for blocks.)

The LLM reads it with `memory_get_core` and replaces it with `memory_write_core`.

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
  See the `project-mcp-bridge` block for details.

- **Stateful Agent Memory** — The Layer 2 memory system itself. Designing the
  file formats, conversation lifecycle, and skill instructions. See the
  `project-agent-memory` block.

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

Note that cross-references inside core point to **block names** (`project-mcp-bridge`), not filenames — consistent with the vocabulary the LLM actually uses with the tools.

### 4.4 The Derived Index

The index maps each block name to a one-line summary and a last-updated timestamp. The LLM uses it to decide which blocks to load for the current conversation. In this design the index is **not a stored file**: each block's `summary` and `updated_at` live in YAML frontmatter inside the block file itself, and the bridge's `memory_get_index` tool assembles the index on demand by walking the blocks directory (with caching). See [Chapter 3, Section 3.10](stateful-agent-design-chapter3.md#310-tool-memory_get_index) for the assembly algorithm, per-handle view semantics, and cache design.

What the LLM receives from `memory_get_index`:

```json
{
  "handle": "abc1def2",
  "index": {
    "schema_version": 1,
    "blocks": [
      { "name": "decisions",            "summary": "Cross-project architectural decisions and rationale",            "updated_at": "2026-06-02T19:40:00Z" },
      { "name": "episodic-2026-06",     "summary": "Conversation log for June 2026",                                 "updated_at": "2026-06-11T22:05:00Z" },
      { "name": "project-mcp-bridge",   "summary": "MCP bridge server: Go implementation, tool design, testing",     "updated_at": "2026-06-10T15:12:00Z" },
      { "name": "reference-go-patterns","summary": "Go idioms, error handling patterns, and package conventions",    "updated_at": "2026-05-28T09:30:00Z" }
    ]
  }
}
```

**Why this replaced `index.md`:** the v1 design stored the index as a markdown table that Claude was instructed (by the skill) to keep in sync with the blocks — a compliance-based maintenance rule and a known failure mode. Worse, under the per-handle branching model a stored index would leak information across conversation boundaries: one conversation's summary updates would land in the shared index file while its block content was correctly isolated in a branch. Deriving the index from the same files that per-block reads use eliminates both problems by construction. **There is no index maintenance rule anymore** — the summary is supplied (optionally) with each `memory_write_block` call, travels inside the block file, and can never drift out of sync.

**For the user:** block metadata is still fully inspectable — open any block file and the summary/timestamp are in the frontmatter at the top. A human-readable index file no longer exists as part of normal operation.

### 4.5 File Format: Content Blocks

Content blocks are markdown files with a YAML frontmatter header that the **bridge manages transparently**. The frontmatter holds exactly the metadata the derived index needs; the body is free-form markdown optimized for Claude's comprehension.

**On-disk format:**

```markdown
---
summary: "MCP bridge server: Go implementation, tool design, testing status"
updated_at: 2026-06-10T15:12:00Z
---

# MCP Bridge Server

## Status
Implementation in progress. Core module structure defined. spawn_agent handler
is the current focus.

## Architecture
The bridge is a single Go binary that registers twelve MCP tools via the mcp-go SDK.
It communicates with Claude Desktop over stdin/stdout using MCP's stdio transport.
Sub-agents are launched as `claude -p` subprocesses.

## Open Issues
- Need to test hybrid sync/async with real Claude Desktop (not just unit tests)
- Determine if output truncation heuristic (chars/4) is accurate enough

## Technical Notes
- The sync window (25s) was chosen to stay under Claude Desktop's ~30s reliability
  threshold. See proposal Open Question #3.
```

**Division of responsibility for this format:**

- **The bridge** owns the frontmatter. `memory_get_block` strips it and returns only the body; `memory_write_block` composes it (the supplied or preserved `summary`, plus `updated_at` set to the write time) and writes frontmatter + body as one atomic file operation ([Chapter 3, Section 3.16](stateful-agent-design-chapter3.md#316-block-file-format-and-atomic-writes)). The LLM never sees, produces, or repairs frontmatter.
- **The LLM** owns the body and the summary text — it supplies both through `memory_write_block` parameters.
- **The user** can edit block files directly in a text editor. If an edit damages or removes the frontmatter, the bridge inserts default frontmatter on the next read or write rather than refusing the file.

**Schema evolution:** the frontmatter is naturally extensible. Future fields (e.g., `importance` — see [Chapter 9, Section 9.7](stateful-agent-design-chapter9.md#97-importance-scoring-on-blocks-and-episodic-entries)) can be added backwards-compatibly; removing or renaming fields requires a migration sweep at bridge startup.

### 4.6 File Format: Episodic Logs

Episodic logs are monthly files (`episodic-YYYY-MM.md`) containing dated entries for each significant conversation. They remain a **distinct concept** from ordinary blocks at the tool surface: the LLM appends entries with `memory_append_episodic(handle, content)` and never computes the current month's name — the bridge selects the target file from the system clock and handles month rotation internally ([Chapter 3, Section 3.12](stateful-agent-design-chapter3.md#312-tool-memory_append_episodic)).

On disk, episodic files live in the blocks directory and carry the standard frontmatter, with a bridge-generated summary. They therefore **appear in the derived index** (e.g., as `episodic-2026-06` with summary "Conversation log for June 2026") and can be read like any block via `memory_get_block`, using the name shown in the index. Each append refreshes the file's `updated_at` so the index reflects the time of the last entry.

**Example:**

```markdown
---
summary: "Conversation log for June 2026"
updated_at: 2026-06-11T22:05:00Z
---

# June 2026

## 2026-06-11 — Stateful agent design rewrite
Updated the design documents to the memory-aware tool architecture per the design
update plan. Chapter 3 restructured around the nine memory tools, handle model,
and state persistence.

## 2026-06-05 — Final open questions resolved
Resolved §3.5 (summary contract), §3.6 (index schema), and §3.8 (branch naming) in
the update plan. All eleven open questions now closed; rewrite unblocked.
```

**Entry format:** Each entry has a heading with date and brief title (`## YYYY-MM-DD — Title`), followed by a short prose summary (2–5 sentences). The summary should capture what was accomplished, any significant decisions, and any artifacts produced. It is deliberately concise — detailed project context belongs in project blocks, not in the episodic log.

**Appending new entries:** The memory skill instructs Claude to append a new entry before the conversation ends (or incrementally during long conversations) via `memory_append_episodic`. Appends are serialized by the bridge and never create branches ([Chapter 3, Section 3.11](stateful-agent-design-chapter3.md#311-tools-memory_get_block-memory_write_block-memory_append_block)).

### 4.7 File Format: decisions.md

A single cross-project block (block name `decisions`) for architectural decisions and their rationale. Unlike project blocks, this captures decisions that span projects or affect the overall system. It uses the standard block format of [Section 4.5](#45-file-format-content-blocks).

**Example:**

```markdown
---
summary: "Cross-project architectural decisions and rationale"
updated_at: 2026-06-02T19:40:00Z
---

# Architectural Decisions

## 2026-05-27 — Bridge state persisted across restarts
The bridge persists handles, the branch map, and read baselines to .bridge-state.json,
written on clean shutdown and at debounced checkpoints. Rationale: the bridge dies on
every Claude Desktop close, so in-memory-only state was discarded routinely; persistence
makes restarts transparent.

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

The LLM names blocks (when creating them via `memory_write_block`) and sees these names in the index. Block names may contain letters, digits, hyphens, and underscores; the bridge rejects anything else (`INVALID_BLOCK_NAME`). The `.md` extension is a storage detail — block *names* never include it.

| Pattern | Usage | Examples |
|---------|-------|---------|
| `project-<name>` | Active or completed projects | `project-mcp-bridge`, `project-website` |
| `reference-<topic>` | Persistent reference material | `reference-go-patterns`, `reference-deploy-checklist` |
| `episodic-YYYY-MM` | Monthly conversation logs (bridge-named via `memory_append_episodic`) | `episodic-2026-05`, `episodic-2026-06` |
| `decisions` | Cross-project architectural decisions | (Single block) |

**When to create a new block:** When a conversation introduces a significant new project or topic that warrants its own structured tracking, and the content doesn't fit naturally into an existing block. Trivial or one-off topics belong as entries in the episodic log, not as standalone blocks.

**When not to create a new block:** For temporary information, questions that are fully resolved in the current conversation, or topics that only need a brief mention (add to the episodic log instead).

### 4.9 Why Markdown (Not JSON, SQLite, or YAML)

This decision is fundamental and is not revisited in the design. The rationale:

| Format | Decision |
|--------|-----------------|
| **JSON** | *Rejected:* Not human-readable at scale. Requires programmatic tooling to inspect or edit. Not Git-diff-friendly for prose content. Claude reads text natively — markdown is optimal. |
| **SQLite** | *Rejected:* Opaque binary format. Cannot be inspected in a text editor or GitHub web UI. Merge conflicts are unresolvable. Overkill for the expected data volume (dozens of files, hundreds of KB). |
| **YAML** | *Rejected:* Fragile whitespace sensitivity. Poor for long-form prose. Acceptable for metadata (hence the bridge-managed frontmatter), but not for content bodies. |
| **Markdown** | *Accepted:* Human-readable, human-editable, Git-friendly diffs, viewable in any text editor or GitHub, Claude-native format, no parsing dependencies. Trade-off: lookups require reading files, not querying an index — acceptable at our scale. |

(The bridge-private `.bridge-state.json` is JSON, but it is operational state, not memory content — it is never read by a human as part of using the memory system.)

### 4.10 Branching and Merge

When the bridge detects a concurrent read-modify-write race on a memory target (core or a block), it transparently writes the racing conversation's changes to a per-handle "branch" file instead of overwriting the base file. This preserves data from all concurrent conversations. **The LLM is never aware that branching happened** — its reads and writes are silently routed through its branch, every write appears to succeed, and read-your-own-writes is preserved. See [Chapter 3, Section 3.15](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection) for the branch model, naming convention, and race-detection mechanism.

**Branch files are transient.** They exist only until `memory_run_maintenance` reconciles them with the base file. They never appear in the derived index (the index walk enumerates base files, substituting the calling handle's own branch content where one exists) and are not part of the permanent memory structure. They are named `<basename>.branch-<handle>-<timestamp>.<ext>` (e.g., `core.branch-h7k3xy90-20260520T142300Z.md`), so a user inspecting the directory can attribute each branch to the conversation that owns it.

**Merge semantics:** Merges are *semantic*, not textual, and run only during user-triggered maintenance ([Chapter 3, Section 3.17](stateful-agent-design-chapter3.md#317-merge-process-and-merge-mutex)). A merge sub-agent reads the base file and all its branches, understands the meaning of each version's content, and produces a single unified document preserving the important information from all versions; the bridge then atomically replaces the base, deletes the branches, and regenerates the frontmatter. A line-based three-way merge (as in `git merge`) would produce incoherent results when two conversations independently rewrite the same paragraph of prose.

**Example scenario:**

1. Conversation A (handle `a1a1a1a1`) reads the `project-x` block (status: "in progress").
2. Conversation B (handle `b2b2b2b2`) also reads `project-x`.
3. A writes `project-x`, marking it "completed". No race (A's baseline matched), so the base file is updated.
4. B writes `project-x` to add a new technical note. The bridge detects the race (base changed since B's read) and silently routes B's write to `project-x.branch-b2b2b2b2-20260612T101500Z.md`. B's response is `{ ok: true }` — B never knows.
5. B re-reads `project-x` later in its conversation and sees its own version (read-your-own-writes via the branch). A continues to see the base.
6. Days later the user asks for memory maintenance. The merge sub-agent reads both versions and produces a merged `project-x` that is marked "completed" (from A) and includes the new technical note (from B). The bridge replaces the base, deletes the branch, and clears the branch-map entry. Both conversations' future reads see the merged content (each will get `changed_since_last_read: true` on its first read after the merge).
