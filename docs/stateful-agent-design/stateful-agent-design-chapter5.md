# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Contents

- [5. Memory Skill](#5-memory-skill)
  - [5.1 Skill Packaging](#51-skill-packaging)
  - [5.2 SKILL.md Content](#52-skillmd-content)
  - [5.3 Session Lifecycle](#53-session-lifecycle)
  - [5.4 Memory Write Triggers](#54-memory-write-triggers)
  - [5.5 Memory Read Triggers](#55-memory-read-triggers)
  - [5.6 Reconciliation with Layer 1](#56-reconciliation-with-layer-1)

## 5. Memory Skill

### 5.1 Skill Packaging

The memory skill is a Claude Desktop skill packaged as a .zip file containing a single `SKILL.md` file. It does not contain scripts (all operations use existing MCP tools). The .zip is uploaded via Claude Desktop > Settings > Capabilities.

```
stateful-memory.zip
└── SKILL.md           # Instructions for Layer 2 memory lifecycle
```

**Why no scripts?** All memory read/write operations are performed via the bridge's MCP tools (`safe_read_file`, `safe_write_file`, `safe_append_file`), with `Filesystem:search_files` available as an interim search fallback (see [OQ#13](stateful-agent-design-chapter11.md)). No Python or shell scripts are needed. This eliminates dependency management and makes the skill trivially portable.

### 5.2 SKILL.md Content

The SKILL.md below is the complete skill instruction file. It is the primary artifact that controls Claude's memory behavior.

```markdown
# Stateful Agent Memory Skill

You have access to a persistent memory system stored as markdown files on the local
filesystem. This memory persists across conversations and gives you deep context
about the user, their projects, and your shared history.

## CRITICAL: Use the Correct Tools for Memory Operations

All memory file reads and writes MUST go through the bridge's memory tools. These
tools provide session tracking, race detection, and branching to prevent concurrent
conversations from overwriting each other's updates.

1. **Session initialization:** Call `Bridge:memory_session_start` once at the start
   of every conversation. This returns a `session_id` that you MUST pass to all
   subsequent memory tool calls. Store this ID and use it consistently.

2. **Reading memory files:** Use `Bridge:safe_read_file(path, session_id)`.
   This records the file version so the bridge can detect races on later writes.
   If branched versions of the file exist (from a prior concurrent write race),
   their content will be included in the response, annotated as branches.

3. **Writing memory files:** Use `Bridge:safe_write_file(path, content, session_id)`
   for full file replacement, or `Bridge:safe_append_file(path, text, session_id)`
   for appending (primarily for episodic logs). If the bridge detects that another
   conversation modified the file since you last read it, your write is automatically
   redirected to a branch file — no data is lost.

4. **Searching memory files:** Use `Filesystem:search_files` on the memory directory.
   The bridge does not yet have a dedicated search tool (planned for v1.1), so
   searching via the Filesystem extension is the accepted v1 workaround.
   **Important:** If a search result hits a `.branch-*` file (e.g.,
   `core.branch-20260313T1423-a1b2.md`), do NOT read the branch file directly.
   Instead, call `Bridge:safe_read_file` on the corresponding base file (e.g.,
   `core.md`), which will return both the base content and all branch content in
   a properly annotated structure.

NEVER use `Filesystem:read_file`, `Filesystem:write_file`, or `Filesystem:edit_file`
for memory files — those bypass session tracking, race detection, and branching.
`Filesystem:search_files` is the one exception, permitted only for search (not for
reading file content). After finding a file via search, always read it through
`Bridge:safe_read_file`.

NEVER use cloud VM tools (`bash_tool`, `create_file`, `str_replace`) for persistent data.
The cloud VM filesystem is ephemeral and resets between sessions.

Memory files live at `C:\franl\.claude-agent-memory\` — always access them via the
bridge memory tools listed above.

## Memory Directory

Location: C:\franl\.claude-agent-memory\

Structure:
- core.md — Your identity summary and active project list. Always load this first.
- index.md — Table mapping block filenames to summaries. Always load after core.md.
- blocks\ — Individual content files. Load on demand based on conversation topic.
- *.branch-*.* — Temporary branch files from concurrent write races (if any exist).

## Session Start Protocol

At the start of every conversation, BEFORE responding to the user's first message:

1. Call `Bridge:memory_session_start` to get a session_id. Store it for the session.
   If the response includes `branches_exist: true`, note this — you may want to
   trigger a merge later (or mention it to the user).
2. Read core.md via `Bridge:safe_read_file(path, session_id)`
3. Read index.md via `Bridge:safe_read_file(path, session_id)`
4. Scan the index for blocks relevant to the user's opening message
5. If a relevant block exists, read it via `Bridge:safe_read_file(path, session_id)`
6. Now respond to the user, informed by your loaded context

If core.md does not exist, this is a first-run scenario. Create the memory directory
structure and seed core.md with basic information from Layer 1 (your built-in memory)
and the current conversation.

## Handling Branches

If `safe_read_file` returns branches for a file (the `has_branches` field is true),
this means another conversation's changes were saved to a branch file during a
concurrent write race. The branch content represents changes that haven't been
merged yet.

When you encounter branches:
- Consider ALL versions (base + branches) when answering questions about the topic.
- The base file is the "main line" and branches contain divergent changes.
- You can offer to merge branches by spawning a sub-agent, or mention to the user
  that unmerged branches exist.
- Do NOT manually rewrite the base file to include branch content — use the merge
  process instead (spawn a sub-agent with merge instructions).

## During the Conversation

### When to Read Blocks
- When the conversation shifts to a topic listed in index.md that you haven't loaded
- When the user asks "what do you remember about X?" and X matches a block
- When you need project context to give an informed answer
- Always use `Bridge:safe_read_file(path, session_id)` — never `Filesystem:read_file`

### When to Search Memory
If you need to find content in memory but the index doesn't clearly identify which
block contains it (e.g., the user asks about a specific term or decision and the
index summaries are too terse to match):

1. Use `Filesystem:search_files` on the memory directory (`C:\franl\.claude-agent-memory\`)
2. Review the search results. If any hit is on a `.branch-*` file, note the
   corresponding base filename (e.g., `core.branch-20260313T1423-a1b2.md` → `core.md`)
3. Call `Bridge:safe_read_file(path, session_id)` on the base file — this returns
   both the base content and any branch content in a properly annotated structure
4. Never read a branch file directly via `Filesystem:read_file` — always go through
   `safe_read_file` on the base file

### When to Write Memory
Write memory updates incrementally as significant information emerges. Do NOT
accumulate changes and batch-write at session end — sessions can end abruptly.

**Write to core.md** (via `Bridge:safe_write_file(path, content, session_id)`) when:
- A new project starts or an existing project's status changes significantly
- Key facts about the user change (role, location, preferences)
- Keep core.md under ~1,000 tokens. Move detailed content to blocks.
- Provide the COMPLETE updated file content (safe_write_file does full replacement)

**Write to index.md** (via `Bridge:safe_write_file(path, content, session_id)`) when:
- You create a new block (add a row)
- A block's summary needs updating (edit the Summary column)
- A block's content changes (update the Updated column)
- Provide the COMPLETE updated file content

**Write to blocks** (via `Bridge:safe_write_file(path, content, session_id)`) when:
- Significant project decisions are made
- Technical details worth remembering emerge
- The user shares information that will be useful in future sessions
- Provide the COMPLETE updated file content

**Append to episodic log** (via `Bridge:safe_append_file(path, text, session_id)`) when:
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
  Read the file first via `Bridge:safe_read_file` if you don't already have its
  content in context. Always include your session_id in every tool call.
- If a write returns `branch_created: true`, this means the file was modified by
  another conversation since you last read it. Your changes were saved to a branch
  file. This is normal — the branch will be merged later.

## Session End

If the user says goodbye, thanks you, or the conversation is clearly winding down:

1. Persist any pending memory updates (core.md, index.md, relevant blocks)
2. Append an entry to the current month's episodic log summarizing the session
3. You do not need to announce that you're saving memory — just do it

## Handling User Questions About Memory

If the user asks "what do you remember about X?":
1. Check index.md for blocks related to X
2. If the index clearly identifies a relevant block, read it via
   `Bridge:safe_read_file(path, session_id)`
3. If the index doesn't clearly match (summaries are too terse), fall back to
   `Filesystem:search_files` on the memory directory to find which files mention X.
   If search hits a `.branch-*` file, read the corresponding base file via
   `safe_read_file` instead.
4. If any loaded blocks have branches, consider all versions
5. Combine with any Layer 1 (built-in) memory you have
6. Respond naturally, as if recalling from your own knowledge

If the user asks to correct or delete a memory:
1. Read the file via `Bridge:safe_read_file`, make the correction, and write via
   `Bridge:safe_write_file(path, content, session_id)`
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
├─ 3. Call Bridge:memory_session_start → receive session_id (store for session)
│     If branches_exist is true, note for potential merge
├─ 4. Read core.md (Bridge:safe_read_file with session_id, ~500–1,000 tokens)
├─ 5. Read index.md (Bridge:safe_read_file with session_id, ~300–800 tokens)
├─ 6. Evaluate user's first message against index entries
├─ 7. Read relevant blocks if any match (Bridge:safe_read_file, varies)
└─ 8. Respond to user's first message
│
Session Active
│
├─ On topic change → Check index, load relevant blocks (Bridge:safe_read_file)
├─ On significant information → Update relevant block or core.md (Bridge:safe_write_file)
├─ On new project/topic → Create new block + update index.md (Bridge:safe_write_file)
├─ On decision made → Update decisions.md or project block (Bridge:safe_write_file)
├─ Every 30–60 minutes → Append episodic log entry (Bridge:safe_append_file)
├─ On context pressure → Summarize verbose blocks to free tokens
├─ On branch_created response → Note that branching occurred (merge needed later)
└─ On branches_exist at session start → Optionally trigger merge via sub-agent
│     (All write/append calls include session_id)
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

