# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>

**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Contents

- [9. Future Enhancements](#1-overview)
  - [9.1 FTS5 Search Index (Option 3)](#11-fts5-search-index-option-3)
  - [9.2 Memory-Aware Tools](#12-memory-aware-tools)
  - [9.3 Architecture B2 Upgrade](#13-architecture-b2-upgrade)
  - [9.4 GitHub Backup Automation](#14-github-backup-automation)
  - [9.5 Remote Access: Mobile-to-Local Communication](#95-remote-access-mobile-to-local-communication)
    - [9.5.1 Dispatch Integration (Preferred Path)](#951-dispatch-integration-preferred-path)
    - [9.5.2 GitHub Relay (Fallback)](#952-github-relay-fallback)
    - [9.5.3 Architecture B2 as Long-Term Solution](#953-architecture-b2-as-long-term-solution)
  - [9.6 Proposed Solution to Concurrent Read-Modify-Write Race Condition](#16-proposed-solution-to-concurrent-read-modify-write-race-condition)

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


### 1.6 Proposed Solution to Concurrent Read-Modify-Write Race Condition

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
