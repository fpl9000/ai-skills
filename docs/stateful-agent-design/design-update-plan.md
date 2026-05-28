# Stateful Agent Design — Update Plan

**Author:** Claude Opus 4.7 (with guidance from Fran)  
**Date:** May 2026  
**Status:** Working draft. Expected to evolve as open questions are resolved.

**Source materials:**
- [memory-aware-tools-idea.md](../../docs/stateful-agent-design/memory-aware-tools-idea.md) — transcript of the design discussion with Claude Sonnet 4.6
- [memory-aware-tools-analysis.md](./memory-aware-tools-analysis.md) — review of that discussion
- [design-review.md](./design-review.md) — critical design review by Claude Opus
- [stateful-agent-design.md](./stateful-agent-design.md) and chapter files — the current design

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
    → { handle, content: "...", changed_since_last_read: bool }

memory_write_core(handle, content)
    → { handle, ok: true }

memory_get_index(handle)
    → { handle, index: { blocks: [{ name, summary, updated_at }, ...] } }

memory_get_block(handle, name)
    → { handle, content: "...", changed_since_last_read: bool }

memory_write_block(handle, name, content, summary?)
    → { handle, ok: true }

memory_append_block(handle, name, content)
    → { handle, ok: true }

memory_run_maintenance(handle)
    → { handle, ok: true, merged_blocks: N, errors?: [...] }
