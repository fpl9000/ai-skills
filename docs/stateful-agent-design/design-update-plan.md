# Stateful Agent Design — Update Plan

**Author:** Claude Opus 4.7 (with guidance from Fran)  
**Date:** May 2026  
**Status:** Working draft. Expected to evolve as open questions are resolved.

**Source materials:**  
- [memory-aware-tools-idea.md](stateful-agent-design/memory-aware-tools-idea.md) — transcript of the design discussion with Claude Sonnet 4.6
- [memory-aware-tools-analysis.md](memory-aware-tools-analysis.md) — review of that discussion
- [design-review.md](design-review.md) — critical design review by Claude Opus
- [stateful-agent-design.md](stateful-agent-design.md) and chapter files — the current design

---

## 1. Purpose and Scope

This plan captures everything decided so far about the memory-aware tools redesign, identifies what still needs to be resolved, and proposes an ordering for the design-document rewrite work. It is **not** the rewrite itself. The intent is to settle the remaining open questions here, then execute the rewrite in a fresh conversation working from this plan and the existing chapter files.

The scope of the rewrite is the memory subsystem only — the sub-agent system (`spawn_agent`, `run_command`, the async executor) is unaffected and stays as currently designed.

---

## 2. Decisions Ratified

These are settled by the discussion or by Fran's subsequent clarifications. They become firm requirements for the rewrite.

### 2.1 Tool surface

The bridge exposes memory-aware tools that operate on memory concepts, not files. Final signatures:

```
memory_start_conversation()
    → { handle: "<bridge-generated>" }

memory_get_core(handle)
    → { handle, content: "..." }

memory_write_core(handle, content)
    → { handle, ok: true }

memory_get_index(handle)
    → { handle, index: { blocks: [{ name, summary, updated_at }, ...] } }

memory_get_block(handle, name)
    → { handle, content: "..." }

memory_write_block(handle, name, content, summary?)
    → { handle, ok: true }

memory_append_block(handle, name, content)
    → { handle, ok: true }
```

Notes:

- The handle is returned in **every** tool response, not just from `memory_start_conversation`. This refreshes the handle in the LLM's context on every memory tool call, dramatically reducing the chance that compaction can lose it.
- There is no separate index-update tool. The `summary` parameter to `memory_write_block` carries any index changes, and the bridge applies them atomically with the block write.
- `memory_get_index()` returns the index as a structured object. The bridge owns the on-disk markdown format and any future schema migrations.

### 2.2 Branches are invisible to the LLM

The LLM never sees branch filenames, never participates in race detection, and is never told a branch exists. From its perspective, every read returns *the* current state of a block and every write succeeds.

### 2.3 Per-handle branch model

The bridge maintains an internal map: `handle H → block name B → branch file path`.

**Read behavior** for `memory_get_*` from handle H on block B:
- If the bridge's map has an entry for `(H, B)`, return the contents of that branch file.
- Otherwise, return the contents of the canonical (base) file.

**Write behavior** for `memory_write_*` from handle H on block B:
- If the bridge's map has an entry for `(H, B)`, write to that branch file. (No race detection needed; H already owns this branch.)
- Otherwise, compare current base ModTime against H's last-seen baseline for B:
  - If they match: write to the base file. (No race.)
  - If they differ: create a new branch file `B.branch-<H>-<timestamp>.<ext>`, record it in the map at `(H, B)`, and write to it.

This is the mechanism by which read-your-own-writes is preserved: once H writes to B and gets a branch, all subsequent operations from H on B go through that branch. Other conversations continue to see the base file. The LLM is unaware that any of this is happening.

### 2.4 No branches of branches

Once a branch exists for `(H, B)`, all future operations from H on B route through that branch. The branch itself is never branched. This keeps the branch storage model flat: at any moment, B has zero or more peer branches, each owned by exactly one handle.

### 2.5 Background merge during a wake-up phase (Option B)

Merges happen in the background, not during active conversations. The merge process:

- Selects all peer branches of a base block B, along with B itself.
- Performs the merge (mechanically for the index; via an LLM sub-agent for prose blocks).
- Atomically replaces the base file with the merged result.
- Deletes all branch files for B.
- Clears all map entries `(*, B)` so future reads from any handle see the merged base.

