# Stateful Agent Design — Update Plan

**Author:** Claude Opus 4.7 (with guidance from Fran)  
**Date:** May 2026  
**Status:** Final version. Ready for updating the original design.

**History:**

The below source materials are essential to understanding this update plan. These files exist in the same directory as this document. It's best to read them in the order they were created, as described here:

1. Claude and Fran initially wrote `stateful-agent-design.md` (and its associated chapter files, `stateful-agent-design-chapter*.md`). **IMPORTANT:** Claude should not read every chapter file as it will waste valuable context window space. Claude should only read the chapters referenced by this update plan.
2. Fran asked Claude Opus 4.7 to do a critical review of the design. Opus wrote this detailed review: `design-review.md`.
3. Fran and Claude began discussing the review, and Fran realized that the root of many design issues was the lack of memory-aware tools and the burden placed on the LLM to track session IDs and detect race conditions. The critical part of this discussion was captured in `memory-aware-tools-idea.md`.
4. Fran and Claude then discussed the memory-aware tools idea, capturing their design decisions in `memory-aware-tools-analysis.md`.
5. Lastly, Fran asked Claude to document the planned changes to the original design, resulting in `design-update-plan.md` — this document.

**Source materials:**
1. [stateful-agent-design.md](./stateful-agent-design.md) and chapter files — the original design to be updated according to this plan
2. [design-review.md](./design-review.md) — critical design review by Claude Opus, now stale due to significant changes described in this plan
3. [memory-aware-tools-idea.md](../../docs/stateful-agent-design/memory-aware-tools-idea.md) — transcript of my memory-aware tools discussion with Claude Sonnet
4. [memory-aware-tools-analysis.md](./memory-aware-tools-analysis.md) — analysis of the memory-aware tools discussion, which led to creating this update plan

---

## 1. Purpose and Scope

This plan captures everything decided so far about the redesign of the memory access tools in the [Stateful Agent Design](stateful-agent-design.md), identifies what still needs to be resolved, and proposes an ordering for the design-document rewrite work. The intent is to settle the remaining open questions here, then execute the rewrite in a fresh conversation working from this plan and the existing design files.

The scope of the rewrite is the memory subsystem only — the sub-agent system (`spawn_agent`, `run_command`, the async executor) is unaffected and stays as currently designed.

This plan intentionally does not address every issue raised in the [Design Review](design-review.md). The significant design changes planned in this document have made the design review stale. A new design review will be performed before implementation begins.

---

## 2. Decisions Ratified

These are settled by the discussion or by Fran's subsequent clarifications. They become firm requirements for the rewrite.

### 2.1 Tool surface

The bridge exposes memory-aware tools that operate on memory concepts, not files. Final signatures:

```
memory_start_conversation()
    → { handle: "<bridge-generated>" }

memory_get_core(handle)
    → { handle, content: "...", changed_since_last_read: bool }

memory_write_core(handle, content)
    → { handle, ok: true }

memory_get_index(handle)
    → { handle, index: { blocks: [{ name, summary, updated_at }, ...] } }

memory_get_block(handle, block_name)
    → { handle, content: "...", changed_since_last_read: bool }

memory_write_block(handle, block_name, content, summary?)
    → { handle, ok: true }

memory_append_block(handle, block_name, content)
    → { handle, ok: true }

memory_run_maintenance(handle)
    → { handle, ok: true, merged_blocks: N, errors?: [...] }
```

**Notes:**

- The handle is returned in **every** tool response, not just from the initial call to `memory_start_conversation`, which allocates the handle. This refreshes the handle in the LLM's context on every memory tool call, dramatically reducing the chance that compaction can lose it.
- There is no separate index-update tool. The `summary` parameter to `memory_write_block` is stored in the block file's YAML frontmatter (see §2.8). The bridge writes the body and frontmatter together as one file, so no cross-file coordination is needed.
- `memory_get_index()` returns a structured object assembled by the bridge from the blocks directory. It is a derived view, not a stored file (see §2.8).
- `memory_run_maintenance()` is invoked manually by the LLM when the user asks for memory maintenance. It dispatches sub-agents to semantically merge branched memory blocks (see §2.5, §3.1).

### 2.2 Branches are invisible to the LLM

The LLM never sees branch filenames, never participates in race detection, and is never told a branch exists. From its perspective, every read returns *the* current state of a block and every write succeeds, even if the bridge chooses to read/write from a branch file instead of the base file.

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

### 2.5 Merge process (triggered by `memory_run_maintenance`)

The merge is the action that folds peer branches of a block back into a single canonical base. It is triggered when the user asks Claude to run memory maintenance (per §3.1), which causes the LLM to call `memory_run_maintenance(handle)`. The bridge then enumerates all blocks with pending branches and, for each, runs the following process:

- Selects all peer branches of a base block B, along with B itself.
- Acquires the merge mutex (per §2.6), blocking all other memory I/O for the duration of this block's merge.
- Performs the merge via an LLM sub-agent. The body of the merged block is produced semantically; the merged file's frontmatter (`summary`, `updated_at`) is regenerated — the new `summary` typically derived by the sub-agent from the merged body, the `updated_at` set to the merge time.
- Atomically replaces the base file with the merged result.
- Deletes all branch files for B.
- Clears all map entries `(*, B)` so future reads from any handle see the merged base.
- Releases the mutex.

The merge work itself runs in sub-agents (separate LLM invocations spawned by the bridge), not in the calling conversation's main reasoning context. In that sense the merge is "in the background" — the calling LLM doesn't have to reason about the merge content. But the maintenance call is synchronous: it returns to the calling LLM only after all merges complete.

### 2.6 Merge holds a mutex that blocks memory I/O

While a merge is in progress, the bridge holds a lock that blocks all `memory_*` tool calls for the file being merged. This prevents new branches from being created during the merge and prevents reads from seeing partial merge state.

For v1 simplicity, the lock can be the existing process-wide mutex held for the duration of the merge. A finer-grained per-file lock is a future optimization. Because merges only run when the user invokes `memory_run_maintenance` (per §3.1), and typically at a time the user chooses for that purpose, the impact of process-wide locking is small in practice.

### 2.7 Error on unknown or malformed handle (persisted state first, lazy adoption as backstop)

After a bridge restart, the bridge loads its persisted state (§2.12) at startup, so in the normal case a handle from a prior Claude Desktop session is **already recognized** — it's in the loaded in-memory map, along with its branch map and read baselines. The unknown-handle path described here is therefore the exception, not the rule, once persistence is in place.

**The procedure when the bridge does receive a handle it doesn't recognize:**

