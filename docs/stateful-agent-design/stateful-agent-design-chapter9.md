# Stateful Agent System: Detailed Design

**Version:** 2.0 (Draft)  
**Date:** February - June 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)  
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.
- [Design Update Plan](design-update-plan.md) — the plan that produced this version 2.0 rewrite.

## Contents

- [9. Future Enhancements](#9-future-enhancements)
  - [9.1 FTS5 Search Index (Option 3)](#91-fts5-search-index-option-3)
  - [9.2 Memory-Aware Tools](#92-memory-aware-tools)
  - [9.3 Architecture B2 Upgrade](#93-architecture-b2-upgrade)
  - [9.4 GitHub Backup Automation](#94-github-backup-automation)
  - [9.5 Remote Access: Mobile-to-Local Communication](#95-remote-access-mobile-to-local-communication)
    - [9.5.1 Dispatch Integration (Preferred Path)](#951-dispatch-integration-preferred-path)
    - [9.5.2 GitHub Relay (Fallback)](#952-github-relay-fallback)
    - [9.5.3 Architecture B2 as Long-Term Solution](#953-architecture-b2-as-long-term-solution)
  - [9.6 Proposed Solution to Concurrent Read-Modify-Write Race Condition](#96-proposed-solution-to-concurrent-read-modify-write-race-condition)
  - [9.7 Importance Scoring on Blocks and Episodic Entries](#97-importance-scoring-on-blocks-and-episodic-entries)
  - [9.8 Reflection Synthesis for Episodic Logs](#98-reflection-synthesis-for-episodic-logs)
  - [9.9 A `reflections.md` Block Type](#99-a-reflectionsmd-block-type)

## 9. Future Enhancements

These are planned upgrades that are deliberately deferred from the initial implementation. Each addresses a limitation documented in the proposal. This document references terms and concepts from *[Stateful Agent Design](stateful-agent-design.md)* without definition, so please read that design first.

This document was previously section 9, "Future Enhancements", in that design.

### 9.1 FTS5 Search Index (Option 3)

**Trigger:** When the number of blocks exceeds ~50 and summary-based retrieval from the derived index becomes cumbersome. See also [Chapter 11, Open Question #16](stateful-agent-design-chapter11.md), which covers the nearer-term need for a `memory_search` tool under the memory-aware abstraction.

**Design:** Add a SQLite FTS5 full-text search index alongside the markdown files. The index is a derived artifact — it can be rebuilt from the markdown files at any time.

```
C:\franl\.claude-agent-memory\
├── core.md
├── .bridge-state.json
├── blocks\
│   └── ...
└── .search-index.db     # SQLite FTS5 (in .gitignore)
```

**New tool:** `memory_search(handle, query: string, max_results: int) → [{block, snippet, score}]` — results identify blocks by *name*, consistent with the memory-aware tool abstraction (no file paths).

**Implementation:** Use `modernc.org/sqlite` (pure Go, no CGO) or `mattn/go-sqlite3` for the SQLite driver. Because all memory writes already flow through the bridge's memory-aware tools, maintaining the FTS5 index is a natural post-write hook inside `memory_write_core`, `memory_write_block`, and the append tools — no filesystem polling needed. (Direct user edits in a text editor would be picked up by a rebuild during `memory_run_maintenance`.)

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

**Status: implemented in version 2.0 of this design — no longer a future enhancement.**

This section originally proposed memory-aware tools (`update_memory_block`, `create_memory_block`, `append_episodic_log`) as a contingency for when compliance-based memory management proved insufficient — Claude forgetting to update the index, corrupting YAML frontmatter, or using incorrect naming conventions. Exactly those failure modes (plus the "unambiguous tool names" benefit from proposal Open Question #22) motivated the version 2.0 redesign, which replaced the path-based `safe_*` file tools with a full family of nine memory-aware tools and an opaque handle protocol. See [Chapter 3](stateful-agent-design-chapter3.md) for the implemented design and the [Design Update Plan](design-update-plan.md) for the analysis and rationale.

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

| Limitation                                                                                                                                                                             | Impact                                                                                                           |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Mac-only.** Dispatch requires the Claude Mac app; our system runs on Windows 11.                                                                                                     | Blocking. No Windows support means Dispatch cannot be used at all.                                               |
| **Cowork, not Claude Desktop.** Dispatch drives a Cowork session (sandboxed folder, Agent SDK). Our bridge is an MCP server that speaks stdio to Claude Desktop — a different runtime. | Blocking. Dispatch has no access to bridge tools (the memory-aware tools, `spawn_agent`, `run_command`, etc.).         |
| **No MCP bridge access.** Cowork sessions do not currently expose user-configured MCP servers.                                                                                         | Blocking. Even on Mac, Dispatch wouldn't reach the bridge's memory tools, handle tracking, or sub-agent system. |
| **Research preview maturity.** Early testing reports ~50% success rate, slow performance, inability to interact with most apps.                                                        | Non-blocking but concerning. Expected to improve.                                                                |
| **No programmatic API.** Dispatch is a human-facing UI, not an API. Cannot be driven by automation, webhooks, or other agents.                                                         | Non-blocking for the primary use case (human on phone), but limits future integration.                           |

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
3. **Full tool access.** All bridge tools are available — the nine memory-aware tools (`memory_start_conversation`, `memory_get_core`, `memory_write_core`, `memory_get_index`, `memory_get_block`, `memory_write_block`, `memory_append_block`, `memory_append_episodic`, `memory_run_maintenance`) plus `spawn_agent`, `check_agent`, and `run_command` — with the same handle tracking and mutex protection as local use.
4. **Platform-independent.** Works from any Claude client (web, mobile, API) with custom MCP connector support, regardless of OS.

The B2 upgrade is deferred because it requires Cloudflare Tunnel setup and OAuth 2.1 authentication — operational complexity that isn't justified until the base system is stable and proven. But it should be the preferred path once the system matures, rendering both the relay and Dispatch integration moot.

**Relationship between the three approaches:**

| Approach | Prerequisites | Latency | Tool access | Status |
|----------|--------------|---------|-------------|--------|
| **Dispatch** | Windows support, MCP in Cowork | ~seconds | Cowork tools only | Monitor (research preview) |
| **GitHub Relay** | Relay repo, HMAC secret, bridge relay goroutine | 15 sec–5 min | Full bridge tools (via relay) | Spec complete, deferred |
| **Architecture B2** | Cloudflare Tunnel, OAuth 2.1, Streamable HTTP | Sub-second | Full bridge tools (direct MCP) | Deferred (long-term) |


### 9.6 Proposed Solution to Concurrent Read-Modify-Write Race Condition

**Status: implemented (in evolved form) in version 2.0 of this design — preserved here as a historical stub.**

This section originally proposed solving the concurrent read-modify-write race by having the bridge's write tools perform optimistic concurrency control and "branch" a memory file when a race was detected, with branches merged later by a sub-agent. The proposal was adopted and substantially evolved in the version 2.0 redesign: races are detected via per-handle read baselines (version signature = ModTime + size), branches are *per-handle* and completely invisible to the LLM (reads and writes are transparently routed to the handle's branch), branch filenames follow `<basename>.branch-<handle>-<ISO8601compact-UTC>.<ext>`, and merging happens via the user-triggered `memory_run_maintenance` tool. See [Chapter 3, Sections 3.15 and 3.17](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection).

The open QUESTIONS this section posed were all resolved by the [Design Update Plan](design-update-plan.md): version tracking uses an internal mapping (read baselines) rather than hashes or frontmatter timestamps; branch creation time is captured in the branch filename (informational only) and branch state is persisted in `.bridge-state.json`; the conversation identity is passed explicitly as the opaque `handle` parameter on every memory tool call; and the branch naming convention is as given above.

---

### 9.7 Importance Scoring on Blocks and Episodic Entries

**Inspiration:** The [HermitClaw](https://github.com/brendanhogan/hermitclaw) agent, which implements the memory architecture from [Park et al., 2023](https://arxiv.org/abs/2304.03442), assigns every memory object an importance score (1–10, LLM-evaluated) at write time. This score is then combined with recency and semantic relevance at retrieval time to rank memories. Computing importance eagerly at write time is cheap; recomputing it at every retrieval would be expensive.

**Motivation:** Claude currently makes block-loading decisions by matching the current conversation's topic against the one-line block summaries in the derived index. This handles *relevance* well, but *importance* is invisible — two blocks might both match the current topic, while one contains a critical architectural decision and the other contains a routine note. Without importance scores, Claude has no principled way to prioritize.

**Trigger:** When block count grows to the point where index topic-matching alone produces ambiguous or low-confidence loading decisions.

**Design:** Add an `importance` field (integer, 1–10) to the bridge-managed YAML frontmatter of content blocks. Because frontmatter is owned by the bridge in version 2.0 (the LLM never sees or writes it), this requires a small bridge change: an optional `importance` parameter on `memory_write_block` (preserved across updates, like `summary`), with the value stored in the frontmatter and surfaced as a field in the derived index. The memory skill's write instructions include a single additional step: when writing a block, assign an importance score using this scale:

| Score | Meaning |
|-------|---------|
| 1–3 | Routine notes, transient context, easily reconstructed information |
| 4–6 | Useful project context, preferences, resolved questions |
| 7–8 | Significant decisions, design constraints, hard-won knowledge |
| 9–10 | Foundational decisions that affect the entire system; rarely changes |

```yaml
---
summary: MCP bridge server: Go implementation, tool design
updated_at: 2026-05-02T14:23:00Z
importance: 8          # 1=routine notes, 10=foundational/system-wide decision
---
```

(The `summary` and `updated_at` fields are the existing bridge-managed frontmatter; `importance` is the addition.)

For episodic log entries, importance is recorded as a parenthetical annotation on the section heading, keeping the cost to a single added token cluster per entry:

```markdown
## 2026-05-02 — Branching race condition resolved (importance: 9)
Merged PR #27. HMAC authentication protocol for relay finalized. ...
```

The derived index (returned by `memory_get_index`) would surface an `importance` field to make the signal available at the index scan stage, before any block is loaded:

```json
[
  { "name": "decisions",
    "summary": "Cross-project architectural decisions and rationale",
    "importance": 9,
    "updated_at": "2026-05-02T14:23:00Z" },
  { "name": "project-mcp-bridge",
    "summary": "MCP bridge server: Go implementation, tool design",
    "importance": 7,
    "updated_at": "2026-05-01T09:10:00Z" }
]
```

**Implementation cost:** Low, but no longer zero on the bridge side: an optional tool parameter, one frontmatter field, and one derived-index field. The skill change remains a single added instruction. Existing blocks can be back-filled with importance scores during any routine memory maintenance session (each back-fill is an ordinary `memory_write_block` call with the `importance` parameter).

**Relationship to Section 9.1 (FTS5 Search):** If a search index is later added, the `importance` field becomes a first-class filter and sort key in search queries — e.g., `memory_search(handle, "race condition", min_importance=7)`.

---

### 9.8 Reflection Synthesis for Episodic Logs

**Inspiration:** HermitClaw's reflection mechanism (inherited from Park et al., 2023) periodically synthesizes raw memory observations into higher-level insight statements — "reflections" — which are stored back into the memory stream as first-class objects. Over time, reflections accumulate at increasing levels of abstraction, capturing patterns that no individual memory entry makes explicit.

**Motivation:** Episodic log files (`episodic-YYYY-MM.md`) accumulate entries indefinitely. An aging month's file is unlikely to be loaded in a typical session, yet it may contain *implicit insights* — patterns about effective approaches, recurring mistakes and corrections, stable preferences confirmed by experience — that are never extracted and promoted to where they'd actually be useful. The episodic log faithfully records *what happened*; reflection synthesis extracts *what was learned*.

**Trigger:** When a month's episodic file is 3+ months old and therefore unlikely to be loaded in normal sessions. This can be checked opportunistically at the start of off-hours maintenance cycles.

**Process:**

1. A maintenance sub-agent reads the aging episodic file in full.
2. It identifies any content that has become a *persistent fact* — likely to remain relevant beyond that specific month. Categories:
   - Behavioral preferences confirmed by experience (→ `core.md`)
   - Project decisions whose rationale should survive the project context (→ `decisions.md`)
   - Patterns or lessons that apply across conversations (→ `reflections.md`, see Section 9.9)
   - Significant technical discoveries relevant to an active project block (→ that project block)
3. The identified content is promoted to its target location using the normal block-write path (with importance scoring per Section 9.7).
4. The episodic file is condensed in place: prose entries are replaced by one-sentence structural summaries, preserving the date/title scaffold as an audit trail while dramatically reducing token cost if the file is ever loaded again.

**Example — before condensation:**

```markdown
## 2026-02-19 — Proposal session 9: Hybrid sync/async execution
Discovered Claude Desktop's 60-second MCP timeout. Redesigned spawn_agent with hybrid
sync/async model. Resolved Open Questions #18 (system prompt), #4 (layer reconciliation),
#10 (concurrent writes), #9 (layer boundary), #19 (CLAUDE.md optimization). The 25-second
sync window was chosen to stay under Claude Desktop's ~30-second reliability threshold.
```

**After condensation:**

```markdown
## 2026-02-19 — Proposal session 9: Hybrid sync/async execution *(condensed)*
Resolved OQs #4, #9, #10, #18, #19. Key outcome: hybrid sync/async spawn_agent design.
See decisions.md for rationale.
```

**Promoted to `decisions.md`:**

```markdown
## 2026-02-19 — Hybrid sync/async execution model (importance: 9)
spawn_agent uses a 25-second sync window chosen to stay under Claude Desktop's ~30-second
reliability threshold. Tasks completing within the window return results directly; longer
tasks return a job_id for async polling. Rationale: simpler than progress tokens, no
protocol extensions needed, enables parallel sub-agents as natural extension.
```

**Implementation cost:** Medium. Requires a maintenance sub-agent capable of reading an episodic file, classifying content, writing to multiple target files, and condensing the source file — all in a single pass. Note that in the version 2.0 single-writer model the sub-agent itself does not write memory: like the maintenance merge sub-agents (see [Chapter 6, Section 6.6](stateful-agent-design-chapter6.md#66-sub-agent-memory-access-rules)), it returns its outputs and the bridge (or the primary agent, via `memory_write_block` / `memory_append_block`) performs the writes. No new bridge tools are needed. The primary cost is authoring the sub-agent prompt and skill instructions carefully enough that the classification step is reliable.

**Relationship to Section 9.6 (Race Condition):** The condensation write to the episodic file is a full rewrite (`memory_write_block`), which means it is subject to the per-handle branching race detection mechanism. Since reflection synthesis runs during maintenance with no concurrent conversations expected, this is unlikely to be a problem in practice.

---

### 9.9 A `reflections.md` Block Type

**Inspiration:** HermitClaw's depth-1 and depth-2 reflections capture *meta-level* insights about how the agent operates — not facts about specific projects, but patterns in how it thinks, what approaches consistently succeed, and what failure modes recur. These reflections are distinct from decisions (which are project-scoped), references (which are domain knowledge), and episodic logs (which are chronological records). They form a separate category: *learned operational patterns*.

**Motivation:** The current block taxonomy — `project-*.md`, `reference-*.md`, `episodic-YYYY-MM.md`, `decisions.md` — covers what work was done and what was decided, but has no natural home for meta-level patterns. Examples of content that belongs in this category but currently has no clear destination:

- *"When a session ends mid-task on a Go project, the next session works best if it reads the relevant project block before any other context — resuming without it consistently causes repeated groundwork."*
- *"Fran's approach to ambiguous architectural questions reliably starts with the minimal-viable option, not the optimal one. Proposals that lead with the ideal design tend to stall."*
- *"Reflection synthesis passes (Section 9.8) should not be triggered mid-session — the token cost of reading a full episodic file competes with the active task."*

**Design:** Add a single `reflections.md` block in the `blocks/` directory. Unlike other blocks, it is not created directly during conversations — it is populated exclusively by reflection synthesis passes (Section 9.8) and periodic maintenance. The block uses the standard YAML frontmatter format with a high default importance score (since operational patterns are broadly applicable), organized by theme:

```markdown
---
summary: Learned operational patterns derived from episodic synthesis
updated_at: 2026-05-15T10:00:00Z
importance: 8
---

# Operational Reflections

## Session Continuity
- Starting a session that resumes a Go project without first reading the project block
  consistently causes repeated groundwork. Always load the relevant project block before
  responding on first turn. *(derived: 2026-05 from episodic-2026-02, episodic-2026-03)*

## Architectural Approach
- Fran's default problem-solving mode leads with the minimal-viable option before the
  optimal one. Proposals structured the other way tend to stall at the review stage.
  *(derived: 2026-05 from episodic-2026-02, episodic-2026-04)*

## Maintenance Scheduling
- Reflection synthesis passes should not run mid-session; the full episodic file read
  competes with the active task's context budget. Schedule for off-hours only.
  *(derived: 2026-05)*
```

The `*(derived: ...)` annotation records the source episodic files from which the reflection was extracted, providing an audit trail analogous to HermitClaw's `references` field on reflection memory objects.

**Derived index entry** (as returned by `memory_get_index`, assuming the Section 9.7 `importance` field):

```json
{ "name": "reflections",
  "summary": "Learned operational patterns derived from episodic synthesis",
  "importance": 8,
  "updated_at": "2026-05-15T10:00:00Z" }
```

**Loading behavior:** The `reflections` block should be loaded opportunistically (via `memory_get_block`) — when the session involves meta-level questions about how to work effectively, when beginning a new project phase, or when the skill detects that `core.md` does not already address the relevant pattern. It should *not* be loaded by default on every session start, as its content is already incorporated into `core.md` for the most stable patterns.

**Implementation cost:** Low, contingent on Section 9.8 being implemented first. The block format requires no new bridge tooling. The main investment is the synthesis prompt that correctly identifies meta-level patterns versus project-specific decisions during the episodic condensation pass.