The wake-up phase mechanism (what schedules and runs this) is still **open** — see §3.1 below.

### 2.6 Merge holds a mutex that blocks memory I/O

While a merge is in progress, the bridge holds a lock that blocks all `memory_*` tool calls for the file being merged. This prevents new branches from being created during the merge and prevents reads from seeing partial merge state.

For v1 simplicity, the lock can be the existing process-wide mutex held for the duration of the merge. A finer-grained per-file lock is a future optimization. Because merges run during a wake-up phase (no active conversations expected), the impact of process-wide locking is small.

### 2.7 Graceful re-initialization on unknown handle

If the bridge receives a memory tool call with a handle it doesn't recognize (e.g., because the bridge restarted, or the handle was evicted, or the LLM fabricated one), it silently creates a new session under that handle (or, alternatively, generates a fresh handle and returns it — see §3.4) and proceeds normally. This converts a class of hard errors into a class of spurious branches, which the system already handles gracefully.

### 2.8 Index is always canonical, mechanically merged

The index does not branch. When a block write triggers a per-handle branch, the index entry is **still updated in place on the canonical index**, applying row-level mechanical merge rules:

- `updated_at` → latest wins.
- `summary` → latest wins (if the writer supplied one; otherwise unchanged).
- New rows → union.
- Deleted rows (not yet supported in v1, but for future): deletion-wins or latest-wins depending on policy.

This eliminates the design-review §1.2 concern that semantic merges don't work for structured tables. The index has no merge problem because the merge is mechanical and immediate.

### 2.9 Atomic block-plus-index update — ordering and recovery

The "atomic" claim is best-effort across two files with a documented recovery path. The ordering on a write to block B with optional summary S:

1. Determine target file (base or branch for handle H, per §2.3).
2. Write content to a temp file alongside the target (e.g., `B.md.tmp.<random>`).
3. `fsync` the temp file.
4. Atomic rename: temp → target file. **At this point, the block content is committed to disk under its canonical name.**
5. Read current index into memory, apply mechanical merge for B's row (update `updated_at`, optionally `summary`).
6. Write the updated index to its own temp file, fsync, atomic-rename onto the canonical `index.md`.

Crash recovery handled by a startup sweeper:

