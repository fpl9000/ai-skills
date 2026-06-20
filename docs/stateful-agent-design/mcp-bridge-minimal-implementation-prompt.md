# Claude Code Prompt — Minimal `mcp-bridge` Implementation

Build the **minimal first cut** of the MCP Bridge Server for my Stateful Agent System:
the memory subsystem only. No sub-agent spawning, no local command execution, no
maintenance/merging, and no branching. The goal is a working, tested, single-binary
MCP server that gives Claude Desktop persistent Layer 2 memory through a small family
of memory-aware tools.

My general conventions — code commenting density, commit-message style, shell
environment (Windows 11 + Cygwin), and so on — are already in
`C:\Users\flitt\.claude\CLAUDE.md`. Follow them. This prompt only states the things
that are *specific to this task* and the decisions I've already made about scope.

---

## 1. Authoritative specification

The complete, authoritative design lives in my `fpl9000/ai-skills` repo under
`docs/stateful-agent-design/`. Read it there (clone the repo if you don't already have
it locally). The main document is `stateful-agent-design.md`; the chapters are
`stateful-agent-design-chapter3.md` through `...-chapter12.md`.

**Important:** the design document describes the *full* twelve-tool system. You are
building a deliberate **subset** of it. Where the document describes spawning,
`run_command`, maintenance, merging, or branching, read it for context but do **not**
implement it. The scope table in Section 3 below is the contract — when the document
and this prompt disagree about *what to build*, this prompt wins; when they disagree
about *how a thing in scope behaves*, the document wins.

Sections you must read closely (all in `chapter3` unless noted):

