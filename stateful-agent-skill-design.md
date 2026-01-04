# Stateful Agent Skill: Design Document

**Version:** 0.1 (Draft)  
**Date:** January 2026  
**Author:** Claude Opus (with guidance from Fran Litterio)

## Overview

This document describes the design of an AI skill that transforms a conversational AI into a stateful agent with persistent memory. The skill provides a hierarchical memory architecture, efficient in-session queries via SQLite, human-readable canonical storage in Markdown, and pluggable persistence backends that work across cloud and local agent environments.

### Goals

- **Continuity**: Enable agents to maintain identity and accumulated knowledge across sessions
- **Transparency**: All memories stored in human-readable, editable formats
- **Portability**: Work in cloud environments (Claude.ai) and local environments (Claude Code, Gemini CLI)
- **Simplicity**: Zero-configuration defaults with progressive enhancement for power users
- **Durability**: Pluggable backends prevent memory loss from conversation deletion

### Non-Goals

- Embedding-based semantic search (adds complexity without proportional benefit)
- Real-time sync between concurrent cloud sessions (each conversation is isolated)
- Fully autonomous operation without user awareness (transparency is a feature)

### Inspirations

- [claude_life_assistant](https://github.com/lout33/claude_life_assistant) — Simple two-file approach demonstrating the core concept
- [Strix](https://timkellogg.me/blog/2025/12/30/memory-arch) — Tim Kellogg's three-tier hierarchical memory architecture

---

## Architecture

### Three-Tier Memory Model

Following Tim Kellogg's Strix architecture, memories are organized into three tiers based on access patterns and permanence:

| Tier | Contents | Loaded | Storage |
|------|----------|--------|---------|
| **Core** | Identity, personality, behavioral rules | Every session | `core.md` |
| **Index** | Pointers to knowledge, summaries, categories | Every session | `index.md` |
| **Content** | Detailed memories, episodes, research | On demand | `blocks/*.md` |

This layering solves a fundamental tension: context windows are finite, but accumulated knowledge is unbounded. Core and Index must always fit in context; Content is retrieved selectively.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Context Window                         │
├─────────────────────────────────────────────────────────────────┤
│  SKILL.md (instructions)                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Core: Who the agent is, rules, patterns                 │    │
│  │ Index: What the agent knows and where to find it        │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Content: Loaded on demand based on conversation needs   │    │
│  └─────────────────────────────────────────────────────────┘    │
│  Conversation...                                                │
└─────────────────────────────────────────────────────────────────┘
```

### Dual-Format Storage

The skill uses two complementary formats:

**SQLite (Working Memory)**
- Used during sessions for efficient queries
- Append-only semantics (history preserved)
- Ephemeral in cloud environments, cached in local environments

**Markdown (Canonical Storage)**
- Source of truth for persistence
- Human-readable and editable
- Git-friendly diffs showing exactly what changed
- Inspectable anywhere (GitHub web UI, Google Drive preview, text editors)

```
Persistence Backend
        │
        │  canonical source of truth
        ▼
┌─────────────────────────────┐
│  Markdown Files             │
│  ├── config.yaml            │
│  ├── core.md                │
│  ├── index.md               │
│  └── blocks/                │
│      ├── facts.md           │
│      ├── patterns.md        │
│      └── episodes.md        │
└─────────────────────────────┘
        │
        │  load(): parse → SQLite
        │  save(): query → render
        ▼
┌─────────────────────────────┐
│  SQLite (session cache)     │
│  - Fast queries             │
│  - Append-only history      │
│  - Rebuilt from markdown    │
└─────────────────────────────┘
```

### Why Markdown as Canonical

| Concern | Markdown | Raw SQLite |
|---------|----------|------------|
| Readability | ✓ Human-readable | ✗ Binary blob |
| Editability | ✓ Any text editor | ✗ Requires SQLite tools |
| Git diffs | ✓ Meaningful changes | ✗ Binary noise |
| Inspectability | ✓ GitHub, Drive preview | ✗ Must download |
| Merge conflicts | ✓ Mostly resolvable | ✗ Catastrophic |
| Parse overhead | ✗ Rebuild required | ✓ Direct use |

The parse overhead is acceptable because loading happens once per session, and local agents can cache the SQLite file (rebuilding only when markdown is newer).

---

## Persistence Layer

### Pluggable Backends

The skill supports multiple persistence backends, selectable via configuration:

| Backend | Environment | Setup Required | Script-Driven |
|---------|-------------|----------------|---------------|
| `filesystem` | Local only | None | Yes |
| `git_cli` | Both | Git credentials configured | Yes |
| `github_api` | Both | Personal Access Token | Yes |
| `gdrive` | Both | Google Drive connected | No (Claude orchestrates) |
| `manual` | Both | None | Yes |

#### Backend Interface

All backends implement a common interface:

```
load() → memories dict
    Load memories from persistent storage, return structured data.

save(memories) → None
    Export memories to persistent storage.

exists() → bool
    Check if persistent storage contains existing data.
```

The `gdrive` backend is special: because Google Drive requires OAuth authentication handled by Claude's built-in tools, the script cannot perform I/O directly. Instead, it prepares export files and returns instructions for Claude to execute the actual upload/download.

### Environment Detection

The skill auto-detects whether it's running in a cloud or local environment:

```
detect_environment():
    if '/mnt/user-data/outputs' exists:
        return 'cloud'    # Claude.ai or similar
    else:
        return 'local'    # Claude Code, Gemini CLI, etc.
```

This detection drives default configuration generation.

### Configuration Discovery

At session start, the skill searches for existing configuration:

```
discover_config():
    1. Check /mnt/user-data/uploads/config.yaml (cloud: user uploaded)
    2. Check AGENT_MEMORY_CONFIG environment variable
    3. Check ~/.config/agent-memory/config.yaml (local: default path)
    4. Return None if not found (triggers first-run setup)
```

If no configuration exists, the skill generates environment-appropriate defaults.

---

## Configuration

### Default Configuration

**Local agents** receive filesystem-based defaults (zero-friction persistence):

```yaml
# config.yaml (auto-generated for local environment)

persistence:
  backend: filesystem
  filesystem:
    path: ~/.local/share/agent-memory/

backup:
  checkpoint_interval: 5
  export_markdown: true

memory:
  consolidation_threshold: 50
```

**Cloud agents** receive manual-mode defaults (works immediately, upgradeable):

```yaml
# config.yaml (auto-generated for cloud environment)
#
# Currently using manual upload/download. To enable automatic
# persistence, configure one of the backends below.

persistence:
  backend: manual
  
  # Uncomment to use GitHub:
  # backend: github_api
  # github_api:
  #   repo: your-username/agent-memory
  #   path: memories/

  # Uncomment to use Google Drive:
  # backend: gdrive
  # gdrive:
  #   folder_name: AgentMemory

backup:
  checkpoint_interval: 5
  export_markdown: true

memory:
  consolidation_threshold: 50
```

### Configuration Storage

The configuration file is stored *in the same backend it describes*. This solves the bootstrap problem elegantly:

| Backend | Config Location |
|---------|-----------------|
| `filesystem` | `~/.config/agent-memory/config.yaml` |
| `github_api` | `{repo}/config.yaml` |
| `git_cli` | `{repo_path}/config.yaml` |
| `gdrive` | `AgentMemory/config.yaml` |
| `manual` | User uploads each session |

### Interactive Configuration

Users can modify configuration through conversation:

> **User:** "Let's set up GitHub persistence"
>
> **Agent:** "I'll configure GitHub as your persistence backend. What repository should I use? (e.g., 'username/agent-memory')"
>
> **User:** "fran/my-agent-memory"
>
> **Agent:** *updates config.yaml, writes to outputs*
>
> "Done. You'll need to:
> 1. Create that repo on GitHub (can be private)
> 2. Create a Personal Access Token with 'repo' scope
> 3. Set GITHUB_TOKEN in your environment"

---

## Memory Schema

### SQLite Schema

The working database uses append-only semantics following Tim Kellogg's design:

```sql
-- Memory blocks with full history preservation
CREATE TABLE memory_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tier TEXT NOT NULL,              -- 'core', 'index', or 'content'
    category TEXT NOT NULL,          -- 'facts', 'patterns', 'episodes', etc.
    name TEXT NOT NULL,              -- Block identifier
    value TEXT,                      -- Current content
    sort INTEGER NOT NULL DEFAULT 0, -- Display ordering
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Index for efficient lookups
CREATE INDEX idx_blocks_lookup ON memory_blocks(tier, category, name);

-- View for current values (latest version of each block)
CREATE VIEW current_blocks AS
SELECT tier, category, name, value, sort, created_at
FROM memory_blocks
WHERE id IN (
    SELECT MAX(id) FROM memory_blocks GROUP BY tier, category, name
);
```

No records are ever modified or deleted. New versions are inserted; the latest version wins for display. This preserves complete history for provenance and debugging.

### Markdown Schema

The canonical markdown files mirror the SQLite structure:

```
memories/
├── config.yaml           # Skill configuration
├── core.md               # Tier 1: Identity (always loaded)
├── index.md              # Tier 2: Pointers (always loaded)  
└── blocks/               # Tier 3: Content (loaded on demand)
    ├── facts.md          # Stable facts about the user
    ├── patterns.md       # Observed behavioral patterns
    ├── episodes.md       # Episodic memories (dated events)
    ├── projects.md       # Active project context
    └── insights.md       # Accumulated insights
```

### Markdown Format

Each block includes current value and append-only history:

```markdown
# facts.md

## user_name
**Current:** Fran

**History:**
- 2025-01-03T00:46:00Z: Fran

---

## user_location
**Current:** Massachusetts

**History:**
- 2025-01-03T00:46:00Z: Massachusetts

---

## primary_language
**Current:** Go

**History:**
- 2025-01-15T12:00:00Z: Go
- 2025-01-03T00:46:00Z: Python
  - *Correction: User clarified they've switched primarily to Go*
```

This format is:
- Human-readable (can inspect in any text editor)
- Git-friendly (diffs show exactly what changed and when)
- Editable (user can correct mistakes, add context)
- Parseable (structured enough for reliable import)

---

## Session Lifecycle

### Local Agent Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     Session Start                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ discover_config()     │
              │ (check filesystem)    │
              └───────────┬───────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
          Found                   Not Found
              │                       │
              ▼                       ▼
    ┌─────────────────┐    ┌─────────────────────┐
    │ Load config     │    │ Generate defaults   │
    │ Load markdown   │    │ (filesystem backend)│
    │ Build SQLite    │    │ Initialize empty db │
    └────────┬────────┘    └──────────┬──────────┘
             │                        │
             └──────────┬─────────────┘
                        ▼
              ┌─────────────────┐
              │ Session Active  │
              │ (queries hit    │
              │  SQLite)        │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    On write     Checkpoint     Session end
         │        interval           │
         ▼             │             ▼
    ┌─────────┐        │      ┌─────────────┐
    │ Update  │        │      │ Final save  │
    │ SQLite  │        │      │ to markdown │
    └────┬────┘        │      └─────────────┘
         │             │
         └──────┬──────┘
                ▼
       ┌────────────────┐
       │ Export SQLite  │
       │ → markdown     │
       │ → filesystem   │
       └────────────────┘
```

Local agents benefit from:
- Automatic persistence (no user action required)
- Shared state across concurrent sessions
- SQLite WAL mode for safe concurrent access

### Cloud Agent Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     Session Start                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Check uploads folder  │
              │ for config.yaml and   │
              │ memory files          │
              └───────────┬───────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
       Files Found              Not Found
              │                       │
              ▼                       ▼
    ┌─────────────────┐    ┌─────────────────────┐
    │ Load config     │    │ Generate defaults   │
    │ Parse markdown  │    │ (manual backend)    │
    │ Build SQLite    │    │ Initialize empty db │
    │                 │    │ Write to outputs    │
    └────────┬────────┘    └──────────┬──────────┘
             │                        │
             └──────────┬─────────────┘
                        ▼
              ┌─────────────────┐
              │ Session Active  │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    On write     Checkpoint     Session end
         │        interval           │
         ▼             │             ▼
    ┌─────────┐        │      ┌─────────────────┐
    │ Update  │        │      │ Final export    │
    │ SQLite  │        │      │ Remind user to  │
    └────┬────┘        │      │ download files  │
         │             │      └─────────────────┘
         └──────┬──────┘
                ▼
       ┌────────────────┐
       │ Export to      │
       │ /outputs/      │
       │ (checkpoint)   │
       └────────────────┘
```

Cloud agents require:
- User uploads config + memories at session start
- Periodic checkpoints to outputs folder (safety net)
- Reminder to download before session end
- Optional: GitHub or Google Drive backend eliminates manual steps

---

## Cloud Persistence Strategies

### Manual Mode (Default)

The simplest approach—user manages file transfer:

1. **Session start:** Upload `config.yaml` and `memories/` files
2. **During session:** Checkpoints written to `/mnt/user-data/outputs/`
3. **Session end:** Download updated files

The agent reminds users at natural breakpoints and before session end.

### GitHub Backend

Enables automatic sync without user file management:

1. User creates a GitHub repo and Personal Access Token
2. Configures `github_api` backend with repo name
3. Agent uses GitHub REST API to push/pull markdown files
4. Git history provides complete provenance

**Note:** Scripts can call GitHub API directly (github.com is in allowed domains), so this backend is fully script-driven.

### Google Drive Backend

For users with Google Drive connected:

1. User configures `gdrive` backend with folder name
2. Agent uses Claude's `google_drive_*` tools to sync
3. Files visible in Drive for inspection/editing

**Note:** Because Google Drive requires OAuth, Claude must orchestrate uploads/downloads—scripts prepare the files but cannot perform I/O directly.

### Checkpoint Strategy

Regardless of backend, the skill implements defensive checkpointing:

- Every N memory writes (configurable, default 5)
- Checkpoints go to `/mnt/user-data/outputs/` with timestamps
- Even if user forgets final download, they lose at most a few updates

---

## Concurrency Considerations

### Local Agents

Multiple Claude Code sessions may access the same memory store simultaneously. SQLite handles this gracefully with proper configuration:

```sql
-- Enable Write-Ahead Logging for better concurrency
PRAGMA journal_mode=WAL;

-- Set a reasonable busy timeout (milliseconds)
PRAGMA busy_timeout=5000;
```

Best practices for scripts:
- Keep transactions short
- Don't hold connections open during LLM "thinking" time
- Read, close connection, process, then open new connection to write

### Cloud Agents

Each conversation has isolated ephemeral storage—no concurrency concerns within a session. However, if the user has multiple conversations using the same GitHub/Drive backend, conflicts could occur.

Mitigation strategies:
- Last-write-wins for simple cases
- Markdown format allows manual conflict resolution
- Git-based backends preserve both versions in history

---

## Skill File Structure

```
/mnt/skills/user/stateful-memory/
├── SKILL.md                    # Instructions, identity, behavioral rules
├── scripts/
│   ├── __init__.py
│   ├── initialize.py           # Session startup, config discovery
│   ├── memory.py               # Core memory operations
│   ├── export.py               # SQLite → Markdown conversion
│   ├── import.py               # Markdown → SQLite conversion
│   └── backends/
│       ├── __init__.py
│       ├── base.py             # Abstract backend interface
│       ├── filesystem.py       # Local filesystem backend
│       ├── git_cli.py          # Git CLI backend
│       ├── github_api.py       # GitHub REST API backend
│       ├── gdrive.py           # Google Drive backend (Claude-orchestrated)
│       └── manual.py           # Manual upload/download backend
└── templates/
    ├── config.yaml.local       # Default config for local environments
    └── config.yaml.cloud       # Default config for cloud environments
```

---

## SKILL.md Outline

The skill's instruction file should cover:

1. **Identity & Purpose**
   - What this skill does
   - The three-tier memory model

2. **Session Startup**
   - Run initialization script
   - Load or generate configuration
   - Build SQLite from markdown (or initialize empty)

3. **Memory Operations**
   - When to create memories (facts, patterns, episodes)
   - When to update vs. append
   - When to load content blocks

4. **Persistence Rules**
   - Checkpoint after significant updates
   - Export to outputs folder (cloud)
   - Backend-specific instructions

5. **Session End**
   - Final export
   - Remind user to download (cloud/manual mode)
   - Offer backup to GitHub/Drive if configured

6. **User Interactions**
   - How to respond to "what do you remember about X?"
   - How to handle memory corrections
   - Configuration wizard for backend setup

---

## Open Questions

### Memory Consolidation

As memories accumulate, how should old content be consolidated?

- Automatic summarization after N entries?
- User-triggered "consolidate memories" command?
- Tiered aging (recent → summarized → archived)?

### Memory Categories

The current design proposes: facts, patterns, episodes, projects, insights. Are these the right categories? Should users be able to define custom categories?

### Cross-Session Learning

Can the agent observe patterns in its own memory evolution? Tim's Strix does this via journal analysis. Should this skill include similar self-reflection capabilities?

### Conflict Resolution

When markdown files are edited externally and conflict with SQLite state, what's the resolution strategy? Current proposal: markdown always wins (it's canonical), but this deserves more thought.

---

## Future Enhancements

- **MCP Memory Server**: For environments that support MCP, expose memory operations as tools
- **Selective Loading**: Smarter retrieval of content blocks based on conversation context
- **Memory Sharing**: Export subsets of memories for sharing between agents or users
- **Encryption**: Optional encryption for sensitive memories (especially on shared backends)

---

## References

- [claude_life_assistant](https://github.com/lout33/claude_life_assistant) — Luis Fernando's minimal stateful agent
- [Memory Architecture for a Synthetic Being](https://timkellogg.me/blog/2025/12/30/memory-arch) — Tim Kellogg's Strix architecture
- [SQLite Documentation](https://sqlite.org/docs.html) — Particularly WAL mode and concurrency
- [PEP 723](https://peps.python.org/pep-0723/) — Inline script metadata for self-contained Python scripts