- Orphan temp files (`*.tmp.*`) are deleted at bridge startup.
- For each block, the sweeper compares the block file's ModTime against the index's `updated_at` for that block. If the block is newer, the sweeper rebuilds that index row (using the block's stored frontmatter summary, if present, or leaving the existing summary unchanged).
- Branch files with no corresponding entry in the handle→branch map (because they belong to a forgotten handle from a prior bridge instance) are flagged for merge during the next wake-up phase.

The window of inconsistency (block updated, index not yet updated) is short and recoverable. Readers calling `memory_get_index()` during this window may see a stale `updated_at` for B — acceptable for a metadata table.

### 2.10 Episodic logs handled separately (provisional)

The original design treats episodic logs (`episodic-YYYY-MM.md`) as a distinct file category from blocks, with monthly rotation. The discussion's tool table implicitly collapsed them under `memory_append_block`. The plan keeps them separate by default:

```
memory_append_episodic(handle, content)
    → { handle, ok: true }
```

The bridge handles month rotation internally based on system time. This avoids breaking the existing Chapter 4 episodic-log conventions and matches the "bridge owns file layout" principle of the redesign. (If on review this proves over-complicated, we can collapse it into `memory_append_block` with a documented naming convention.)

### 2.11 Append semantics: serialized, never branched

Appends are serialized by the bridge mutex. They never produce branches. The semantic justification: appends are commutative when the order isn't load-bearing, and for episodic logs (the primary use case) chronological ordering is already approximate. Race detection on appends would produce branches that need to be merged for no real benefit; serializing avoids the problem.

---

## 3. Open Questions Still to Resolve

These need answers before the rewrite. Listed roughly in order of consequence.

### 3.1 Wake-up phase mechanism

What schedules and runs the periodic merge process? Candidate approaches:

- **Windows Task Scheduler + `claude -p`.** A scheduled task invokes `claude -p` with a merge-orchestrator prompt that talks to the bridge over MCP (requires `claude -p` to be configured with the bridge MCP server) or directly to the bridge via a maintenance-mode CLI. Robust on Windows, but requires `claude -p` to be set up with MCP access to the bridge.
- **AutoHotkey driving Claude Chat.** AHK sends a prompt to the Claude Chat window during off-hours. Fragile (GUI automation), but works on the user's existing setup.
- **Lazy merge at session start.** When `memory_start_conversation` is called, the bridge synchronously merges any pending branches before returning. Pros: zero external scheduling, fully automatic. Cons: every conversation pays the merge cost at startup, including the LLM-merge token cost; the merge sub-agent must be invocable from inside the bridge's startup path.
- **Manual user trigger.** The user asks Claude (or the bridge directly) to "run merges now." Simple, no automation, but means merges accumulate until the user notices.
- **Hybrid: manual trigger now, automated later.** v1 ships with manual; an automated mechanism is added in v1.1 once one approach proves out.

**Recommendation for v1:** manual trigger plus a `memory_run_maintenance(handle)` tool the user can ask Claude to invoke. This sidesteps the unattended-execution problem entirely and lets us defer the AHK/Task Scheduler decision. The system is then correct (merges happen) and operable (the user controls when), just not fully automatic.

### 3.2 Should writes branch when other sessions have outstanding reads?

The existing design branches on read-modify-write races: X writes B against a stale baseline. The new question (Fran's note 2) is whether to *also* branch on a different scenario:

- X reads B at T₁ (sees content C₁).
- Y reads B at T₁ (sees C₁).
- Y writes B at T₂ (no race; Y's baseline matches base ModTime).
- X's context is compacted; C₁ rolls out.
- X re-reads B at T₃ and sees Y's content C₂.

If we treat Y's write as a branch-triggering event (because X has an outstanding read of B), then:
- Y writes to a branch instead of the base.
- X re-reads B and sees C₁ (consistent with X's previous read).
- The base is unchanged.

This is stricter conversation isolation, but the cost is significant: in a system with even modest concurrency, almost every write would branch (because at any moment some conversation somewhere probably has an outstanding read of any frequently-touched file like `core.md` or `index.md`). The merge load could explode.

**Trade-offs:**

| | Branch on RMW race only (current) | Branch also on read-then-write-by-another (proposed) |
|---|---|---|
| Reader sees other conversations' writes on re-read? | Yes (consistency = filesystem-style) | No (consistency = snapshot isolation) |
| Branch frequency | Low (only on actual race) | Potentially very high |
| Merge load | Low | High |
| LLM mental-model surprise on re-read | Possible | Eliminated |

**Recommendation:** Defer this to a v1.x decision. Ship v1 with branch-on-RMW-race-only and add an explicit caveat in the SKILL or design doc that re-reads of a block may show updates from other conversations. Monitor in practice whether the surprise is real or theoretical. If it becomes a problem, revisit.

An intermediate option: have `memory_get_*` return a flag `{ changed_since_last_read: true }` on a re-read that shows different content than the last read by this handle. The LLM can then choose to acknowledge the change. This is a low-cost mitigation that preserves the existing branching policy.

### 3.3 Handle as required parameter vs. optional with auto-init

When the LLM calls a memory tool without first calling `memory_start_conversation`, two behaviors are possible:

- **Required:** MCP validates the parameter; the call fails without a handle. The LLM must always call `memory_start_conversation` first. SKILL enforces this.
- **Optional with auto-init:** The handle parameter is optional. If absent, the bridge generates one, includes it in the response, and from then on the LLM uses it. `memory_start_conversation` becomes a courtesy, not a requirement.

**Recommendation:** **Required parameter.** The MCP schema-validation gives a clean enforcement mechanism that doesn't rely on SKILL prose. The auto-init path adds bridge complexity for marginal benefit, and the design has the graceful-re-init path (§2.7) as the safety net for any case where the LLM passes a stale or invalid handle. Calling `memory_start_conversation` once per conversation is a tiny compliance burden and the SKILL can frame it as "always start with this, like opening a file before reading."

### 3.4 Handle generation policy

Decisions needed:

- **Format and length:** 4 alphanumeric characters (per the discussion) is fine for the expected single-user concurrency. Spelling it out: lowercase alphanumeric, 4 chars, ~1.6M possibilities. Probably enough; cheap to make 6 or 8 chars if we want headroom.
- **Generation site:** The bridge generates the handle. The LLM never invents one. Even on the graceful re-init path, if the LLM supplies an unknown handle, the bridge can either honor it or substitute a fresh one. Honoring the LLM-supplied unknown handle is simpler but allows handle collisions (LLM A fabricates handle `h7k3`, currently in use by LLM B → their histories merge silently). **Recommendation:** when the bridge receives an unknown handle, it generates a fresh one and returns that in the response. The SKILL tells the LLM "always use the most recently returned handle."
- **Persistence:** The handle→state map is in memory. On bridge restart, all handles are invalidated; the next tool call from each conversation triggers graceful re-init. This is consistent with the design-review §3.1 concern; making it persistent across bridge restarts is a v1.x improvement.

### 3.5 `summary` parameter contract

For `memory_write_block(handle, name, content, summary?)`:

- **For new blocks** (no existing index entry): `summary` is required. The bridge rejects the call with a clear error if absent.
- **For existing blocks:** `summary` is optional. If absent, the existing index summary is preserved unchanged. If present (including empty string), it replaces the existing summary.
- **Length:** capped at, say, 200 characters. Truncated with a warning if exceeded.

### 3.6 Schema for `memory_get_index()`

Proposed:

```json
{
  "handle": "abc1",
  "index": {
    "schema_version": 1,
    "blocks": [
      { "name": "project-foo", "summary": "...", "updated_at": "2026-05-20T14:23:00Z" },
      ...
    ]
  }
}
```

Ordering: stable sort by `name`. (Insertion order would be subtle to maintain across bridge restarts; `updated_at` order would change every write, which is disruptive for the LLM's mental model.)

Pagination: not in v1. If the index grows past ~500 entries, we revisit.

### 3.7 Handle lifetime and cleanup

Open: when does a handle's state get cleaned up?

- **On bridge restart:** all in-memory state is lost. Branches on disk remain and are reaped by the wake-up phase.
- **On graceful Claude Desktop disconnect:** the bridge sees the stdio pipe close; it could clean up all handles at that point. But the discussion noted (line 153) that this only signals "Claude Desktop exited" — it can't tell which conversations were ongoing. Best behavior: at disconnect, mark all handles as orphaned; their branches will be merged during the next wake-up phase.
- **On idle timeout:** a handle that hasn't seen activity in N hours could be auto-evicted. Probably not worth the complexity in v1.

### 3.8 Where do branches store on disk?

Proposed naming convention: `<basename>.branch-<handle>-<ISO8601compact>.<ext>`. Example: `core.branch-h7k3-20260520T1423.md`.

This embeds the handle in the filename, which:

- Lets the bridge reconstruct the handle→branch map from disk on startup (for branches whose handles are still active).
- Makes orphaned branches (handle no longer active) visible by inspection.
- Replaces the random hex suffix from the old design with the handle itself, which is more meaningful.

The on-disk layout remains flat: branches sit alongside their base files in the same directory. The SKILL never references this layout; only the bridge does.

### 3.9 Behavior when `memory_run_maintenance` is invoked during an active conversation

If the user asks Claude to run maintenance while other conversations are active, what happens?

- The bridge enumerates pending merges (branches on disk).
- For each, acquire the merge mutex, perform the merge, release.
- Other conversations attempting memory I/O during a merge are blocked (per §2.6).

This works but means the user's "run maintenance now" command may block other conversations briefly. Acceptable for v1; document it.

---

## 4. Documentation Changes Required

### 4.1 Main file (`stateful-agent-design.md`)

- **§1.3 Design Principles:** Principle 4 (bridge-mediated memory access) needs rewriting around memory-aware tools and the handle model. Principle 5 (branching) needs rewriting around invisible per-handle branches and background merging.
- **§1.4 Terminology:** Replace "Session ID" with "Handle"; update bridge tool list; update "Branch (memory)" to reflect per-handle naming; update "Merge (memory)" to reflect mutex-protected background merges.
- **§2.1 Component diagram:** Replace `safe_read_file`/`safe_write_file`/`safe_append_file`/`memory_session_start` with the new memory_* tools listed in §2.1 of this plan.
- **§2.2 Data flow:** Rewrite the memory-read and memory-write subsections. Drop the branch-content-included-in-read flow. Add the per-handle branch routing.
- **§2.3 What the Bridge Does NOT Do:** Remove "Memory-aware tools — deferred" since they're now v1.

### 4.2 Chapter 3 (MCP Bridge Server)

Largest single change. The chapter needs substantial rewriting:

- Tool definitions (currently `safe_read_file`, `safe_write_file`, `safe_append_file`, `memory_session_start`) replaced by the seven memory_* tools.
- Session tracker (currently `session_id → file_path → last_seen_modtime`) replaced by handle map (`handle → block_name → branch_file_path`) plus per-handle read-baseline tracking for race detection.
- Race detection logic rewritten around the per-handle branch model (§2.3 of this plan).
- Branching mechanism rewritten: instead of "create a branch on race," the model is "if no branch exists for this handle+block, create one on race; otherwise reuse."
- Atomic block+index write logic specified (§2.9 of this plan).
- Merge mutex specified (§2.6 of this plan).
- New tool: `memory_run_maintenance(handle)` for manual merge trigger (if §3.1 lands on the manual-first approach).

### 4.3 Chapter 4 (Memory System Layer 2)

Moderate change. The file formats on disk are mostly unchanged:

- Branch file naming convention updated (now includes handle, per §3.8 of this plan).
- Maintenance rule about Claude updating `index.md` is **removed** — the bridge handles it.
- The episodic-log section stays as-is if §2.10 lands on "separate concept"; otherwise needs a substantive rewrite.

### 4.4 Chapter 5 (Memory Skill)

Largest simplification. The SKILL should be **much** shorter:

- No session ID instructions (handle is opaque infrastructure, never inspected).
- No branch instructions (branches don't exist as far as the LLM is concerned).
- No file paths (the bridge owns them).
- No race-recovery instructions.
- No `branches_exist` flag handling.
- New: clear instruction to call `memory_start_conversation` once per conversation and to use the most recently returned handle.
- New: optional guidance on the `summary` parameter for `memory_write_block`.
- Retained: when to read core vs. blocks vs. index; when to create a new block vs. update an existing one; how to structure block content.

### 4.5 Chapter 6 (Sub-Agent System)

Largely unaffected. Sub-agents don't write to memory (single-writer model preserved). Minor touch-ups only.

### 4.6 Chapter 7 (Deployment)

Unaffected.

### 4.7 Chapter 8 (Testing Strategy)

Moderate change. New test cases needed for:

- Handle round-trip across compaction simulation.
- Per-handle branch isolation (X's writes invisible to Y).
- Read-your-own-writes across multiple writes from the same handle.
- Mechanical index merge correctness.
- Atomic block+index ordering (crash simulation).
- Graceful re-init on unknown handle.
- Maintenance flow: branch creation, merge, base file replacement.

### 4.8 Chapter 9 (Future Enhancements)

§9.2 (memory-aware tools) was described as future work. It moves to v1, so the section either disappears or becomes a brief "this is now v1 — see Chapter 3" stub. Other §9 sections may need rewording to remove references to the old session/branching model.

### 4.9 Chapter 11 (Open Questions)

Several existing questions become moot (anything about session ID handling or branch surfacing). New questions from §3 of this plan (the ones we don't resolve before the rewrite) get added.

### 4.10 Chapter 12 (SDK Reference)

Unaffected.

---

## 5. Proposed Work Ordering

Suggested order for the rewrite conversation:

1. **Resolve all §3 open questions** (this plan) — landed in a follow-up version of this plan before the rewrite starts.
2. **Update Chapter 3** (Bridge Server) — most consequential changes; many downstream chapters reference it.
3. **Update Chapter 4** (Memory System) — file-format and branch-naming changes.
4. **Update Chapter 5** (SKILL) — simplification pass.
5. **Update the main design doc** (§1.3, §1.4, §2.1, §2.2, §2.3) — overview reflects the new architecture.
6. **Update Chapters 6–8 and 11** — touch-ups, test cases, open questions.
7. **Update Chapter 9** (Future Enhancements) — collapse §9.2.
8. **Final cross-reference pass** — verify all internal links and consistent terminology.

Each step lands as its own PR for review. This keeps any individual PR small enough to review thoroughly, and lets us catch issues early before they propagate through later chapters.

---

## 6. Working Notes (Iterative)

A scratchpad for decisions, course-corrections, or additional clarifications added as the plan evolves. Initially empty.