- Main doc §1–§2 — overview, architecture, terminology, data flows.
- §3.1 — Go module structure (I've pruned the file list for you in Section 4 below).
- §3.2 — configuration schema and loading (with my modifications in Section 5 below).
- §3.3, §3.7 — tool summary and the memory-tool abstraction/handle protocol.
- §3.8–§3.12 — the eight in-scope tool handlers.
- §3.14 — handle management (minting, handle map, read baselines, retention).
- §3.16 — block file format and atomic writes.
- §3.18 — bridge state persistence and recovery.
- §3.19 — error response convention.
- §3.22 — logging. §3.23 — error handling. §3.24 — graceful shutdown.
- Chapter 4 §4.3–§4.8 — file formats: core.md, derived index, blocks, episodic logs,
  decisions, naming conventions.
- Chapter 8 §8.1 — the bridge unit tests (in-scope subset listed in Section 7 below).
- Chapter 12 — the `mark3labs/mcp-go` SDK reference. Use this SDK for the MCP layer;
  do not hand-roll the protocol.

Sections to read only for context and then **skip implementing**: §3.4–§3.6
(`spawn_agent`, `check_agent`, `run_command`), §3.13 (maintenance), §3.15 (branching),
§3.17 (merge), §3.20 (async executor), §3.21 (job lifecycle).

---

## 2. The two scope-narrowing decisions I've already made

These differ from the design document, so apply them everywhere:

1. **No branching at all.** The full design resolves a concurrent read-modify-write
   race by transparently routing the losing write to a per-handle *branch* of the
   block. We are **not** building that in this cut. Instead, the write mutex serializes
   all memory I/O and the **last writer to a block wins**. This means the entire
   branching subsystem is omitted: no branch files, no branch naming, no branch
   routing, no branch map in the persisted state, no lazy-adoption disk scan, no
   immediate-checkpoint-on-branch. (The `changed_since_last_read` read-time flag still
   exists and is the LLM's only concurrency signal — see Section 6.)

2. **Use `gopkg.in/yaml.v3`** for parsing and composing block YAML frontmatter. It is
   pure Go and CGO-free, so it does not compromise the single-static-binary goal. It is
   the one dependency beyond the MCP SDK.

---

## 3. Scope table — exactly what to build

**Tools to implement (8):**

| Tool | Behavior reference |
|------|--------------------|
| `memory_start_conversation` | §3.8 — mint an 8-char opaque handle; return `{ handle, core, index }` in one round trip |
| `memory_get_core` | §3.9 — return core.md content; set read baseline; report `changed_since_last_read` |
| `memory_write_core` | §3.9 — replace core.md atomically; **no** frontmatter on core; last-writer-wins |
| `memory_get_index` | §3.10 — derive the index from block frontmatter on demand (per-handle cache); no stored index file |
| `memory_get_block` | §3.11 — return block body with frontmatter stripped; set baseline; report `changed_since_last_read` |
| `memory_write_block` | §3.11 — replace block body; manage `summary`/`updated_at` frontmatter; create block if absent (summary required for creation); last-writer-wins |
| `memory_append_block` | §3.11 — append to an existing block under the mutex; never creates a block (`BLOCK_NOT_FOUND` if absent) |
| `memory_append_episodic` | §3.12 — append a timestamped entry to `blocks/episodic-YYYY-MM.md`; handle month rotation; auto-create the monthly file with frontmatter |

Every memory tool takes `handle` as its first required parameter and echoes it back in
every response, success or failure (§3.7).

**Tools to OMIT (4):** `memory_run_maintenance`, `spawn_agent`, `check_agent`,
`run_command`.

**Source files to build** (from the §3.1 layout, pruned): `main.go`, `config.go`,
`tools.go`, `handles.go`, `memory_core.go`, `memory_index.go`, `memory_block.go`,
`memory_episodic.go`, `frontmatter.go`, `persistence.go`, `memmutex.go`, `errors.go`,
`logging.go`, plus `go.mod`, `go.sum`, and `bridge-config.yaml`.

**Source files to OMIT:** `branching.go`, `async.go`, `spawn.go`, `check.go`,
`run_command.go`, `maintenance.go`, `jobs.go`.

---

## 4. Repository and module

- Module path: `github.com/fpl9000/mcp-bridge`.
- Create a new **private** GitHub repo `fpl9000/mcp-bridge` and push to it (see the
  acceptance gate in Section 8 — create and push only *after* the gate passes). Use
  your existing local GitHub authentication; do not embed any token in the repo.
- Pure Go, no CGO, no external C libraries — must compile to a single static
  `mcp-bridge.exe`.
- Provide a `--version` flag (used in the build smoke test) and a short `README.md`
  covering build, configuration, and how Claude Desktop launches the binary.

---

## 5. Configuration (`config.go` + `bridge-config.yaml`)

Follow §3.2 for config-file location resolution (`--config` flag, then
`MCP_BRIDGE_CONFIG` env var, then the default path). Apply these task-specific rules:

- **Parse the full §3.2 schema** so the config file never has to change when the
  deferred features land later. Define struct fields for every section (`async`,
  `sub_agent`, `run_command`, `memory`, `handle`, `persistence`, `branching`,
  `maintenance`, `logging`, `claude_cli`). The deferred-feature sections parse and then
  sit unused — do not act on them.
- **Validate only the in-scope subset.** Require and validate `memory.*`, `handle.*`,
  `persistence.*`, and `logging.*`. Do **not** validate the executability of
  `claude_cli.path` or `run_command.shell`, and do not enforce
  `async.sync_window_seconds < 30` — those guard features this build doesn't contain,
  and enforcing them would stop the bridge from starting for no reason.
- Create `memory.directory` and its `blocks/` subdirectory if they don't exist (the
  §3.2 validator already calls for creating the memory directory).
- Ship a default `bridge-config.yaml` in the repo containing the full schema, with
  `branching.enabled: false` and a comment on each deferred section noting it is not
  yet honored by this build. It's acceptable to `go:embed` this default and write it
  out / fall back to it when no external config file is present.
- Because branching is omitted, if the loaded config sets `branching.enabled: true`,
  **log a warning** at startup ("branching not implemented in this build;
  last-writer-wins in effect") rather than silently implying behavior that isn't there.

---

## 6. Cross-cutting requirements that are easy to get wrong

- **Never log to stdout.** The bridge speaks MCP/JSON-RPC over stdout; logging there
  corrupts the protocol stream. Log to the file configured in `logging.*` (stderr is an
  acceptable secondary). This is `logging.go`, per §3.22.
- **Atomic writes everywhere** memory is modified: write to a temp file in the same
  directory, then rename over the target, so a reader never sees a partial file and a
  failed write leaves no corruption (§3.16). On write failure, clean up the temp file
  and return `INTERNAL_ERROR`.
- **Frontmatter is bridge-private** (§3.16). Block bodies returned to the LLM never
  contain the `---` frontmatter header; block content the LLM supplies is stored
  verbatim in the body even if it itself begins with `---`. core.md has no frontmatter.
- **Cold-start tolerance.** An empty store is normal and must not error:
  `memory_start_conversation` against a missing core.md and empty `blocks/` returns an
  empty `core` string and an empty `index` array (tested in §8.1.1).
- **Handles, baselines, and the change flag** (`handles.go`, §3.14): mint opaque
  lowercase-alphanumeric handles of `handle.id_length`; track per-handle read baselines
  (ModTime + size) recorded on every read; on a read, set `changed_since_last_read` by
  comparing the block's current signature against this handle's last baseline for that
  block. With branching gone, this flag is the *only* concurrency signal the LLM gets —
  the SKILL.md "stale content" guidance relies on it. Note that handle *eviction* runs
  only during the (deferred) maintenance sweep, so in this build handles are minted and
  tracked but never evicted — that's expected and fine.
- **Writes are unconditional last-writer-wins.** Write handlers proceed straight to the
  atomic base-block write under the mutex; there is no race-routing. You may optionally
  log at `info` when a write's baseline indicates it is overwriting a block that changed
  since this handle last read it, purely as a diagnostic.
- **Memory mutex** (`memmutex.go`): a single `sync.Mutex` serializing all memory file
  I/O so concurrent tool calls never interleave or corrupt a file. (Ignore the
  "merge mutex semantics" mentioned in §3.1 — that belongs to the deferred maintenance
  feature.)
- **State persistence** (`persistence.go`, §3.18): persist live handles, their read
  baselines, and last-activity to `.bridge-state.json` (no branch maps — they're always
  empty now). Debounced checkpoints per `persistence.checkpoint_interval_seconds`;
  atomic state writes (temp + rename); load-and-reconcile at startup; a corrupt or
  truncated state file logs a warning and starts clean (no lazy-adoption fallback,
  since that was branch-file recovery).
- **Graceful shutdown** (§3.24, the relevant half): on stdin EOF / shutdown, flush a
  final state checkpoint before exiting. There are no subprocesses to kill in this build.
- **Error convention** (`errors.go`, §3.19): responses are
  `{ handle, ok: false, error: { code, message [, context] } }`. The reachable code set
  in this build is `INVALID_HANDLE`, `MALFORMED_HANDLE`, `BLOCK_NOT_FOUND`,
  `INVALID_BLOCK_NAME`, `SUMMARY_REQUIRED`, `SUMMARY_TOO_LONG`, `INTERNAL_ERROR`
  (omit `MAINTENANCE_IN_PROGRESS` — its feature is deferred). Block *names*, never
  paths, are the only memory addresses: reject names containing path separators or `..`
  with `INVALID_BLOCK_NAME`. No error message may leak filesystem paths, the mutex, or
  frontmatter internals.
- **MCP layer** (`tools.go` + `main.go`): register exactly the **8** tools over the
  stdio transport using `mark3labs/mcp-go`; implement the `initialize`/capabilities
  handshake; declare each tool's input schema (handle required on all eight).

---

## 7. Tests (`go test ./...`, §8.1 subset)

Standard Go tests, each using its own temporary memory directory. Implement the
in-scope §8.1 sections, dropping the rows that assert branching/maintenance behavior:

- §8.1.1 — `memory_start_conversation` (uniqueness, format, empty store, state
  checkpoint on creation, handle survives a compaction round-trip).
- §8.1.2 — `memory_get_core` / `memory_get_block` (frontmatter stripped on read,
  baseline recorded, the `changed_since_last_read` first/unchanged/changed cases,
  read-your-own-writes, bad-name and bad-handle errors, handle echo). **Omit** the
  "Branched read routing" row.
- §8.1.3 — `memory_write_core` / `memory_write_block` (new-block-with-frontmatter,
  summary required/too-long, update with/without summary, core has no frontmatter,
  atomic replacement, temp-file cleanup on failure, frontmatter-private body).
- §8.1.4 — `memory_append_block` / `memory_append_episodic` (append to existing,
  `BLOCK_NOT_FOUND` on missing, empty-text no-op, monthly file creation, month
  rotation, timestamping, episodic indexed and readable as a block). **Omit** the
  "append routes to existing branch" row.
- §8.1.5 — derived index (empty dir, matches frontmatter, sorted by name, extended
  ISO 8601 timestamps, no index file on disk, `.bridge-state.json` excluded, missing
  frontmatter tolerated, per-handle cache invalidated on write). **Omit** the
  "index reflects own branch" row.
- §8.1.8 — state persistence (written at shutdown, debounced checkpoint, atomic write,
  load-and-reconcile at startup, corrupt file → clean start with warning). **Omit** the
  branch-file and lazy-adoption rows.
- §8.1.9 — write-mutex serialization (concurrent writes don't interleave; write +
  append on different blocks both serialize; no deadlock under rapid mixed ops; index
  derivation sees a consistent point-in-time view).
- §8.1.10 — error-response convention (shape, code set above, no abstraction leaks,
  uniform `INVALID_HANDLE` recovery).
- §8.1.15 — MCP integration (initialize handshake returns capabilities and the 8-tool
  list; missing-required-param and missing-handle errors; two concurrent calls over a
  pipe both complete).

**Omit entirely:** §8.1.6 (branching), §8.1.7 (maintenance), §8.1.11–§8.1.14
(spawn/check/run_command/jobs). The §8.2 skill tests and §8.4 integration tests are
manual procedures I'll run later against Claude Desktop — do not attempt them here.

---

## 8. Commits and the acceptance gate

**Commit in a handful of logically grouped commits**, not one big blob and not noisy
"wip" history — group along the architectural seams so I can review the build chunk by
chunk. A reasonable grouping (use your judgment):

1. Module scaffold + config loading/validation + logging.
2. Handle management + state persistence.
3. Frontmatter + block file format + atomic writes (the memory mutex).
4. Memory tools: core + index.
5. Memory tools: block + episodic.
6. MCP server wiring (tool registration, stdio, handshake) + `main` entry point + README.
7. Test suite.

The **final** state must build and pass; intermediate commits need not each be green.

**Before creating and pushing the repo, this four-part gate must pass:**

1. `go build -o mcp-bridge.exe .` succeeds and `./mcp-bridge.exe --version` runs.
2. `go vet ./...` is clean. (Pay attention to `copylocks` — the memory mutex must be
   passed by pointer, never copied by value.)
3. `gofmt -l .` reports no files.
4. `go test ./...` passes.

Only once all four pass: create the private `fpl9000/mcp-bridge` repo and push the
grouped commits over HTTPS.

---

## 9. Part B — the memory SKILL.md (separate, ungated deliverable)

After the bridge is done, produce the memory skill's `SKILL.md` from the content in
Chapter 5 §5.2, with these adjustments for the reduced scope:

- **Remove or neutralize the "Memory Maintenance" section** and any other references to
  `memory_run_maintenance` (e.g., in the lifecycle and error-handling sections) — that
  tool does not exist in this build, and the skill must not instruct Claude to call it.
- The skill must reference **only the eight implemented tools**.
- Keep everything else: the memory model, handle protocol, conversation-start protocol,
  read/write/append triggers, stale-content guidance (which leans on
  `changed_since_last_read`), block-creation rules, and the `INVALID_HANDLE`
  re-init-and-retry recovery protocol.

Write it to `skill/SKILL.md` in the `mcp-bridge` repo (I'll relocate and zip it per
§7.6 myself). The four-part gate above applies to the Go bridge only, not to this file.

---

## 10. Explicitly out of scope for this task

Do not build, and do not ask to build: sub-agent spawning, `run_command`, maintenance,
merging, branching, the async executor, or the job manager. Do **not** create or seed
`core.md` — I'm handling the initial memory seed separately with accurate content. The
bridge's only obligation toward core.md is to tolerate its absence gracefully
(cold start) and to read/write it when the tools are called.