1. If the handle is malformed (wrong length, wrong character set), return `MALFORMED_HANDLE` immediately — no adoption attempt.
2. If the handle is well-formed but not in the in-memory map (i.e., not recovered from the persisted state either), scan the blocks directory for branch files matching `*.branch-<handle>-*.<ext>` (lazy adoption, the §3.11 backstop).
3. If any branch files are found, reconstruct the corresponding `(handle, block_name) → branch_file_path` entries in the map, treat the handle as live, and proceed with the original tool call. Read baselines for this handle cannot be reconstructed by lazy adoption (they live only in the persisted state, which by hypothesis didn't contain this handle), so the first read for any block by the recovered handle sets a fresh baseline and the `changed_since_last_read` flag is `false` on those first reads.
4. If no branch files match, return `INVALID_HANDLE`. The SKILL teaches the LLM to call `memory_start_conversation` to obtain a fresh handle and retry.

The error response carries a clear textual description (see §3.10 for the error-response convention). The recovery procedure, taught by the SKILL, is uniform across all handle error cases: call `memory_start_conversation` to obtain a fresh handle, then retry the original operation with the new handle.

**Cases that produce a handle error after the procedure above:**
- Handle parameter omitted entirely → MCP schema-validation error before the call reaches the bridge.
- Handle malformed → bridge returns `MALFORMED_HANDLE`.
- Handle well-formed but absent from the persisted state, the in-memory map, and every branch filename on disk → bridge returns `INVALID_HANDLE`. Common causes: the LLM fabricated the handle; the handle was evicted by the §3.7 cleanup policy (which only evicts handles with no branches); a brand-new conversation passed a handle without first calling `memory_start_conversation`.

**Cases that do not produce a handle error:**
- The bridge restarts and a conversation resumes with its prior handle → the handle is recovered from the persisted state (§2.12), with full branch map and read baselines. Transparent; no degradation.
- The persisted state is missing or corrupt, but the conversation had created at least one branch → lazy adoption recovers the branch map (but not baselines), and the call proceeds. Degraded but functional.

**Important corner case:** A resumed conversation whose handle is absent from the persisted state (e.g., the state file was lost) *and* that never created a branch will get `INVALID_HANDLE` — there's nothing on disk to discover. It recovers cleanly via `memory_start_conversation` with no data lost (base writes are visible to anyone reading the base).

This section evolved across several decisions: silent re-init (original) → explicit error, no re-init (§3.3) → lazy adoption from branch filenames (§3.11) → persisted-state-first with lazy adoption as backstop (§2.12). The current behavior gives predictable bridge semantics, no handle-collision risk, and a fully transparent close-reopen experience in the normal case.

### 2.8 Index is a derived view, not a stored file

The original draft of §2.8 said "the index doesn't branch and is mechanically merged in place on every write." Fran pointed out the problem with that: applied to a single write, "latest wins" reduces to "always replace," so writes to a block's summary from conversation Y would land directly in the canonical index and be visible to conversation X — leaking semantic information across conversation boundaries. The mechanical merge rules in the original §2.8 only do non-trivial work when multiple peer branches fold back into one canonical state, but the original §2.8 said no peer branches of the index ever exist. So the merge rules never fired and the leakage was real.

The resolution: **the index is not stored as a separate file at all.** Each block's `summary` and `updated_at` live in YAML frontmatter inside the block file itself. The bridge manages frontmatter transparently — the LLM never sees it. `memory_get_block` strips the frontmatter and returns only the body; `memory_write_block` accepts the body and an optional `summary`, and writes a file containing the appropriate frontmatter and the body.

`memory_get_index(handle)` is implemented as a walk of the blocks directory:

1. Enumerate block files.
2. For each block name B, choose which file to read: H's branch of B if one exists in the bridge's handle→branch map, else the base file.
3. Extract `summary` and `updated_at` from the chosen file's frontmatter.
4. Return the assembled index.

This eliminates the leakage problem by construction. H's index view is built from the files H can see, which are H's branches and the bases of blocks H hasn't branched — exactly what H's per-block view returns. The index and the blocks are guaranteed consistent because they come from the same files.

Block file format on disk:

```yaml
---
summary: "Discussion of the X feature design"
updated_at: 2026-05-20T14:23:00Z
---
# Markdown body of the block goes here
...
```

The user can still inspect block metadata by looking at the top of any block file. A human-readable `index.md` no longer exists as part of normal operation; if one is wanted for debugging, a `memory_dump_index(handle, path)` tool could be added later that writes a snapshot of the current derived index to a user-named file outside the memory directory.

**Performance:** `memory_get_index` is O(n_blocks) in the worst case. The bridge maintains an in-memory cache keyed by the blocks directory's most recent mtime; the walk runs only when the cache is stale. For per-handle views, the cache holds one assembled index per handle, invalidated when that handle writes a block or when the base changes. Steady-state cost is one cached lookup.

**Schema evolution:** YAML frontmatter is naturally extensible. Adding fields (e.g., `importance` per design §9.7) is backwards-compatible. Removing or renaming fields requires a migration sweep at bridge startup.

### 2.9 Atomic block write — ordering and recovery

With the index folded into block files (per §2.8), the "atomic block-plus-index write" problem reduces to "atomic single-file write," which is solvable with the standard temp-and-rename approach:

1. Determine target file (base or branch for handle H, per §2.3).
2. Compose the file content: frontmatter (with `updated_at` set to now, and `summary` set to the provided value or the previous summary preserved) plus the body.
3. Write the composed content to a temp file alongside the target (e.g., `<name>.md.tmp.<random>`).
4. `fsync` the temp file.
5. Atomic rename: temp → target file.

There is no second file to keep in sync. The frontmatter and body are written together as one operation, so they can never be out of sync.

Crash recovery handled by a startup sweeper:

- Orphan temp files (`*.tmp.*`) older than a few seconds are deleted at bridge startup.
- Branch files with no entry in the handle→branch map (because they belong to a handle from a prior bridge instance) are flagged for merge during the next `memory_run_maintenance` call. The handle is forgotten but the data is preserved.
- Block files missing required frontmatter (e.g., user-edited without preserving it) get a default frontmatter inserted on the next read or scheduled write — the bridge does not silently lose the data but does not refuse to read it.

This is materially simpler than the original §2.9, which had to coordinate two file writes. The simpler invariant is easier to verify and easier to recover from.

### 2.10 Episodic logs handled separately (provisional)

The original design treats episodic logs (`episodic-YYYY-MM.md`) as a distinct file category from blocks, with monthly rotation. The discussion's tool table implicitly collapsed them under `memory_append_block`. The plan keeps them separate by default:

```
memory_append_episodic(handle, content)
    → { handle, ok: true }
```

The bridge handles month rotation internally based on system time. This avoids breaking the existing Chapter 4 episodic-log conventions and matches the "bridge owns file layout" principle of the redesign. (If on review this proves over-complicated, we can collapse it into `memory_append_block` with a documented naming convention.)

### 2.11 Append semantics: serialized, never branched

Appends are serialized by the bridge mutex. They never produce branches. The semantic justification: appends are commutative when the order isn't load-bearing, and for episodic logs (the primary use case) chronological ordering is already approximate. Race detection on appends would produce branches that need to be merged for no real benefit; serializing avoids the problem.

### 2.12 Bridge state is persisted across restarts

The bridge persists its in-memory state to disk and reloads it at startup. This supersedes the earlier "in-memory only" decision from §3.4. The motivation: the bridge is spawned by Claude Desktop over stdio and terminates whenever Claude Desktop closes (§3.11). Without persistence, every close-reopen cycle discards all bridge state, and recovery depends entirely on the lazy-adoption mechanism — which cannot recover read baselines and therefore degrades race detection and the `changed_since_last_read` flag after every restart. Persisting the state eliminates that degradation.

**What is persisted.** The bridge state file captures the three pieces of per-conversation state the bridge tracks:

1. The set of live handles.
2. The per-handle branch map (`handle → block name → branch file path`).
3. The per-handle read baselines (`handle → block name → content signature`, used for race detection per §2.3 and the `changed_since_last_read` flag per §3.2).

**Storage location and format.** A single JSON file in the memory root, named `.bridge-state.json` (leading dot so it sorts away from memory content and is visually distinct from blocks). It is bridge-private — neither the LLM nor the SKILL ever references it.

**Write strategy.** The bridge writes the state file:
- On clean shutdown, when it detects EOF on stdin (the normal Claude Desktop close path). This is the common case and captures the most recent state.
- Periodically as a checkpoint (e.g., every N seconds of activity, or after M state-changing operations), to survive a hard crash where the clean-shutdown write never happens.

All writes use the temp-file-plus-atomic-rename pattern (consistent with §2.9) so a crash mid-write cannot corrupt the file.

**Load and reconcile at startup.** On startup the bridge:
1. Loads `.bridge-state.json` if present.
2. Reconciles the loaded state against the filesystem: for each persisted branch-map entry, verify the referenced branch file still exists; drop entries whose files are gone (e.g., merged away by a maintenance run from a different bridge instance, though in a single-bridge deployment this is rare).
3. Runs lazy adoption (§3.11) as a backstop: scans the blocks directory for branch files not represented in the loaded state and rebuilds map entries for them. This covers the cases where the state file is stale (a branch was created after the last checkpoint), missing, or corrupt.

The relationship between persistence and lazy adoption: **persistence is the primary recovery mechanism; lazy adoption is the reconciliation backstop.** With both in place, the bridge recovers full state (including read baselines) in the normal case, and degrades gracefully to branch-map-only recovery (losing just read baselines) if the state file is unavailable.

**Corruption handling.** If `.bridge-state.json` is present but unparseable, the bridge logs the problem to its server-side log, discards the corrupt file, and falls back to pure lazy adoption — exactly the behavior the design had before persistence was added. The system is therefore never worse off than the lazy-adoption-only design, even in the corruption case.

A few finer points (write cadence specifics, whether to persist incrementally vs. whole-file each time, and the cleanup of stale handles to bound file growth) are detailed in §3.7.

---

## 3. Open Questions (All Resolved)

All eleven items below have been resolved. They are retained with their full reasoning (and ✅ RESOLVED markers) as the decision record for the rewrite. Listed roughly in the order they were originally raised.

### 3.1 Wake-up phase mechanism ✅ RESOLVED

**Decision:** For v1, merges are triggered manually via the bridge tool `memory_run_maintenance(handle)`. The SKILL teaches the LLM to call this tool when the user asks (in any phrasing) to run memory maintenance, merge branches, consolidate memory, etc. The bridge enumerates all pending branches and dispatches an LLM sub-agent to perform the semantic merge for each block. The maintenance call holds the merge mutex per §2.6 and blocks until all merges complete.

Automated triggers (Windows Task Scheduler + `claude -p`, AutoHotkey driving Claude Chat, lazy merge at session start) are deferred to v1.x. The manual approach is correct (merges happen when asked) and operable (the user controls timing). It sidesteps the unattended-execution problem entirely and lets us defer the AHK/Task Scheduler decision until we see how the system performs in practice. If branches accumulate uncomfortably, the SKILL can be updated to have the LLM suggest running maintenance — but that's a soft mitigation, not a v1 requirement.

**Tool surface change (§2.1):** Add `memory_run_maintenance(handle)` to the seven existing tools. Initial signature:

```
memory_run_maintenance(handle)
    → { handle, ok: true, merged_blocks: N, errors?: [...] }
```

**SKILL change (§4.4):** The SKILL teaches the LLM that:
- The tool exists and what it does at a conceptual level (merges branched memory back together).
- It should be called when the user explicitly asks for memory maintenance, merging, or consolidation.
- The call may take a noticeable amount of time, during which other memory operations from any conversation will block. This is acceptable because the user has asked for it.

**Deferred to the rewrite:**
- Exact return shape (do we list merged block names? include per-block error details? include count of branches found vs. successfully merged?).
- Whether to support partial maintenance (`memory_run_maintenance(handle, block_name?)`) for merging a single block, or always merge everything pending. Default: merge everything. Partial maintenance is a v1.x option if it proves useful.
- Behavior when called with no pending branches. Default: return `{ ok: true, merged_blocks: 0 }` immediately.
- **MCP tool-call timeout handling.** A synchronous `memory_run_maintenance` call could exceed the MCP tool-call timeout if many branches accumulate (e.g., 10 blocks × ~30s per sub-agent merge = 5 minutes). Three approaches to consider in the rewrite: (a) cap the call at N blocks per invocation and return `{ more_pending: true }` if more remain, letting the LLM call again; (b) plug into the existing async sub-agent infrastructure (Chapter 6) — `memory_run_maintenance` returns an agent ID and the LLM polls; (c) keep it fully synchronous and accept that very large merge batches require the user to wait or split their request. Recommendation is (a) for v1: easy to implement, easy for the LLM to handle, no async-polling complexity. The cap should be tunable.

### 3.2 Should writes branch when other sessions have outstanding reads? ✅ RESOLVED

The existing design branches on read-modify-write races: X writes B against a stale baseline. The new question (Fran's note 2) was whether to *also* branch on a different scenario:

- X reads B at T₁ (sees content C₁).
- Y reads B at T₁ (sees C₁).
- Y writes B at T₂ (no race; Y's baseline matches base ModTime).
- X's context is compacted; C₁ rolls out.
- X re-reads B at T₃ and sees Y's content C₂.

If we treated Y's write as a branch-triggering event (because X has an outstanding read of B):
- Y writes to a branch instead of the base.
- X re-reads B and sees C₁ (consistent with X's previous read).
- The base is unchanged.

This is stricter conversation isolation, but the cost is significant: in a system with even modest concurrency, almost every write would branch (because at any moment some conversation somewhere probably has an outstanding read of any frequently-touched file like `core.md` or a hot block). The merge load could explode.

**Trade-offs considered:**

| | Branch on RMW race only (v1) | Branch also on read-then-write-by-another (deferred) |
|---|---|---|
| Reader sees other conversations' writes on re-read? | Yes (consistency = filesystem-style) | No (consistency = snapshot isolation) |
| Branch frequency | Low (only on actual race) | Potentially very high |
| Merge load | Low | High |
| LLM mental-model surprise on re-read | Possible | Eliminated |

**Decision:** Ship v1 with **branch-on-RMW-race-only** semantics. Defer the stricter snapshot-isolation behavior until we have practical experience with how often the surprise actually occurs in real use. The merge-load risk of the stricter approach is concrete; the surprise it would prevent is hypothetical until observed.

**Mitigation included in v1:** `memory_get_core` and `memory_get_block` return a `changed_since_last_read: true` flag when the content returned to this handle differs from the content this handle most recently read for the same target. Implementation: the bridge tracks, per handle, the hash (or just the ModTime + size) of the most recent content returned for each block name. On the next read for the same target, if the new content's signature differs, the flag is set.

The flag lets the LLM notice that another conversation has modified shared memory and react appropriately (e.g., re-read related blocks, mention it to the user if relevant, or re-derive any conclusions that depended on the prior content). Importantly, the LLM is **not** told *what* changed or *who* changed it — just that the content is different from what it last saw. This preserves the per-conversation isolation principle (X can't introspect Y's activity) while still letting X know its prior view is stale.

**Response shape (updates §2.1):**

```
memory_get_core(handle)
    → { handle, content: "...", changed_since_last_read: bool }

memory_get_block(handle, name)
    → { handle, content: "...", changed_since_last_read: bool }
```

The flag is `false` on the first read of a target by this handle, on subsequent reads where the content is unchanged, and on any read that returns a per-handle branch (because the branch was last written by this handle, so "what this handle last saw" matches by construction). The flag is `true` only when this handle previously read this target and the content has since changed without this handle writing it.

**Re-visit criteria:** If user feedback or observation indicates that the surprise from `changed_since_last_read` is too disruptive — for example, the LLM frequently gets confused on re-reads despite the flag, or important information gets overwritten across conversations in ways the merge can't recover — revisit the stricter-isolation option. Until then, the v1 behavior is the default.

**SKILL change (§4.4):** The SKILL teaches the LLM that re-reading core or a block may yield different content than was previously seen, signaled by `changed_since_last_read: true`. When that flag is set, the LLM should treat any earlier reasoning that depended on the previous content as potentially stale.

### 3.3 Handle as required parameter vs. optional with auto-init ✅ RESOLVED

**Decision:** Handle is a **required parameter**. The MCP schema declares it as required, so omitting it produces a schema-validation error before the call reaches the bridge.

The bridge additionally rejects with an error any of:
- Handle parameter present but malformed (wrong length, wrong character set, etc.).
- Handle parameter present and well-formed but not recognized by the bridge (e.g., the bridge restarted and lost its in-memory handle map, or the LLM fabricated a handle).

In all error cases, the bridge returns a clear error message (see §3.10 for the error-response convention) instructing the LLM to call `memory_start_conversation` to obtain a fresh handle. There is **no graceful re-init** in the bridge — the LLM is responsible for recovering by calling `memory_start_conversation`. This keeps the bridge simple and the error semantics predictable.

**Failure modes and recovery:**

| Scenario | What happens |
|---|---|
| Handle omitted from tool call | MCP schema validation rejects; LLM calls `memory_start_conversation`, retries |
| Handle malformed | Bridge returns `MALFORMED_HANDLE`; LLM recovers same way |
| Handle valid; bridge restarted between calls; conversation had created branches | Bridge adopts branches from disk on first memory call (per §3.11); no error; handle is treated as live |
| Handle valid; bridge restarted between calls; conversation had not created branches | Bridge returns `INVALID_HANDLE`; LLM recovers via `memory_start_conversation`. No data lost (no branches existed) |
| Compaction wipes recent responses but LLM remembers older handle still in the bridge's map | No error; handle is still valid |
| Compaction wipes all memory responses including the original `memory_start_conversation` | LLM has no handle; calls `memory_start_conversation` again on its next memory operation; gets a fresh handle |
| LLM fabricates a handle | Bridge doesn't find it in the map; scans disk and finds no branches matching that handle; returns `INVALID_HANDLE`; LLM recovers same way |

This eliminates handle-collision risk (the bridge controls handle generation entirely; LLMs can't accidentally land on each other's handles), simplifies the bridge (no auto-init code path), and gives the LLM a single, predictable recovery procedure for any handle problem.

**Knock-on changes:**
- §2.7 rewritten to specify error-and-recover behavior, refined further by §3.11's lazy-adoption mechanism.
- The "bridge restart loses handle state" failure mode is mostly mitigated by §3.11's lazy adoption; only conversations that never branched still need to recover via `memory_start_conversation`.

**SKILL change (§4.4):** The SKILL teaches the LLM to call `memory_start_conversation` once at the start of any conversation that will use memory, and to call it again as a recovery step whenever any memory tool returns an unknown-handle or invalid-handle error. The recovery instruction is simple and uniform: "if you get a handle error, get a new handle and retry."

### 3.4 Handle generation policy ✅ RESOLVED

**Format and length.** Handles are **8 lowercase alphanumeric characters** (alphabet `[a-z0-9]`, 8 positions, ~2.8 × 10¹² possibilities). The expansion from 4 to 8 chars costs a few tokens per response and makes handle collisions astronomically unlikely even across bridge restarts and long-lived conversations.

**Generation site.** The bridge mints handles. The LLM never invents one. Following §3.3, an LLM-supplied unrecognized handle produces an `INVALID_HANDLE` error rather than being honored or substituted.

**Collision check.** Before returning a newly minted handle from `memory_start_conversation`, the bridge looks the candidate up in its in-memory handle→state map. If the candidate is already in use (vanishingly unlikely but cheap to verify), the bridge generates another candidate and re-checks. This makes in-flight collision impossible by construction.

**Randomness source.** v1 uses a standard PRNG (`math/rand` in Go, seeded at bridge startup). The probability of meaningful collisions with PRNG output at this handle length is negligible for the expected workload, and an unprivileged LLM has no way to predict or attack handle values through the MCP interface. **Future improvement:** upgrade to a CSPRNG (`crypto/rand`) when the threat model grows to include adversarial scenarios — e.g., if memory ever becomes accessible to untrusted parties, or if handle prediction could enable a meaningful attack. Noted here so it isn't forgotten.

**Persistence.** The handle→state map **is persisted across bridge restarts** (per §2.12). This reverses the earlier draft of this bullet, which specified in-memory-only state. The change was made after recognizing that the bridge terminates on every Claude Desktop close (§3.11), so in-memory-only state would be discarded routinely rather than rarely. With persistence, a handle issued in one Claude Desktop session is still valid in the next, and read baselines survive the restart. See §2.12 for the persistence mechanism and §3.7 for the handle-lifetime and cleanup policy that bounds the persisted file's growth.

**Open follow-up resolved in §3.11 and superseded by §2.12:** Closing Claude Desktop terminates the bridge. The originally-planned recovery was the lazy-adoption mechanism in §3.11. With the §2.12 persistence decision, persistence is now the primary recovery mechanism and lazy adoption is the reconciliation backstop.

### 3.5 `summary` parameter contract ✅ RESOLVED

Confirmed as drafted; no changes requested.

For `memory_write_block(handle, name, content, summary?)`:

- **For new blocks** (no existing block file with that name visible to this handle): `summary` is required. The bridge rejects the call with a clear error if absent.
- **For existing blocks:** `summary` is optional. If absent, the existing summary in the block's frontmatter is preserved unchanged. If present (including empty string), it replaces the existing frontmatter summary.
- **Length:** capped at, say, 200 characters. Truncated with a warning if exceeded.

### 3.6 Schema for `memory_get_index()` ✅ RESOLVED

Confirmed as drafted, with the handle example updated to the 8-character form per §3.4.

```json
{
  "handle": "abc1def2",
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

### 3.7 Handle lifetime and cleanup ✅ RESOLVED

With persistence (§2.12), handles now live across bridge restarts, so the question shifts from "how do we recover after a restart" (answered by §2.12) to "how do we keep the persisted state file from growing without bound." Each handle's persisted footprint is small (an 8-char handle, plus a branch map and a set of read-baseline signatures), but over months of daily use the count of handles grows steadily, and most of them belong to conversations the user will never return to.

**When a handle's state can be cleaned up:**

A handle is eligible for eviction when **both** of the following hold:
1. It owns no branches (all its branches have been merged away by `memory_run_maintenance`, or it never created any). A handle with live branches must never be evicted, because evicting it would orphan its branch files and lose the read-your-own-writes guarantee for that conversation.
2. It has been inactive for longer than a retention window (default: 60 days since its last memory tool call). Read baselines for a handle that hasn't been used in two months are very unlikely to ever be consulted again, because the conversation that owned the handle is almost certainly finished.

**When cleanup runs:**

Cleanup is folded into `memory_run_maintenance` (the existing manual-trigger flow from §3.1). After the maintenance pass merges branches, it sweeps the handle table and evicts every handle meeting both eligibility criteria. This keeps cleanup on the same user-controlled cadence as merging — no separate timer, no background thread.

The bridge also opportunistically drops a handle's read baselines for blocks that no longer exist (e.g., a block the baseline references was deleted), since those baselines can never be meaningfully compared again. This is cheap bookkeeping done during the same sweep.

**What eviction does:** removes the handle's entry from the in-memory map and from the next persisted write of `.bridge-state.json`. If an evicted handle is later presented again (e.g., a very old conversation the user returns to after 60+ days), it is treated as unknown: the bridge attempts lazy adoption (finds no branches, since eviction required zero branches), then returns `INVALID_HANDLE`, and the LLM recovers via `memory_start_conversation`. No data is lost because an evicted handle had no branches by definition.

**Write cadence for `.bridge-state.json` (resolving the detail deferred from §2.12):**

- Write on clean shutdown (stdin EOF).
- Checkpoint during operation after a state-changing operation, debounced so that a burst of writes doesn't cause a burst of disk I/O (proposed: coalesce changes and flush at most once every few seconds, plus an immediate flush after branch creation since that is the most important state to not lose).
- Whole-file rewrite each time (via temp + atomic rename). Incremental/append-based persistence is a v1.x optimization; for the expected state size (a few hundred handles at most, each small) a whole-file JSON rewrite is well under a millisecond and not worth optimizing.

**Retention window is configurable.** The 60-day default is a starting point. A user who runs many concurrent conversations might want it shorter; a user who returns to old conversations might want it longer. Exposed as a bridge configuration value, not hard-coded.

**Deferred to v1.x:**
- A hard cap on handle count (evict least-recently-used beyond the cap) as a backstop if the retention window alone proves insufficient. Not expected to be needed for single-user workloads.
- Incremental persistence (append-only change log + periodic compaction) if whole-file rewrites ever become a bottleneck.

### 3.8 Where do branches store on disk? ✅ RESOLVED

Naming convention: `<basename>.branch-<handle>-<ISO8601compact-UTC>.<ext>`. Example: `core.branch-h7k3xy90-20260520T142300Z.md`.

This embeds the handle in the filename, which:

- Lets the bridge reconstruct the handle→branch map from disk via lazy adoption (§3.11), serving as the reconciliation backstop to the persisted state file (§2.12).
- Makes branches visible and attributable by inspection (the handle in the name identifies the owning conversation).
- Replaces the random hex suffix from the old design with the handle itself, which is more meaningful.

The on-disk layout remains flat: branches sit alongside their base files in the same directory. The SKILL never references this layout; only the bridge does.

**The embedded timestamp — what it means and how it behaves:**

- **It is the branch's creation time** — the moment the bridge wrote the branch file in response to the first branching write for that (handle, block) pair (per §2.3, a write against a stale baseline when no branch yet exists for that pair).
- **It is frozen at creation and never updated.** Per §2.4 (no branches of branches), all subsequent writes by the same handle go to the same branch file, updating its *contents* but not its *filename*. The embedded timestamp therefore reflects "when this conversation first diverged from the base," not "when the branch was last modified." Last-modified time is available from the filesystem's own mtime if needed. Creation-time-in-the-name plus mtime-for-recency is a deliberate split: it means the bridge never has to rename a branch file (renaming on every write would add complexity and could race with lazy adoption mid-rename).
- **It is purely informational / for human debugging.** The bridge never parses or compares it. Lazy adoption matches branches by handle (globbing `*.branch-<handle>-*.<ext>`); uniqueness is already guaranteed by the (handle, block) pair plus the block basename. The timestamp is not a lookup key or a uniqueness key — just a human-readable annotation of when the fork happened.

**Timestamp format — compact UTC with seconds and a `Z` suffix:**

- **Compact (basic) ISO 8601**, not extended: no hyphens between date parts, no colons between time parts, but the literal `T` separator retained. Two reasons: colons are illegal in Windows filenames (`:` is the drive-letter separator), and the extended form's internal hyphens would collide visually and programmatically with the hyphens this filename uses to separate its own fields (`branch` - `<handle>` - `<timestamp>`).
- **UTC with a trailing `Z`**, e.g., `20260520T142300Z`. `Z` is filename-safe (just a letter) and marks the time as UTC, removing daylight-saving and timezone ambiguity. Chosen over local time for unambiguity; the small loss of at-a-glance local readability is acceptable since the timestamp is a debug annotation, not a primary interface.
- **Seconds included** (`...142300Z`, not `...1423Z`). Cheap, improves debug precision, and removes any same-minute ambiguity even though uniqueness doesn't strictly require it.

Decoding the example `20260520T142300Z`: year `2026`, month `05`, day `20`, `T` separator, hour `14`, minute `23`, second `00`, `Z` = UTC — i.e., 2026-05-20 14:23:00 UTC.

### 3.9 Behavior when `memory_run_maintenance` is invoked during an active conversation ✅ RESOLVED

**Decision** (falls out of §3.1's resolution): If the user asks Claude to run maintenance while other conversations are active:

- The bridge enumerates pending merges (branches on disk).
- For each, acquires the merge mutex, performs the merge via sub-agent, releases.
- Other conversations attempting memory I/O during a merge block on the mutex.

This means the user's "run maintenance now" command may briefly block other concurrent conversations. Acceptable for v1; the SKILL should mention this so the LLM can warn the user if it knows other conversations are likely active. (In practice, the user is the one who decides when to run maintenance, so they can pick a moment when other conversations are idle.)

### 3.10 Error response convention ✅ RESOLVED

**Background:** Traditional programming APIs tended toward terse, machine-only error codes (`ENOENT`, error number 17) because the consumer was other code that couldn't usefully act on free-form text. LLMs collapse that gap — the error message itself is the recovery instruction. This lets us provide rich error semantics that improve LLM behavior without complicating the bridge.

**Decision:** Memory tool error responses follow a uniform shape with both a stable machine-readable code and a human/LLM-readable message.

**Schema:**

```
{
  "handle": "abc1",         // echoed back if a handle was supplied and is recognized;
                            //   omitted or null if the error was a handle problem
  "ok": false,
  "error": {
    "code": "INVALID_HANDLE",         // stable identifier; never changes between bridge versions
    "message": "Handle 'xy77' is not recognized. Call memory_start_conversation to obtain a fresh handle and retry.",
    "context": { "supplied_handle": "xy77" }   // optional; included only when useful for diagnosis
  }
}
```

**Why both `code` and `message`:**

- The `message` gives the LLM a natural-language explanation it can act on directly, without needing the SKILL to enumerate every possible error code and recovery procedure.
- The `code` stays stable across message rewordings. Tests, future tooling, and any automated handling can rely on `INVALID_HANDLE` even if the message text is improved later.
- The `code` is grep-able in server logs without false matches from message text that happens to contain the same words.

**Abstraction discipline (critical):** Error messages must respect the layers established by the design. The LLM operates on the concepts of *handles*, *core*, *blocks*, *summaries*, and *the index*. Branches, mutexes, frontmatter, file paths, the per-handle branch map, and any other implementation detail are bridge-internal and must not appear in error messages.

Good error messages:
- ✅ `"Block 'foo' does not exist for this handle"` — speaks at the block abstraction.
- ✅ `"Handle 'xy77' is not recognized. Call memory_start_conversation."` — gives the LLM the recovery path.
- ✅ `"Summary is required when creating a new block"` — explains the contract.
- ✅ `"Block name 'foo bar' contains invalid characters; use letters, digits, hyphens, and underscores"` — actionable correction.

Bad error messages (leak the design):
- ❌ `"Branch 'foo.branch-h7k3-...' already exists"`
- ❌ `"Cannot acquire merge mutex; try again"`
- ❌ `"Frontmatter parse failed at line 3"`
- ❌ `"Failed to atomic-rename temp file"`

For internal errors the LLM cannot recover from (disk failure, invariant violation, sub-agent merge failure), the message is generic ("An internal bridge error occurred; the operation was not completed. Please report this to the user.") and the actual technical detail is written to a server-side log file the user can inspect when debugging.

**Initial error code set:**

| Code | Meaning |
|---|---|
| `INVALID_HANDLE` | Handle parameter present and well-formed but not recognized by the bridge |
| `MALFORMED_HANDLE` | Handle parameter present but format is wrong (length, character set) |
| `BLOCK_NOT_FOUND` | Read or operation targets a block that doesn't exist for this handle |
| `INVALID_BLOCK_NAME` | Block name contains disallowed characters or violates naming rules |
| `SUMMARY_REQUIRED` | `memory_write_block` called for a new block without a `summary` argument |
| `SUMMARY_TOO_LONG` | `summary` exceeds the configured length cap |
| `MAINTENANCE_IN_PROGRESS` | Caller-friendly version of "the bridge is currently merging memory and your operation will be retried shortly" — used when blocking on the merge mutex would exceed an acceptable wait |
| `INTERNAL_ERROR` | Catch-all for anything else; the message stays generic; details go to the server log |

New codes can be added in v1.x as new error situations are identified. The set above is the starting point; not exhaustive.

**Note on schema-validation errors:** If MCP itself rejects a call (e.g., handle parameter omitted entirely from a tool that requires it), the error response shape is whatever MCP returns and is not under the bridge's control. The SKILL teaches the LLM to recover from any handle-related rejection — schema-validation or bridge-issued — via the same procedure: call `memory_start_conversation`, retry.

**SKILL change (§4.4):** The SKILL teaches the LLM to look at the `error.message` first and act on it as natural-language instruction. The `error.code` is mentioned briefly so the LLM can recognize the recovery patterns it sees most often (`INVALID_HANDLE` and `MALFORMED_HANDLE` → call `memory_start_conversation` and retry; `SUMMARY_REQUIRED` → supply a summary and retry; etc.). The SKILL does not enumerate every code exhaustively — for any error the SKILL doesn't specifically cover, the LLM acts on the message.

### 3.11 Bridge lifecycle and orphaned branches ✅ RESOLVED

**Background.** The bridge is an MCP server spawned by Claude Desktop over stdio. When Claude Desktop closes, the stdio pipe closes, the bridge process sees EOF and terminates. The in-memory state would die with the bridge — which is precisely why §2.12 introduces state persistence. The discussion below traces the reasoning chronologically: it first works out a recovery scheme assuming no persistence (lazy adoption), then records how the §2.12 persistence decision changed lazy adoption's role from primary mechanism to backstop.

**Initial concern.** Without recovery, branches from a previous session would become "orphaned" — branch files would remain on disk, but no live handle would own them, so new conversations could not see them. Content would still be safe but invisible to any conversation until `memory_run_maintenance` ran.

**The recovery mechanism (Fran's observation).** Branch filenames already embed the handle (per §3.8: `B.branch-<handle>-<ISO8601compact-UTC>.<ext>`). The filesystem is therefore a partial backing store for the handle→branch portion of the bridge's state. When a conversation resumes after Claude Desktop reopens, its LLM context typically still contains the handle from the prior bridge instance (because the handle was echoed in every memory tool response per §2.1, making it robust to compaction). When that conversation makes any memory tool call, the bridge can rebuild the relevant map entries by scanning the directory for branch files whose embedded handle matches.

**The decision: lazy adoption.** On any memory tool call with a handle the bridge doesn't recognize, before returning `INVALID_HANDLE`, the bridge scans the blocks directory for branch files matching the pattern `*.branch-<handle>-*.<ext>`. For each match found, the bridge reconstructs the corresponding map entry `(handle, block_name) → branch_file_path` and treats the handle as live. Only if no branch files match does the bridge proceed to return `INVALID_HANDLE`.

This means:
- Conversations that resume after a Claude Desktop close, with their handle still in context, see their previous writes naturally. Branches are adopted on first use.
- Conversations the user has abandoned never make further memory calls; their branches remain on disk and are reaped at the next `memory_run_maintenance`.
- Conversations whose handle was lost from context (e.g., catastrophic compaction) get `INVALID_HANDLE` on their next memory call, recover via `memory_start_conversation`, and continue with a fresh handle. Their old branches remain on disk and are reaped at the next `memory_run_maintenance`.

**What still cannot be recovered:** The bridge cannot reconstruct per-handle read-baseline tracking from disk — that state was purely in-memory and is gone. After bridge restart and lazy adoption, the bridge has no record of what versions of any blocks the recovered handle previously read. Two consequences, both acceptable:

- **Race detection on writes:** Without a baseline, the bridge cannot tell whether a write from the recovered handle is racing with a concurrent write from another conversation. v1 policy: treat the first write after recovery as having no baseline race signal — write to the existing branch if one exists for `(handle, block)`, otherwise write to the base file. This may very occasionally miss a race, producing one cross-conversation overwrite per bridge restart per affected block. The `memory_run_maintenance` flow surfaces no help here, but the cost is bounded and small. (Stricter alternatives exist — e.g., always branch the first write after recovery — but produce spurious branches every restart, which costs more than it gains.)
- **`changed_since_last_read`:** On the first read of a block by a recovered handle, the bridge has no prior signature to compare against, so the flag is `false`. This matches the behavior on the very first read by a fresh handle (per §3.2) and is similarly acceptable.

**The bridge's branch reaping in `memory_run_maintenance`:** During maintenance, the bridge enumerates *all* branch files on disk regardless of whether their handles are in the live map. Branches whose handles are still live get merged just like any other; truly-abandoned branches (those whose conversations have gone silent forever) also get merged. From the merge sub-agent's perspective there is no distinction — branched content is branched content.

**Why option C plus lazy adoption is now the right answer.** With lazy adoption, the common case (user reopens Claude Desktop and resumes prior conversations) recovers automatically with no user-visible bookkeeping. Only abandoned conversations leave debris, and abandoned conversations by definition don't surprise anyone. Periodic invocation of `memory_run_maintenance` (the manual-trigger flow from §3.1) cleans the debris when convenient. There is no need to expose a `pending_merges` count, no need to nag the user, no need to scan-and-merge at bridge startup.

**Options revisited:**

| Option | Status |
|---|---|
| A. Auto-merge on bridge startup | Rejected. Startup blocking on sub-agent merges is bad UX; merge bugs could prevent app launch. |
| B. Expose "needs maintenance" flag to LLM | Rejected. Violates §2.2 (branches invisible to LLM). |
| C. Do nothing beyond manual `memory_run_maintenance` | **Chosen, in combination with lazy adoption.** Simplest; consistent with §3.1's manual-trigger philosophy. |
| D. Report pending count from `memory_start_conversation` | Rejected. The pending count would mostly reflect debris from abandoned conversations the user doesn't care about, making the signal noisy. |

**Superseded by §2.12 (state persistence).** The analysis above was written when bridge state was in-memory-only, making lazy adoption the *primary* recovery mechanism. Fran subsequently decided to persist bridge state across restarts (§2.12). That changes the role of lazy adoption:

- **Primary recovery is now the persisted state file.** On startup the bridge loads `.bridge-state.json`, recovering the full handle table, branch map, *and* read baselines. The read-baseline recovery is the key gain — lazy adoption alone could never recover baselines, so before persistence, every restart degraded race detection and the `changed_since_last_read` flag. With persistence, a restart is transparent.
- **Lazy adoption is now the reconciliation backstop**, not the primary mechanism. It runs at startup after loading the state file, to pick up any branch files on disk that the state file doesn't know about (created after the last checkpoint, or present when the state file is missing/corrupt). It also still runs on the unknown-handle path (§2.7) to handle a handle that's valid on disk but absent from the loaded state.

The net effect: the common close-reopen case is now fully transparent (no degradation at all), and the system degrades to the previous lazy-adoption-only behavior (branch map recovered, baselines lost) only when the state file is missing or corrupt. The design is strictly better than before and never worse.

**Implementation notes (lazy adoption, in its backstop role):**

- The directory scan in lazy adoption is cheap (single directory listing with a glob pattern). It runs at startup (once, after loading the state file) and on the unknown-handle path.
- Branch filename pattern matching must be tolerant of timestamp variation — the handle is the lookup key, not the timestamp.

**Note on what persistence does and doesn't store:** §2.12 persists handle identity, the branch map, and read baselines. The branch *files* themselves remain the source of truth for branch content; the state file only records the mapping and metadata. Because branch filenames also embed the handle (§3.8), the branch→handle association is independently recoverable from disk even if the state file is lost — which is exactly what makes lazy adoption a viable backstop. Future work that changes the branch naming convention must preserve this property or accept that the backstop stops working (the primary persisted-state path would still function).

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

- Tool definitions (currently `safe_read_file`, `safe_write_file`, `safe_append_file`, `memory_session_start`) replaced by the eight memory_* tools (per §2.1).
- Session tracker (currently `session_id → file_path → last_seen_modtime`) replaced by handle map (`handle → block_name → branch_file_path`) plus per-handle read-baseline tracking for race detection.
- Race detection logic rewritten around the per-handle branch model (§2.3 of this plan).
- Branching mechanism rewritten: instead of "create a branch on race," the model is "if no branch exists for this handle+block, create one on race; otherwise reuse."
- Atomic block write logic specified (§2.9 of this plan; single-file write with frontmatter, no cross-file coordination).
- Derived-view index implementation specified (§2.8 of this plan; bridge walks blocks directory, reads frontmatter, assembles index on demand with caching).
- Merge mutex specified (§2.6 of this plan).
- New tool `memory_run_maintenance` specified (§2.5, §3.1 of this plan): bridge enumerates pending branches, dispatches sub-agents for semantic merges, holds the merge mutex, returns when all merges complete. Also performs the §3.7 handle-cleanup sweep at the end of the pass.
- State persistence specified (§2.12 of this plan): `.bridge-state.json` in the memory root holding live handles, the branch map, and read baselines; atomic write on clean shutdown plus debounced checkpoints; load-and-reconcile at startup with lazy adoption (§3.11) as the backstop.
- Handle lifetime and cleanup specified (§3.7 of this plan): eviction of zero-branch, long-inactive handles during the maintenance sweep; configurable retention window.

### 4.3 Chapter 4 (Memory System Layer 2)

Larger change than initially scoped, due to §2.8:

- Block files now carry YAML frontmatter (`summary`, `updated_at`). Chapter 4 needs to document this format.
- `index.md` as a stored file is **removed**. The chapter should describe the index as a derived view assembled by the bridge from block frontmatter.
- Branch file naming convention updated (now includes handle, per §3.8 of this plan).
- Maintenance rule about Claude updating `index.md` is **removed** — there is no `index.md` to maintain.
- The episodic-log section stays as-is if §2.10 lands on "separate concept"; otherwise needs a substantive rewrite. Note that episodic logs likely also need frontmatter (for date-range or last-appended-at metadata) if we want them to participate in the derived index.

### 4.4 Chapter 5 (Memory Skill)

Largest simplification. The SKILL should be **much** shorter:

- No session ID instructions (handle is opaque infrastructure, never inspected).
- No branch instructions (branches don't exist as far as the LLM is concerned).
- No file paths (the bridge owns them).
- No race-recovery instructions.
- No `branches_exist` flag handling.
- New: clear instruction to call `memory_start_conversation` once per conversation and to use the most recently returned handle.
- New: optional guidance on the `summary` parameter for `memory_write_block`.
- New: instruction to call `memory_run_maintenance(handle)` when the user asks for memory maintenance, merging, consolidation, or similar. The SKILL should describe the tool conceptually (it merges branched memory back together; uses sub-agents internally; the call may take a noticeable amount of time and will briefly block other concurrent conversations' memory operations) without exposing implementation details like branches or the mutex.
- New: instruction on how to interpret `changed_since_last_read` (per §3.2). When `memory_get_core` or `memory_get_block` returns this flag as `true`, the LLM should treat any earlier reasoning that depended on the previous content as potentially stale. The SKILL should frame this in conversational terms (e.g., "this memory has been updated since you last read it; double-check anything you concluded from the earlier version") rather than mechanical terms, and should not reveal that the change came from another conversation — to the LLM, it just looks like the content changed.
- New: instruction on how to handle error responses (per §3.10). Memory tools may return `{ ok: false, error: { code, message, context? } }`. The LLM should act on the `message` (which is written to be self-explanatory) and recognize a few common patterns: `INVALID_HANDLE` or `MALFORMED_HANDLE` → call `memory_start_conversation` and retry; `SUMMARY_REQUIRED` → supply a summary and retry; `BLOCK_NOT_FOUND` → either create the block (if intended) or check the name; `INTERNAL_ERROR` → mention the failure to the user and don't retry blindly. For codes the SKILL doesn't explicitly cover, follow the `message`'s recovery instructions.
- Retained: when to read core vs. blocks vs. consult the index; when to create a new block vs. update an existing one; how to structure block content. (Note that "the index" is now described as a roll-up the bridge produces — the LLM doesn't read a file, it calls `memory_get_index`.)

### 4.5 Chapter 6 (Sub-Agent System)

Largely unaffected. Sub-agents don't write to memory (single-writer model preserved). Minor touch-ups only.

### 4.6 Chapter 7 (Deployment)

Unaffected.

### 4.7 Chapter 8 (Testing Strategy)

Moderate change. New test cases needed for:

- Handle round-trip across compaction simulation.
- Per-handle branch isolation (X's writes invisible to Y).
- Read-your-own-writes across multiple writes from the same handle.
- Derived-view index correctness (assembles correctly from block frontmatter; per-handle views show correct branch/base mix).
- Single-file atomic block write (crash simulation between temp-write and rename).
- Frontmatter handling (preserved across writes when summary not supplied; updated when supplied; gracefully defaulted if missing on read).
- Unknown/malformed handle handling: `INVALID_HANDLE` and `MALFORMED_HANDLE` returned correctly; LLM-side recovery via `memory_start_conversation`.
- State persistence (§2.12): write-on-shutdown and checkpoint produce a valid `.bridge-state.json`; load-and-reconcile at startup restores handles, branch map, and read baselines; restart is transparent to a resuming conversation (handle still recognized, baselines intact).
- Persistence corruption fallback: a missing or corrupt state file causes a clean fall-back to lazy adoption (branch map recovered from filenames, baselines reset) with no crash.
- Lazy-adoption backstop (§3.11): branch files on disk not present in the loaded state are picked up at startup.
- Handle cleanup (§3.7): zero-branch, long-inactive handles are evicted during the maintenance sweep; handles with live branches are never evicted.
- Maintenance flow: branch creation, merge, base file replacement, post-merge handle cleanup.

### 4.8 Chapter 9 (Future Enhancements)

§9.2 (memory-aware tools) was described as future work. It moves to v1, so the section either disappears or becomes a brief "this is now v1 — see Chapter 3" stub. Other §9 sections may need rewording to remove references to the old session/branching model.

### 4.9 Chapter 11 (Open Questions)

Several existing questions become moot (anything about session ID handling or branch surfacing). New questions from §3 of this plan (the ones we don't resolve before the rewrite) get added.

### 4.10 Chapter 12 (SDK Reference)

Unaffected.

---

## 5. Proposed Work Ordering

Suggested order for the rewrite conversation:

1. **Resolve all §3 open questions** (this plan) — ✅ complete.
2. **Update Chapter 3** (Bridge Server) — most consequential changes; many downstream chapters reference it.
3. **Update Chapter 4** (Memory System) — file-format and branch-naming changes.
4. **Update Chapter 5** (SKILL) — simplification pass.
5. **Update the main design doc** (§1.3, §1.4, §2.1, §2.2, §2.3) — overview reflects the new architecture.
6. **Update Chapters 6–8 and 11** — touch-ups, test cases, open questions.
7. **Update Chapter 9** (Future Enhancements) — collapse §9.2.
8. **Final cross-reference pass** — verify all internal links and consistent terminology.

Each step lands as its own PR for review. This keeps any individual PR small enough to review thoroughly, and lets us catch issues early before they propagate through later chapters.

---

## 6. Working Notes

A scratchpad for decisions, course-corrections, or additional clarifications added as this plan evolves.

### 2026-05-23 — §2.8 revised: index becomes a derived view

Fran identified that the original §2.8 (index doesn't branch, mechanically merged in place on every write) had a memory-leakage problem: applied to a single write, "latest wins" reduces to "always replace," so Y's summary updates would land in the canonical index and be visible to X immediately. The leak was real.

Two resolutions were considered:

- **Option 1: Index branches per-handle like blocks do.** Symmetric with the block model, but reintroduces a semantic-merge problem (one the redesign was supposed to eliminate) and adds two-file cross-branch atomicity per write.
- **Option 2 (chosen): Index becomes a derived view.** Block-level metadata (`summary`, `updated_at`) lives in each block's YAML frontmatter. `memory_get_index(handle)` walks the blocks directory and assembles the index on demand, using per-handle branches where present. Cached by mtime. The leak is impossible by construction because the index and blocks come from the same files.

Knock-on effects: §2.9 simplified (single-file atomic write, no cross-file coordination); Chapter 4 needs more rewriting than initially scoped (block files now have frontmatter, `index.md` no longer exists); §2.5 (merge) now regenerates frontmatter from the merged content rather than mechanically merging an index file; test-case list in §4.7 updated accordingly.

Open sub-question: episodic logs may also need frontmatter if we want them to appear in the derived index — flagged in §4.3 for the rewrite to address.

### 2026-05-24 — §3.1 and §3.9 resolved: manual-trigger merge via `memory_run_maintenance`

Decision: v1 ships with manual-trigger merging. The bridge exposes a new tool `memory_run_maintenance(handle)` that the SKILL teaches the LLM to call when the user asks for memory maintenance, merging, or consolidation. The bridge enumerates pending branches and dispatches sub-agents to perform each block's semantic merge, holding the merge mutex (§2.6) during the operation. The maintenance call is synchronous from the caller's perspective: it returns when all merges complete.

Rejected for v1 (deferred to v1.x): Windows Task Scheduler + `claude -p`, AutoHotkey driving Claude Chat, lazy-merge-at-session-start. These add automation complexity that we can layer on later once the manual approach proves out in practice. The choice prioritizes correctness and operability over full automation.

Knock-on changes: §2.1 tool surface gains `memory_run_maintenance`; §2.5 retitled and rewritten to reflect manual triggering and synchronous semantics (the merge runs in sub-agents, but the call to `memory_run_maintenance` is synchronous from the caller's view); §2.6 wording adjusted to say merges happen when invoked rather than during a "wake-up phase"; §2.9 crash recovery references the next maintenance call instead of a wake-up phase; §3.7 (handle cleanup) references updated similarly; §3.9 marked resolved as a corollary of §3.1; §4.2 (Chapter 3 changes) updated; §4.4 (SKILL changes) gains an instruction line for `memory_run_maintenance`.

Deferred to the rewrite (recorded inside §3.1): exact return-shape details, whether to support partial maintenance (one block at a time), and the no-op return when there are no pending branches.

### 2026-05-25 — §3.2 resolved: ship v1 with RMW-only branching plus `changed_since_last_read` flag

Decision: v1 keeps the existing RMW-only branching policy — branches are only created when a handle writes against a stale baseline. The stricter snapshot-isolation alternative (also branch when another handle has an outstanding read) is deferred to v1.x because the merge-load risk is concrete while the surprise it would prevent is hypothetical until observed.

To soften the surprise of "X re-reads B and sees Y's content," `memory_get_core` and `memory_get_block` return a new `changed_since_last_read` boolean. The bridge tracks per-handle content signatures (hash or ModTime+size) of the most recent read for each target. On the next read of the same target by the same handle, the flag is set to `true` if the signature changed and `false` otherwise. The flag tells the LLM "your prior view is stale" without revealing what changed or who changed it, preserving per-conversation isolation.

The flag is always `false` on first read of a target, on unchanged re-reads, and when reading the handle's own branch (because the branch's contents track that handle's own last write by construction).

Re-visit criteria recorded inside §3.2: if observation shows the `changed_since_last_read` mitigation is insufficient — e.g., LLM confusion persists, or cross-conversation overwrites cause information loss the merge can't recover — revisit the stricter-isolation option.

Knock-on changes: §2.1 tool signatures for `memory_get_core` and `memory_get_block` updated to include the flag in their response. SKILL change (§4.4) adds a line teaching the LLM how to interpret the flag.

Note on `memory_get_index`: not given a `changed_since_last_read` flag for v1. The index is a directory-style overview and per-block changes are already signaled by the per-block read flag. Can be added later if it proves useful.

### 2026-05-25 — §3.3 resolved: handle is required; no graceful re-init in the bridge

Decision: handle is a required parameter on every memory tool. The MCP schema enforces presence; the bridge enforces format and recognition. Any of (omitted, malformed, unknown) produces an error response. There is no graceful re-init path in the bridge — the LLM recovers from any handle error by calling `memory_start_conversation` to obtain a fresh handle and then retrying.

Rationale: keeping the bridge simple and the error semantics predictable. The "auto-init" alternative (silent re-init under an unknown handle) was attractive for resilience but added bridge complexity, introduced a handle-collision risk, and required the LLM to reason about whether a handle it supplied was honored or substituted. The error-and-recover approach is simpler in every dimension.

Knock-on changes: §2.7 rewritten to remove graceful re-init and document the error-and-recover behavior; §3.4 generation-site bullet updated to remove the substitute-handle option; §3.7 already references maintenance-based reaping of orphaned branches, so no change there.

Failure-mode coverage: bridge restart, compaction-induced handle loss, and LLM handle fabrication all converge on the same recovery procedure — get a new handle, retry. This is something the SKILL can teach in a single sentence.

### 2026-05-25 — §3.10 added and resolved: rich error response convention

Decision: memory tool error responses carry both a stable `error.code` (machine-readable, never changes between versions) and a natural-language `error.message` (the LLM's primary recovery signal), with optional `error.context` for diagnostic data.

Rationale: traditional terse error codes were a concession to consumer code that couldn't act on text. LLMs collapse that gap — the message is the recovery instruction. We can have the readability of natural language and the stability of error codes at the same time without complicating the bridge.

Abstraction discipline noted in §3.10 and worth emphasizing: error messages must never leak implementation details the LLM isn't supposed to know about (branches, the merge mutex, frontmatter, file paths, the per-handle branch map). For internal errors the LLM cannot recover from, the message stays generic and details go to a server-side log file.

Initial error code set (`INVALID_HANDLE`, `MALFORMED_HANDLE`, `BLOCK_NOT_FOUND`, `INVALID_BLOCK_NAME`, `SUMMARY_REQUIRED`, `SUMMARY_TOO_LONG`, `MAINTENANCE_IN_PROGRESS`, `INTERNAL_ERROR`) is starting point, not exhaustive. New codes added as new error situations are identified.

Knock-on changes: §2.7 and §3.3 forward-reference §3.10 for the error-response convention. §4.4 (SKILL changes) gets a bullet for teaching the LLM how to interpret error responses — act on the message; recognize a few common codes; for anything else, follow the message's recovery instructions.

### 2026-05-25 — §3.4 resolved and §3.11 raised

§3.4 resolved with: 8-character lowercase alphanumeric handles, bridge-minted with in-memory map collision check, PRNG for v1 (CSPRNG noted as a future upgrade when threat model warrants), in-memory only (no cross-restart persistence in v1).

§3.11 added in response to Fran's question about Claude Desktop closing terminating the bridge. Confirmed yes — bridge dies with Claude Desktop, all handles invalidated, and (more consequentially) the per-handle branch map is lost while branch files remain on disk. This produces "orphaned branches" — content that's still preserved on disk but invisible to any live conversation until `memory_run_maintenance` scans the filesystem and folds them in.

Four options considered (auto-merge on startup, expose "needs maintenance" flag, do nothing, report pending count from `memory_start_conversation`). Recommended Option D: have `memory_start_conversation` return `{ handle, pending_merges: N }` so the LLM knows whether deferred work exists. Preserves the manual-trigger philosophy from §3.1, respects the branches-invisible principle from §2.2 (count only, not branch identities), and surfaces the issue at the only moment when it actually matters (the start of a new conversation).

§3.11 is currently marked "pending Fran's review."

### 2026-05-25 — §3.11 resolved: lazy adoption from disk eliminates the orphaning problem

Fran observed that branch filenames already embed the handle (per §3.8), so the filesystem is effectively a partial backing store for the handle→branch portion of the bridge's state. After bridge restart, a resumed conversation typically still has its handle in context (because handles are echoed on every memory tool response per §2.1). When that conversation makes its next memory call, the bridge can scan disk for branch files matching the embedded handle and reconstruct the relevant map entries on the fly.

This makes the common close-reopen case transparent: the user reopens Claude Desktop, resumes a conversation, makes a memory call, and the bridge recognizes the handle (after a quick disk scan) and adopts the branches it finds. No `INVALID_HANDLE` error, no user-visible disruption.

What still cannot be recovered: per-handle read-baseline tracking. The bridge can't tell what versions of which blocks the recovered handle previously read. Acceptable degradations: the first write after recovery may miss a race (one cross-conversation overwrite per restart per affected block, bounded); `changed_since_last_read` is `false` on first reads after recovery (matches the behavior for a fresh handle).

Decision: Option C (do nothing beyond manual `memory_run_maintenance`) is the right answer once lazy adoption is in place. Pending merges that don't get adopted (because their conversations were abandoned or lost their handle) are exactly the merges no one cares about right now — they get reaped at the next maintenance run.

Knock-on changes: §2.7 substantially rewritten to specify the lazy-adoption procedure; §3.3 failure-modes table updated to reflect that bridge-restart-with-branches no longer produces an error; §3.4 closing follow-up note resolved against §3.11.

Subtle point worth preserving for future work: §3.4 says handles aren't persisted, but lazy adoption is a *partial* form of persistence — the handle→branch relationship is recoverable from disk thanks to §3.8's filename convention. Any future change to branch naming must preserve this property or accept that lazy adoption stops working. Noted at the end of §3.11.
### 2026-05-27 — §2.12 added: bridge state is persisted across restarts (supersedes the in-memory-only decision)

After seeing the close-reopen implications spelled out in §3.11, Fran decided the bridge should persist its state across restarts rather than relying on lazy adoption alone. This reverses the "in-memory only" persistence decision recorded in the 2026-05-25 §3.4 working note above.

Rationale: the bridge terminates on every Claude Desktop close, so in-memory-only state is discarded routinely, not rarely. Lazy adoption (§3.11) could recover the handle→branch map from disk but never the read baselines, so every restart degraded race detection and the changed_since_last_read flag. Persistence recovers all three pieces of state (live handles, branch map, read baselines), making restarts transparent.

Design (new §2.12): a single JSON file `.bridge-state.json` in the memory root, written atomically (temp + rename) on clean shutdown and on debounced checkpoints during operation, loaded and reconciled at startup. Reconciliation drops persisted branch entries whose files are gone and runs lazy adoption as a backstop to pick up branch files not represented in the loaded state. If the state file is missing or corrupt, the bridge falls back to pure lazy adoption — so it is never worse off than the pre-persistence design.

Role change for lazy adoption (§3.11): demoted from primary recovery mechanism to reconciliation backstop. The §3.11 analysis is preserved as the chronological record, with a "superseded by §2.12" note explaining the new role.

§3.7 resolved as part of this change: with persistence, handles live across restarts, so a cleanup policy is now needed to bound the state file. Decision — a handle is evictable when it owns zero branches AND has been inactive past a configurable retention window (default 30 days). Cleanup is folded into memory_run_maintenance (no separate timer). Evicting a zero-branch handle loses no data. Write-cadence detail also settled here: clean-shutdown write + debounced checkpoints, whole-file rewrite via temp+rename (incremental persistence deferred to v1.x).

Knock-on changes: §2.7 rewritten again to put persisted-state recovery first and lazy adoption as the backstop; §3.4 persistence bullet reversed to point at §2.12; §3.11 options table and notes updated; §3.11 background reframed to present the reasoning chronologically. §3.2's within-session logic is unchanged, but its cross-restart behavior now benefits (baselines survive), as noted in §2.12.

Note on superseded earlier notes: the 2026-05-25 §3.4 note (says "in-memory only") and the 2026-05-25 §3.11 notes (Option D recommendation, then "lazy adoption is primary") are left intact as a historical record. The authoritative current state is: persistence primary (§2.12), lazy adoption backstop (§3.11), Option C chosen for the surfacing question.

### 2026-06-04 — Retention default changed to 60 days; PR #44 (Chapter 3 §3.2 config) closed without merging

Two housekeeping items:

**Retention window default: 30 → 60 days.** Fran changed the handle retention window default from 30 to 60 days. The manual edit initially updated only one occurrence (the eviction-recovery example), leaving the authoritative statement in §3.7 item 2 and the "Retention window is configurable" note still saying 30. Reconciled both to 60 so §3.7 is internally consistent. The historical 2026-05-29 working note above still says "default 30 days" — left intact as a dated record of the original decision; the authoritative current value is 60 days.

**PR #44 closed without merging.** During this round, a surgical update to Chapter 3 §3.2 Configuration was made (session→handle terminology, `retention_days: 60`, a new `persistence:` block, and validation pseudo-code for the new params) and opened as PR #44. We then recognized this was premature — the original design documents should not be modified while the update plan is still being finalized. PR #44 was closed without merging and the local change reverted. Chapter 3 §3.2 on `main` therefore remains in its original session-era state and still needs migration as part of the full Chapter 3 rewrite (work-ordering step 2 in §5).

For the eventual Chapter 3 rewrite, the §3.2 config content devised in the closed PR #44 is a good starting point and can be reused: a `handle:` block (`id_length: 8`, `retention_days: 60`), a `persistence:` block (`state_file` path, `checkpoint_interval_seconds: 5`, immediate checkpoint on branch creation), removal of the old `max_sessions` cap (deferred to v1.x per §3.7), and the corresponding additions to the config-loading validation pseudo-code. The PR #44 branch (`docs/chapter3-config-handle-terminology`) preserves the exact text if it hasn't been deleted.

### 2026-06-05 — §3.5, §3.6, §3.8 resolved; all §3 open questions now closed

The final three open questions are resolved, completing §3:

- **§3.5 (`summary` parameter contract):** confirmed as drafted; no changes.
- **§3.6 (`memory_get_index()` schema):** confirmed as drafted, with the handle example updated from the old 4-char form to the 8-char form (`abc1def2`) per §3.4.
- **§3.8 (branch storage on disk):** naming convention confirmed as `<basename>.branch-<handle>-<ISO8601compact-UTC>.<ext>` (e.g., `core.branch-h7k3xy90-20260520T142300Z.md`). The embedded timestamp is fully specified: it is the branch's **creation time**, **frozen at creation** (never renamed on later writes — last-modified comes from filesystem mtime), and **purely informational** (the bridge never parses or compares it; lazy adoption matches by handle). Format is compact (basic) ISO 8601 in UTC with seconds and a trailing `Z` — compact because colons are illegal in Windows filenames and extended-form hyphens would collide with the filename's field separators; UTC-with-Z for timezone unambiguity; seconds for debug precision.

With this, all eleven §3 items (3.1–3.11) are resolved. §5 work-ordering step 1 is complete. The plan is ready for the design-document rewrite, which will be executed in a fresh conversation working from this plan plus the existing chapter files, following the §5 ordering (Chapter 3 first, then Chapter 4, Chapter 5, the main design doc, remaining chapters, and a final cross-reference pass).

Note on the §3.6 `updated_at` JSON value (`2026-05-20T14:23:00Z`): this is intentionally the *extended* ISO 8601 form, not the compact form used for branch filenames. Colons are legal in JSON string values, so the more readable extended form is fine there; the compact form is only required for filenames (§3.8). The two formats coexisting is deliberate, not an inconsistency.
