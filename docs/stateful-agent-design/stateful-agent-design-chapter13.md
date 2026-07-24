# Stateful Agent System: Detailed Design – Chapter 13

**Version:** 1.0  
**Date:** July 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)  
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Chapter 3: MCP Bridge Server](stateful-agent-design-chapter3.md) — the normative specification this appendix sequences.

## Contents

- [13. Appendix: Implementation Ordering for Branching and Merging](#13-appendix-implementation-ordering-for-branching-and-merging)
  - [13.1 Purpose and Scope](#131-purpose-and-scope)
  - [13.2 The Governing Constraint](#132-the-governing-constraint)
  - [13.3 Two Kinds of Prerequisite](#133-two-kinds-of-prerequisite)
  - [13.4 The Ordered Plan](#134-the-ordered-plan)
  - [13.5 Milestone Boundaries and Stopping Points](#135-milestone-boundaries-and-stopping-points)
  - [13.6 Dependency Summary](#136-dependency-summary)
  - [13.7 Effect on Chapter 7 (Build and Deployment)](#137-effect-on-chapter-7-build-and-deployment)
  - [13.8 Relationship to Multi-Bridge Concurrency (Section 3.25)](#138-relationship-to-multi-bridge-concurrency-section-325)

---

## 13. Appendix: Implementation Ordering for Branching and Merging

### 13.1 Purpose and Scope

The minimal Layer 2 build in `fpl9000/mcp-bridge` (the eight-tool, memory-only build scoped by that
repository's `IMPLEMENTATION-PROMPT.md`) deliberately omits the invisible per-handle branching
subsystem of [Section 3.15](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection)
and the semantic merge process of [Section 3.17](stateful-agent-design-chapter3.md#317-merge-process-and-merge-mutex).
In that build, writes are unconditional last-writer-wins.

This appendix defines the order in which the omitted functionality should be added so that branching
works correctly in the **single-bridge** case, which is the immediate goal. It is a sequencing
document, not a specification: every item below is already specified normatively in Chapter 3, and
this appendix only says *in what order* to implement those specifications and *why that order is
forced*. Where an item's position in the order is non-obvious or counter-intuitive, the reasoning is
given explicitly.

Multi-bridge concurrency ([Section 3.25](stateful-agent-design-chapter3.md#325-multi-bridge-concurrency))
is a later goal and is out of scope here except where a single-bridge step should be implemented in
its multi-bridge-ready form to avoid rework; those cases are called out individually in
[Section 13.8](#138-relationship-to-multi-bridge-concurrency-section-325).

### 13.2 The Governing Constraint

**No functionality is re-implemented.** Every piece of new code either (a) implements a Chapter 3
specification that the minimal build left unimplemented, or (b) is functionality the minimal build
*explicitly* marked as omitted (in a code comment referencing the relevant section or the
`IMPLEMENTATION-PROMPT.md` scope). Nothing is redesigned in passing, and no working code is rewritten
except where this appendix identifies it as **currently correct only under the no-branching
assumption** — see [Section 13.3](#133-two-kinds-of-prerequisite).

The practical test for the implementer: before writing any code for an item below, locate the
Chapter 3 section it implements and the matching "deferred / omitted / not implemented in this build"
marker in the current source. If both exist, the item is in scope as specified. If the source has no
such marker — meaning the minimal build already implemented something in this area — stop and treat
the difference as potential drift to be reconciled against the spec before proceeding, exactly as was
done for the `memory_start_conversation` bundling deviation.

### 13.3 Two Kinds of Prerequisite

The prerequisites to branching fall into two categories, and the distinction matters because it
determines whether an item is a pure addition or a modification of existing code.

- **Additive (restore omitted spec structure).** The minimal build left a field, a map, or a code
  path out entirely. Adding it back is pure construction against the spec and disturbs nothing that
  currently works. Example: restoring `HandleState.Branches`.

- **Corrective (currently correct only because branches don't exist).** The minimal build contains
  code that is spec-compliant *for a build with no branches* and becomes spec-violating the moment
  branch files can exist on disk or two handles can see different views. This code must change
  **before** branching is switched on, or branching will be silently defeated by it. These are the
  dangerous items, because they look finished. Each is flagged **[CORRECTIVE]** below.

Treating a corrective item as though it were merely additive — building branching on top of it
without changing it first — is the single most likely way for this work to produce subtle,
hard-to-attribute memory corruption. The corrective items are therefore front-loaded in the order.

### 13.4 The Ordered Plan

Each step lists the Chapter 3 section it implements, its category, what it touches, and why it holds
the position it does. Steps 1–5 are prerequisites; step 6 is branching itself; step 7 is merging.

#### Step 1 — Add a content hash to the read-baseline signature **[CORRECTIVE]**

- **Implements:** [Section 3.25.5](stateful-agent-design-chapter3.md#3255-strengthening-the-read-baseline-signature)
  (the `Hash` field), applied here for a single-bridge reason rather than a multi-bridge one.
- **Touches:** the `Signature` type and its `Equal` method; every site that computes a signature.
- **Why first:** branching's entire branch/no-branch decision is the signature comparison. The
  minimal build compares `ModTime` + `Size` only, and its own comment calls a content hash "a
  possible v1.x upgrade" — optional under last-writer-wins, because a false "unchanged" there merely
  produces a slightly stale `changed_since_last_read` flag. Under branching, the same false match
  causes the write path to *suppress a branch that was required* and overwrite a concurrent
  conversation's block — the precise data loss branching exists to prevent. On Windows especially, a
  coarse filesystem timestamp combined with an in-place edit that preserves file size is a realistic
  way to hit that false match. The hash must exist and be authoritative before any code consumes the
  comparison's verdict to make a branch decision, so it is unconditionally first.

#### Step 2 — Restore `HandleState.Branches` and persist it **[additive]**

- **Implements:** [Section 3.15](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection)
  (the per-handle branch map) and [Section 3.18](stateful-agent-design-chapter3.md#318-bridge-state-persistence-and-recovery)
  (persisting it).
- **Touches:** the `HandleState` struct (add `Branches map[string]string`); the persistence
  serialization and load-and-reconcile path.
- **Why here:** nothing can *record* a branch without the map, and the map must survive a bridge
  restart or a mid-conversation bridge bounce orphans live branches (a handle would lose the pointer
  to its own branch file and fall back to the base, silently discarding its divergent view). This is
  pure restoration of omitted spec structure; it changes no behavior on its own, so it is safe to
  land before the logic that uses it.

#### Step 3 — Make the derived index branch-aware, and make its cache per-handle **[CORRECTIVE]**

- **Implements:** [Section 3.15](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection)
  index-assembly steps 2–3 (base files only; per-handle branch substitution) and the per-handle index
  cache.
- **Touches:** `assembleIndex` (exclude `*.branch-*` files from block enumeration); the index-read
  path (substitute a handle's branch of a block for the base when the branch map has an entry); the
  `IndexCache` type (from a single shared cache keyed on directory mtime to one cache per handle).
- **Why here, and why corrective — two distinct problems:**
  1. *Enumeration.* Once branch files live in the blocks directory, `assembleIndex`'s "every `*.md`"
     walk will index them as if they were blocks, producing phantom index entries the LLM can see.
     The exclusion must be in place before the first branch file can be created.
  2. *Caching.* The minimal build's index cache is a **single shared** value invalidated on directory
     mtime. Section 3.15 specifies **one cache per handle**, because under branching two handles
     legitimately see *different* index views of the same directory. A shared cache would serve one
     handle the view that includes another handle's branch — defeating branch isolation invisibly,
     with no error. This is the subtler of the two and the reason the whole step is corrective: the
     cache looks finished and is not, for a branched world.

#### Step 4 — Implement branch filename production and parsing **[additive]**

- **Implements:** [Section 3.15](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection)
  filename convention: `<basename>.branch-<handle>-<ISO8601compact-UTC>.<ext>` (e.g.
  `core.branch-h7k3xy90-20260520T142300Z.md`).
- **Touches:** a small self-contained producer/parser module: build a branch filename from
  `(basename, handle, now)`; recover the owning handle from a filename by glob/parse.
- **Why here:** foundational and dependency-free, so it can be built and unit-tested in isolation at
  any point in steps 1–4; it is placed just before the write-path wiring that first needs it. Two
  correctness notes for the implementer: the timestamp is the **compact** UTC form
  (`20260520T142300Z`), distinct from the *extended* form used in the index JSON — colons are illegal
  in Windows filenames; and the producer must handle **both** `core.md` in the memory root and
  `blocks/*.md`, because core branches too ([Section 3.9](stateful-agent-design-chapter3.md#39-tools-memory_get_core-and-memory_write_core)).

#### Step 5 — Replace the Windows write with a genuinely atomic replace **[CORRECTIVE]**

- **Implements:** [Section 3.25.6](stateful-agent-design-chapter3.md#3256-atomic-replace-on-windows),
  promoted from the multi-bridge phase to here.
- **Touches:** `atomicWriteFile` (replace the remove-then-rename fallback with `MoveFileEx` +
  `MOVEFILE_REPLACE_EXISTING`, or `ReplaceFile`).
- **Why here — a correction to where this was originally filed:** this refinement was placed in the
  multi-bridge phase in the Section 3.25 work, on the assumption that the single-bridge memory mutex
  fully covers the remove-then-rename non-existence window. That assumption fails once branching
  exists *even in a single bridge*: the merge process (step 7) releases and reacquires around
  per-block work, and branch read routing can interleave with a base write, so a reader can land in
  the window and observe a block as non-existent — reporting `BLOCK_NOT_FOUND` for a block that
  exists. It is cheaper and safer to make the replace truly atomic before branching than to debug an
  intermittent phantom-missing-block report afterward. Hence it is a single-bridge prerequisite, not
  a multi-bridge one.

#### Step 6 — Wire race-routing into the write path: branching proper **[additive, but the payoff step]**

- **Implements:** [Section 3.15](stateful-agent-design-chapter3.md#315-per-handle-branching-and-race-detection)
  write routing.
- **Touches:** the block/core write handlers. On a write, compare the writing handle's baseline for
  the target against the target's current on-disk signature (now hash-backed, step 1). If they match,
  write the base as today. If they differ, a concurrent conversation changed the base since this
  handle last read it: write to a new branch file (step 4), record `(handle, block) → branch path` in
  the branch map (step 2), and route this handle's subsequent reads/writes/index views of that block
  to its branch (step 3). Reads gain the symmetric routing: a handle with a branch of B reads its
  branch, not the base.
- **Why here:** it consumes all five prerequisites and nothing else. After this step, last-writer-wins
  is replaced by never-lose in the single-bridge case. **This is a coherent, shippable stopping
  point** — see [Section 13.5](#135-milestone-boundaries-and-stopping-points).

#### Step 7 — Implement the semantic merge: `memory_run_maintenance` **[additive — but drags in the sub-agent subsystem]**

- **Implements:** [Section 3.17](stateful-agent-design-chapter3.md#317-merge-process-and-merge-mutex),
  plus the `MAINTENANCE_IN_PROGRESS` error code
  ([Section 3.19](stateful-agent-design-chapter3.md#319-error-response-convention)) and the ninth
  registered tool.
- **Touches:** far more than the preceding steps. The merge is performed by a `claude -p` sub-agent
  doing a three-way semantic combine, so this step unblocks the entire deferred sub-agent subsystem:
  `spawn_agent`, the shared async executor, `ClaudeCLIConfig`, and `MaintenanceConfig`, all of which
  the minimal build defers together (see the `(deferred)` markers in `config.go` and the scope note
  in `tools.go`). It also adds the merge mutex and its interaction with the memory mutex
  ([Section 3.17](stateful-agent-design-chapter3.md#317-merge-process-and-merge-mutex)).
- **Why last, and why it is a hard gate rather than a nicety:** branching without merging is
  coherent but **monotonic** — every raced write forks a branch that nothing ever folds back, so
  branch files accumulate without bound. Within a single bridge this accumulates slowly, but it does
  accumulate. Merging is therefore not optional for a long-lived deployment; it is the second half of
  branching. Its cost is that it cannot be done as a self-contained memory feature: it requires the
  sub-agent machinery, which is why it is isolated as the final milestone rather than bundled with
  step 6.

### 13.5 Milestone Boundaries and Stopping Points

There are exactly two safe places to stop, and one place that looks like a stopping point but is not:

- **After step 6 — Branching milestone (safe, shippable).** Single-bridge branching is complete and
  correct: concurrent conversations never silently overwrite one another. Deployable as-is for as
  long as branch accumulation stays tolerable. This is the correct first delivery.
- **After step 7 — Merging milestone (safe, complete for single-bridge).** Branches are folded back
  on user-invoked maintenance; the single-bridge memory system matches the full Chapter 3
  specification. This is the correct second delivery and the prerequisite for any multi-bridge /
  Claude Code work ([Section 13.8](#138-relationship-to-multi-bridge-concurrency-section-325)).
- **Between steps 6 and 7, as a permanent state — not safe.** Shipping branching with no merge path
  and leaving it there indefinitely lets branches grow without bound. Acceptable as a temporary
  milestone boundary; not acceptable as a destination.

Steps 1–5 individually are **not** stopping points in the product sense — they add latent structure
and corrective changes that are inert until step 6 switches branching on — but each is independently
testable and should be landed and tested on its own before the next begins. In particular, steps 1,
3, and 5 (the corrective ones) each warrant regression tests proving the pre-branching behavior is
unchanged, since their whole risk is disturbing code that currently works.

### 13.6 Dependency Summary

```
Step 1  content-hash signature   ─┐
Step 2  branch map + persistence ─┤
Step 3  branch-aware index+cache ─┼──►  Step 6  race-routing (BRANCHING)  ──►  Step 7  merge (MERGING)
Step 4  branch filename codec    ─┤                                              │
Step 5  atomic Windows replace   ─┘                                              └─ unblocks sub-agent
                                                                                    subsystem (spawn_agent,
   corrective: 1, 3, 5                                                              async executor, CLI cfg,
   additive:   2, 4                                                                 maintenance cfg, merge mutex)
```

Steps 1–5 have no ordering dependencies *among themselves* and may be implemented in any internal
order or in parallel; the numbering reflects recommended risk-first sequencing (corrective items and
the hash the write decision depends on come first). Step 6 depends on all of 1–5. Step 7 depends on
6.

### 13.7 Effect on Chapter 7 (Build and Deployment)

**Minimal to none.** Chapter 7 documents how to *build the binary and deploy it to clients* — compile
the bridge, configure Claude Desktop and Claude Code, set up the memory directory, seed initial
memory, install the skill. None of that is touched by *how the bridge's internals are ordered
during implementation*. The appendix and Chapter 7 are orthogonal: Chapter 7 describes deploying
whatever the current binary is, and this appendix describes the order in which that binary's features
are written.

There is exactly one forward coupling, and it is triggered by **step 7**, not by this appendix:

- When the semantic-merge milestone lands, the sub-agent subsystem becomes live, which means the
  bridge configuration grows the keys the minimal build marks `(deferred)` — the `claude -p` CLI path
  (`ClaudeCLIConfig`), the async executor settings, and `MaintenanceConfig`. The configuration
  example in [Section 7.2](stateful-agent-design-chapter7.md#72-claude-desktop-configuration) and the
  build note in [Section 7.1](stateful-agent-design-chapter7.md#71-build-the-bridge) will need
  **additive** updates at that point: new keys documented, nothing restructured or renumbered.

That update is a consequence of *implementing merging*, not of *adding this appendix*, and it is
purely additive. Steps 1–6 require **no** Chapter 7 change at all: branch files, the branch map,
per-handle index caches, and the atomic replace are all internal to the bridge and invisible to
deployment. So the answer to "will this cause much churn in Chapter 7" is: nothing now, and only a
small additive config note whenever step 7 is eventually built.

### 13.8 Relationship to Multi-Bridge Concurrency (Section 3.25)

Two of the prerequisites here were originally specified in the multi-bridge section, and are pulled
forward deliberately:

- **The content-hash signature (step 1)** is specified in
  [Section 3.25.5](stateful-agent-design-chapter3.md#3255-strengthening-the-read-baseline-signature)
  as a multi-bridge hardening, but is a single-bridge *branching* prerequisite for the reason given in
  step 1. Implementing it now is not premature multi-bridge work; it is required by single-bridge
  branching and merely happens to also be needed later.
- **The atomic Windows replace (step 5)** is likewise specified in
  [Section 3.25.6](stateful-agent-design-chapter3.md#3256-atomic-replace-on-windows) but is a
  single-bridge branching prerequisite (step 5's rationale).

Implementing both in their Section 3.25 form now means they will not need to be revisited when
multi-bridge support is built. **Everything else in Section 3.25 remains deferred** and must not be
pulled forward: the cross-process file lock, per-client state files, client-scoped temp filenames,
and the self-healing branch-map routing are multi-bridge concerns with no single-bridge purpose, and
adding them now would be unused complexity. The correct reading is: single-bridge branching and
merging (steps 1–7) come first and are a hard prerequisite for multi-bridge, because
[Section 3.25.8](stateful-agent-design-chapter3.md#3258-effect-on-branching-and-merging) shows that
multi-bridge turns branching from rare to routine — and there is no point making routine an operation
that does not yet exist.