```

Notes:

- The handle is returned in **every** tool response, not just from `memory_start_conversation`. This refreshes the handle in the LLM's context on every memory tool call, dramatically reducing the chance that compaction can lose it.
- There is no separate index-update tool. The `summary` parameter to `memory_write_block` is stored in the block file's YAML frontmatter (see §2.8). The bridge writes the body and frontmatter together as one file, so no cross-file coordination is needed.
- `memory_get_index()` returns a structured object assembled by the bridge from the blocks directory. It is a derived view, not a stored file (see §2.8).
- `memory_run_maintenance()` is invoked manually by the LLM when the user asks for memory maintenance. It dispatches sub-agents to semantically merge branched memory blocks (see §2.5, §3.1).

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

### 2.7 Error on unknown or malformed handle (with lazy adoption from disk)

If the bridge receives a memory tool call with a handle it doesn't recognize, it first attempts lazy adoption from disk before returning an error (per §3.11).

**The procedure for an unrecognized handle:**

1. If the handle is malformed (wrong length, wrong character set), return `MALFORMED_HANDLE` immediately — no adoption attempt.
2. If the handle is well-formed but not in the in-memory map, scan the blocks directory for branch files matching `*.branch-<handle>-*.<ext>`.
3. If any branch files are found, reconstruct the corresponding `(handle, block_name) → branch_file_path` entries in the map, treat the handle as live, and proceed with the original tool call. Per-handle read-baseline state is *not* recovered (it was purely in-memory), so the first read for any block by the recovered handle sets a fresh baseline and the `changed_since_last_read` flag is `false` on first reads.
4. If no branch files match, return `INVALID_HANDLE`. The SKILL teaches the LLM to call `memory_start_conversation` to obtain a fresh handle and retry.

The error response carries a clear textual description (see §3.10 for the error-response convention). The recovery procedure, taught by the SKILL, is uniform across all handle error cases: call `memory_start_conversation` to obtain a fresh handle, then retry the original operation with the new handle.

**Cases that produce a handle error after the procedure above:**
- Handle parameter omitted entirely → MCP schema-validation error before the call reaches the bridge.
- Handle malformed (wrong length, wrong character set, etc.) → bridge returns `MALFORMED_HANDLE`.
- Handle well-formed but neither in the in-memory map nor present in any branch filename on disk → bridge returns `INVALID_HANDLE`. Common causes: LLM fabricated the handle; the handle was issued by a long-departed bridge instance for a conversation that never branched; the LLM is in a brand-new conversation that hasn't called `memory_start_conversation` yet but is somehow passing a handle.

**Cases that no longer produce a handle error (thanks to lazy adoption):**
- The bridge restarts (e.g., Claude Desktop close/reopen) and a conversation resumes with its prior handle still in context, and that conversation had created at least one branch → the bridge adopts the branches from disk and the call proceeds normally.

**Important corner case:** A resumed conversation whose prior handle had *no* branches on disk (because it never wrote, or only wrote to base files) will still get `INVALID_HANDLE` — there's nothing on disk to discover. The conversation recovers cleanly via `memory_start_conversation` with no data lost (since base writes are visible to anyone reading the base). This is the right behavior: handles without disk-persistent state are not preserved, but no information is lost.

The earlier draft of §2.7 specified silent re-init under any unknown handle. That was rescinded in favor of the explicit-error approach as part of resolving §3.3, then refined further when §3.11 added lazy adoption from branch filenames. Net trade-off: predictable bridge behavior, no handle-collision risk, simpler internal state, and the common close-reopen case still works transparently because of the disk-recoverable portion of the handle→branch map.

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

---

## 3. Open Questions Still to Resolve

These need answers before the rewrite. Listed roughly in order of consequence.

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

**Persistence.** The handle→state map is in-memory only. On bridge restart all handles are invalidated; the next memory tool call from each conversation receives an `INVALID_HANDLE` error and the LLM recovers via `memory_start_conversation` (per §2.7 / §3.3). Cross-restart persistence is deferred to v1.x.

**Open follow-up resolved in §3.11:** Closing Claude Desktop invalidates every handle simultaneously. The lazy-adoption mechanism specified in §3.11 covers the common case (conversations resume with their handle still in context) so most users never see the impact.

### 3.5 `summary` parameter contract

For `memory_write_block(handle, name, content, summary?)`:

- **For new blocks** (no existing block file with that name visible to this handle): `summary` is required. The bridge rejects the call with a clear error if absent.
- **For existing blocks:** `summary` is optional. If absent, the existing summary in the block's frontmatter is preserved unchanged. If present (including empty string), it replaces the existing frontmatter summary.
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

- **On bridge restart:** all in-memory state is lost. Branches on disk remain and are reaped by the next `memory_run_maintenance` call.
- **On graceful Claude Desktop disconnect:** the bridge sees the stdio pipe close; it could clean up all handles at that point. But the discussion noted (line 153) that this only signals "Claude Desktop exited" — it can't tell which conversations were ongoing. Best behavior: at disconnect, mark all handles as orphaned; their branches will be merged during the next `memory_run_maintenance` call.
- **On idle timeout:** a handle that hasn't seen activity in N hours could be auto-evicted. Probably not worth the complexity in v1.

### 3.8 Where do branches store on disk?

Proposed naming convention: `<basename>.branch-<handle>-<ISO8601compact>.<ext>`. Example: `core.branch-h7k3-20260520T1423.md`.

This embeds the handle in the filename, which:

- Lets the bridge reconstruct the handle→branch map from disk on startup (for branches whose handles are still active).
- Makes orphaned branches (handle no longer active) visible by inspection.
- Replaces the random hex suffix from the old design with the handle itself, which is more meaningful.

The on-disk layout remains flat: branches sit alongside their base files in the same directory. The SKILL never references this layout; only the bridge does.

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

**Background.** The bridge is an MCP server spawned by Claude Desktop over stdio. When Claude Desktop closes, the stdio pipe closes, the bridge process sees EOF and terminates. Per §3.4, the handle→state map is in-memory only and dies with the bridge.

**Initial concern.** Without recovery, branches from a previous session would become "orphaned" — branch files would remain on disk, but no live handle would own them, so new conversations could not see them. Content would still be safe but invisible to any conversation until `memory_run_maintenance` ran.

**The recovery mechanism (Fran's observation).** Branch filenames already embed the handle (per §3.8: `B.branch-<handle>-<ISO8601compact>.<ext>`). The filesystem is therefore a partial backing store for the handle→branch portion of the bridge's state. When a conversation resumes after Claude Desktop reopens, its LLM context typically still contains the handle from the prior bridge instance (because the handle was echoed in every memory tool response per §2.1, making it robust to compaction). When that conversation makes any memory tool call, the bridge can rebuild the relevant map entries by scanning the directory for branch files whose embedded handle matches.

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
| C. Do nothing beyond manual `memory_run_maintenance` | **Chosen, in combination with lazy adoption.** Simplest; consistent with §3.1's manual-trigger philosophy. The lazy-adoption recovery mechanism handles the common case automatically; manual maintenance handles the rest. |
| D. Report pending count from `memory_start_conversation` | Rejected. The pending count would mostly reflect debris from abandoned conversations the user doesn't care about, making the signal noisy. Lazy adoption already handles the cases the user *does* care about. |

**Implementation notes:**

- The directory scan in lazy adoption is per-call but cheap (single directory listing with a glob pattern). It runs only on unknown-handle paths, which is the slow path anyway.
- Optimization deferred to v1.x if it proves necessary: the bridge could perform a single full scan on startup, building a `handle → [branch files]` cache, then consult the cache on unknown-handle calls. For v1, scan-on-demand is fine.
- Branch filename pattern matching must be tolerant of timestamp variation — the handle is the lookup key, not the timestamp.

**Note on the partial-persistence reality:** §3.4 specifies that handles aren't persisted across bridge restarts. That remains true in a strict sense — handle *identity*, *issuance*, and *read baselines* are not persisted; only the handle → block-branch relationship is recoverable from disk because branch filenames carry the handle. This is a happy accident of §3.8's filename convention rather than an intentional persistence design. Worth noting because future work that changes the branch naming convention must preserve this property or accept that lazy adoption stops working.

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
- New tool `memory_run_maintenance` specified (§2.5, §3.1 of this plan): bridge enumerates pending branches, dispatches sub-agents for semantic merges, holds the merge mutex, returns when all merges complete.

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

A scratchpad for decisions, course-corrections, or additional clarifications added as the plan evolves.

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
