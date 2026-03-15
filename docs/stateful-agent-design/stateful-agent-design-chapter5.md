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
