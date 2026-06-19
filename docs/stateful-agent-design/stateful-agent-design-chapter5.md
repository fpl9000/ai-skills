# Stateful Agent System: Detailed Design

**Version:** 2.0 (Draft)  
**Date:** February - June 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)  
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.
- [Design Update Plan](design-update-plan.md) — the decision record for the memory-aware tools redesign incorporated into this version.

## Contents

- [5. Memory Skill](#5-memory-skill)
  - [5.1 Skill Packaging](#51-skill-packaging)
  - [5.2 SKILL.md Content](#52-skillmd-content)
  - [5.3 Conversation Lifecycle](#53-conversation-lifecycle)
  - [5.4 Memory Write Triggers](#54-memory-write-triggers)
  - [5.5 Memory Read Triggers](#55-memory-read-triggers)
  - [5.6 Reconciliation with Layer 1](#56-reconciliation-with-layer-1)

## 5. Memory Skill

The memory-aware tool redesign makes this the most-simplified chapter of the design. The v1 skill had to teach Claude the storage model: file paths, session IDs, branch annotations, index maintenance, race recovery, and a list of forbidden tools. All of that is now enforced by the bridge in code. What remains for the skill is the part that genuinely requires judgment: **when** to read and write memory, **what** to store, and **how** to structure it. The skill teaches lifecycle and content quality; the bridge guarantees storage correctness.

### 5.1 Skill Packaging

The memory skill is a Claude Desktop skill packaged as a .zip file containing a single `SKILL.md` file. It does not contain scripts (all operations use the bridge's MCP tools). The .zip is uploaded via Claude Desktop > Settings > Capabilities.

```
stateful-memory.zip
└── SKILL.md           # Instructions for Layer 2 memory lifecycle
```

**Why no scripts?** All memory operations are performed via the bridge's memory-aware MCP tools. No Python or shell scripts are needed. This eliminates dependency management and makes the skill trivially portable.

### 5.2 SKILL.md Content

The SKILL.md below is the complete skill instruction file. It is the primary artifact that guides Claude's memory behavior. Note its brevity relative to the v1 skill: there are no file paths, no session-ID bookkeeping, no branch-handling instructions, and no index-maintenance rules — the bridge owns all of that.

```markdown
# Stateful Agent Memory Skill

You have access to a persistent memory system that survives across conversations
and gives you deep context about the user, their projects, and your shared history.
You interact with it exclusively through the bridge's memory tools. You never need
to know how or where memory is stored.

## The Memory Model

- **Core** — a compact always-loaded summary: who the user is, active projects,
  key preferences. Read it with `memory_get_core`; replace it with `memory_write_core`.
- **Blocks** — named content documents (e.g., `project-foo`, `decisions`,
  `reference-go-patterns`). Read with `memory_get_block`, write with
  `memory_write_block`, append with `memory_append_block`.
- **The index** — a list of every block's name, one-line summary, and last-updated
  time, returned by `memory_get_index`. Use it to decide which blocks to load.
- **The episodic log** — a chronological record of significant conversations.
  Add entries with `memory_append_episodic`; past months appear in the index as
  `episodic-YYYY-MM` blocks.

## Handles

Call `memory_start_conversation` once at the start of any conversation that will
use memory. It returns a `handle` — an opaque token identifying this conversation.
Pass the handle to every memory tool call, always using the most recently returned
value (every memory tool response echoes it back).

If any memory tool returns a handle error, the recovery is always the same:
call `memory_start_conversation` to get a fresh handle, then retry the operation.

## Conversation Start Protocol

At the start of every conversation, BEFORE responding to the user's first message:

1. Call `memory_start_conversation` to get a handle.
2. Call `memory_get_core(handle)`.
3. Call `memory_get_index(handle)`.
4. If any index entry is relevant to the user's opening message, load it with
   `memory_get_block(handle, block_name)`.
5. Respond to the user, informed by your loaded context.

If core comes back empty, this is a first-run scenario: write an initial core with
`memory_write_core`, seeded from your built-in memory and the current conversation.

## During the Conversation

### Reading
- When the conversation shifts to a topic listed in the index that you haven't
  loaded, read that block.
- When the user asks "what do you remember about X?", check the index for matching
  blocks and read them. If the index summaries are too terse to identify the right
  block, read the most plausible candidates. Combine with your built-in (Layer 1)
  memory and respond naturally, as if recalling from your own knowledge.

### Stale content
A `memory_get_core` or `memory_get_block` response may include
`changed_since_last_read: true`. This means the content has been updated since you
last read it. Treat any earlier reasoning that depended on the previous version as
potentially stale — double-check anything you concluded from it before relying on it.

### Writing
Write memory updates incrementally as significant information emerges. Do NOT
accumulate changes and batch-write at the end — conversations can end abruptly.

- **Update core** (`memory_write_core`) when a project starts or significantly
  changes status, or when key facts about the user change. Provide the COMPLETE
  document (full replacement). Keep core under ~1,000 tokens; move detail to blocks.
- **Update a block** (`memory_write_block`) when significant project decisions are
  made, technical details worth remembering emerge, or the user shares information
  useful in future conversations. Provide the COMPLETE content (full replacement).
  The optional `summary` parameter sets the block's one-line index description:
  REQUIRED when creating a new block; omit it on updates unless the summary needs
  to change.
- **Append to a block** (`memory_append_block`) when adding to a running list or
  log-style block without rewriting it.
- **Append to the episodic log** (`memory_append_episodic`) periodically during
  long conversations, at natural breakpoints, and when the user is wrapping up.
  Format: `## YYYY-MM-DD — Brief Title` followed by a 2–5 sentence summary.

### Creating new blocks
If a conversation introduces a significant new project or topic that doesn't fit an
existing block, create one with `memory_write_block` (a `summary` is required):
- Projects: `project-<name>`
- Reference material: `reference-<topic>`
Do NOT create blocks for trivial or one-off topics — those go in the episodic log.

### Memory quality guidelines
- Be concise. Memory content is loaded into your context window — every token counts.
- Prefer facts and decisions over process narrative. "Chose Go for single-binary
  deployment" is better than "We discussed several languages and eventually...".
- Date-stamp significant decisions and status changes.
- Write summaries that will let a future conversation decide whether to load the
  block — name the topic and its key contents, not just a title.

## Memory Maintenance

If the user asks you to run memory maintenance, merge memory, consolidate memory,
or similar: call `memory_run_maintenance(handle)`. This consolidates memory that
has accumulated from concurrent conversations back into a single canonical state.
The call may take a noticeable amount of time, and memory operations in other
concurrent conversations will briefly block while it runs — that's expected, and
acceptable because the user asked for it. If the response has `more_pending: true`,
call it again to continue until `more_pending` is false, then report the total
number of merged blocks to the user.

## Error Handling

Memory tools may return `{ ok: false, error: { code, message } }`. The `message`
is written to be self-explanatory — read it and act on it. Common patterns:

- `INVALID_HANDLE` or `MALFORMED_HANDLE` → call `memory_start_conversation`, retry.
- `SUMMARY_REQUIRED` → retry with a one-line `summary` argument.
- `BLOCK_NOT_FOUND` → check the name against the index; create the block if creation
  was the intent.
- `MAINTENANCE_IN_PROGRESS` → memory is being consolidated; retry shortly.
- `INTERNAL_ERROR` → mention the failure to the user; do not retry blindly.

For any other code, follow the message's instructions.

## Conversation End

If the user says goodbye, thanks you, or the conversation is clearly winding down:

1. Persist any pending memory updates (core, relevant blocks).
2. Append an episodic entry summarizing the conversation.
3. You do not need to announce that you're saving memory — just do it.

## User Questions and Corrections

If the user asks to correct or delete a memory: read the relevant block (or core),
make the correction, write it back, and acknowledge.

If the user asks to see their memory: show them the relevant content from the tools.
You can mention that the underlying storage is plain markdown files on their machine
that they can edit directly — the bridge will pick up their edits.
```

### 5.3 Conversation Lifecycle

Detailed sequence of operations at each phase:

```
Conversation Start
│
├─ 1. Skill instructions loaded into context (automatic, ~400 tokens)
├─ 2. Layer 1 memory loaded into context (automatic, ~500–2,000 tokens)
├─ 3. Call memory_start_conversation → receive handle (echoed on every later call)
├─ 4. memory_get_core(handle) (~500–1,000 tokens)
├─ 5. memory_get_index(handle) (~300–800 tokens)
├─ 6. Evaluate user's first message against index entries
├─ 7. memory_get_block(handle, name) for any relevant blocks (varies)
└─ 8. Respond to user's first message
│
Conversation Active
│
├─ On topic change → check index, load relevant blocks (memory_get_block)
├─ On significant information → update the relevant block or core
│     (memory_write_block / memory_write_core)
├─ On new project/topic → create a new block (memory_write_block with summary)
├─ On decision made → update the decisions block or project block
├─ Periodically / at breakpoints → append episodic entry (memory_append_episodic)
├─ On changed_since_last_read: true → re-validate conclusions drawn from the
│     earlier version of that content
└─ On any handle error → memory_start_conversation, retry
│
Conversation End (if detectable)
│
├─ 1. Write pending updates (memory_write_core / memory_write_block)
├─ 2. Append an episodic entry summarizing the conversation (memory_append_episodic)
└─ 3. (No announcement needed — just persist silently)
```

Note what is *absent* from this lifecycle relative to v1: no session-ID storage discipline (the handle is refreshed in context by every tool response), no index-row maintenance (the index is derived), no branch handling (branches are invisible), and no list of forbidden tools (there are no file paths for the LLM to misuse — the Filesystem extension and cloud VM tools simply have no role in memory access).

### 5.4 Memory Write Triggers

The skill should write memory when these conditions are met:

| Trigger | What to write | Tool |
|---------|---------------|------|
| New project started | Project name, initial description, goals | `memory_write_block` (new `project-<name>`, summary required) + core update |
| Significant decision made | Decision, rationale, date | `memory_write_block` or `memory_append_block` on `decisions` or the project block |
| Project status change | New status, what changed | `memory_write_core` (summary) + `memory_write_block` (detail) |
| User shares key fact | The fact, context | `memory_write_core` (if high-level) or relevant block |
| Technical pattern discovered | The pattern, when to use it | `memory_write_block` on `reference-<topic>` |
| Conversation in progress (periodic) | Brief summary of what's happened so far | `memory_append_episodic` |
| Conversation ending | Conversation summary | `memory_append_episodic` |

### 5.5 Memory Read Triggers

| Trigger | What to read | Why |
|---------|--------------|-----|
| Conversation start (always) | Core, then the index | Establish identity and awareness of available context |
| User mentions a project | The project's block | Load detailed context for informed responses |
| User asks "what do you remember" | Relevant blocks based on the topic and index summaries | Provide comprehensive recall |
| User references a past decision | The `decisions` block or relevant project block | Provide accurate rationale |
| Planning future work | Relevant project blocks + `decisions` | Inform planning with historical context |
| `changed_since_last_read: true` received | Related blocks, if conclusions depended on them | Re-validate stale reasoning |

There is no full-text search over memory in v1. Retrieval is index-driven: the index summaries are the search surface, which is why the skill emphasizes writing summaries that support future load decisions. A dedicated `memory_search` tool is a future enhancement (see [Chapter 9, Section 9.1](stateful-agent-design-chapter9.md#91-fts5-search-index-option-3) and [Chapter 11, OQ#16](stateful-agent-design-chapter11.md)).

### 5.6 Reconciliation with Layer 1

Periodically (monthly, or when the user requests it), the primary agent should reconcile Layer 1 and Layer 2:

**Step 1:** Spawn a sub-agent with `allow_memory_read: true` to read all Layer 2 files and produce a structured digest:
```
spawn_agent(
  task: "Read all files in C:\franl\.claude-agent-memory\ and produce a structured 
         digest listing: active projects, completed projects, key facts,
         recent decisions, and any stale or contradictory content. Ignore
         .bridge-state.json, bridge-config.yaml, bridge.log, and any *.branch-* files.",
  allow_memory_read: true,
  model: "sonnet"  // Routine analysis task
)
```

(The sub-agent reads files directly — read-only, via its sandbox — so it sees the on-disk layout including frontmatter. That is fine: the memory-concepts abstraction exists for the *primary* agent's tool surface; a digest task is explicitly about inspecting the store. Branch files are excluded from the digest because their content is pending consolidation.)

**Step 2:** The primary agent (which has Layer 1 in context automatically) compares both layers and identifies:
- **Gaps:** Important Layer 2 facts that Layer 1 should summarize
- **Contradictions:** Layer 1 says a project is active, Layer 2 says it's completed
- **Stale entries:** Layer 1 references outdated information

**Step 3:** The primary agent applies fixes:
- **Layer 1 fixes:** Add steering edits via the `memory_user_edits` tool. These are incorporated by Anthropic's nightly regeneration (~24-hour lag).
- **Layer 2 fixes:** Update memory via `memory_write_core` / `memory_write_block` (immediate effect).
