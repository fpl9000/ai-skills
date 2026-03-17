# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Contents

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
  - [4.10 Branching and Merge](#410-branching-and-merge)

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

When the bridge detects a concurrent read-modify-write race on a memory file, it writes the racing conversation's changes to a "branch" file instead of overwriting the base file. This preserves data from all concurrent conversations.

**Branch files are transient.** They exist only until a merge process reconciles them with the base file. They are not referenced by `index.md` (which always uses canonical filenames) and are not part of the permanent memory structure.

**`index.md` interaction:** The `Updated` column in `index.md` always reflects the most recent modification to a file *or any of its branches*. This ensures that index-based relevance decisions account for recent branch activity. File names in the `Block` column are always canonical (non-branched) names.

**Merge semantics:** Merges are *semantic*, not textual. A merge sub-agent reads the base file and all its branches, understands the meaning of each version's content, and produces a single unified file that preserves important information from all versions. This is necessary because memory files are prose markdown — a line-based three-way merge (as in `git merge`) would produce incoherent results when two conversations independently rewrite the same paragraph.

**Example scenario:**

1. Conversation A reads `core.md` (which lists Project X as "in progress").
2. Conversation B also reads `core.md`.
3. Conversation A updates `core.md` to mark Project X as "completed" and adds Project Y.
4. Conversation B attempts to update `core.md` to add a new preference. The bridge detects the race (file modified since B's read) and writes B's version to `core.branch-20260313T1423-a1b2.md`.
5. Later, a merge sub-agent reads both versions. It produces a merged `core.md` that marks Project X as "completed" (from A), includes Project Y (from A), and includes the new preference (from B). The branch file is deleted.

See [Chapter 3, Section 3.12](stateful-agent-design-chapter3.md#312-branching) for the branch file naming convention, detection mechanism, and merge process details.

