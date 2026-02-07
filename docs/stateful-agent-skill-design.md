# Stateful Agent Skill: Design Document

**Version:** 0.3 (Draft)
**Date:** January 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)

# Contents

- [Overview](#overview)
  - [Goals](#goals)
  - [Non-Goals](#non-goals)
  - [Inspirations](#inspirations)
- [Architecture](#architecture)
  - [Three-Tier Memory Model](#three-tier-memory-model)
  - [Markdown Storage](#markdown-storage)
  - [Why Markdown](#why-markdown)
- [Persistence Layer](#persistence-layer)
  - [Pluggable Backends](#pluggable-backends)
  - [First-Run Setup](#first-run-setup)
- [Configuration](#configuration)
  - [Default Configuration](#default-configuration)
  - [Configuration Storage](#configuration-storage)
  - [Interactive Configuration](#interactive-configuration)
- [Memory Schema](#memory-schema)
  - [File Structure](#file-structure)
  - [Markdown Format](#markdown-format)
- [Session Lifecycle](#session-lifecycle)
  - [Session Flow](#session-flow)
- [Cloud Persistence Strategies](#cloud-persistence-strategies)
  - [Manual Mode (Default)](#manual-mode-default)
  - [GitHub Backend](#github-backend)
    - [Checkpoint Strategy](#checkpoint-strategy)
- [Concurrency Considerations](#concurrency-considerations)
  - [Local Agents](#local-agents)
  - [Cloud Agents](#cloud-agents)
- [Skill File Structure](#skill-file-structure)
- [SKILL.md Outline](#skillmd-outline)
- [Open Questions](#open-questions)
  - [Memory Consolidation](#memory-consolidation)
  - [Memory Categories](#memory-categories)
  - [Cross-Session Learning](#cross-session-learning)
  - [Conflict Resolution](#conflict-resolution)
  - [Query Performance](#query-performance)
  - [Concurrent Write Handling](#concurrent-write-handling)
  - [Atomic Updates](#atomic-updates)
  - [Large Memory Stores](#large-memory-stores)
- [Future Enhancements](#future-enhancements)
- [References](#references)

## Overview

This document describes the design of an AI skill that transforms a conversational AI into a stateful agent with persistent memory. The skill provides a hierarchical memory architecture, human-readable storage in Markdown, and pluggable persistence backends that work across cloud and local agent environments.

### Goals

- **Continuity**: Enable agents to maintain identity and accumulated knowledge across sessions
- **Transparency**: All memories stored in human-readable, editable formats
- **Portability**: Work in cloud environments (Claude.ai) and local environments (Claude Code, Gemini CLI)
- **Simplicity**: Minimal configuration with clear options presented at first run
- **Durability**: Pluggable backends prevent memory loss from conversation deletion

### Non-Goals

- Embedding-based semantic search (adds complexity without proportional benefit)
- Real-time sync between concurrent cloud sessions (each conversation is isolated)
- Fully autonomous operation without user awareness (transparency is a feature)

### Inspirations

- [claude_life_assistant](https://github.com/lout33/claude_life_assistant) — Simple two-file approach demonstrating the core concept
- [Strix](https://timkellogg.me/blog/2025/12/30/memory-arch) — Tim Kellogg's three-tier hierarchical memory architecture


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

### Markdown Storage

All memories are stored directly in Markdown files:

**Markdown Files**
- Source of truth for all memory storage
- Human-readable and editable
- Git-friendly diffs showing exactly what changed
- Inspectable anywhere (GitHub web UI, text editors)
- Parsed directly during session operations

```
Persistence Backend
        │
        │  sync
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
        │  read/write directly
        ▼
┌─────────────────────────────┐
│  Agent Session              │
│  - Parse on read            │
│  - Update in place          │
│  - Atomic file writes       │
└─────────────────────────────┘
```

### Why Markdown

Markdown is ideal for agent memory storage:

| Benefit | Description |
|---------|-------------|
| **Human-readable** | Users can inspect memories in any text editor |
| **Editable** | Users can correct mistakes or add context directly |
| **Git-friendly** | Diffs show exactly what changed and when |
| **Inspectable** | Viewable in GitHub web UI, text editors, etc. |
| **Merge-friendly** | Conflicts are resolvable (unlike binary formats) |
| **Portable** | Works everywhere, no special tools required |

The trade-off is that lookups require parsing, but this is acceptable for typical memory sizes. See [Open Questions](#open-questions) for considerations on scaling.

## Persistence Layer

### Pluggable Backends

The skill supports multiple persistence backends, selectable via configuration:

| Backend | Environment | Setup Required | Script-Driven |
|---------|-------------|----------------|---------------|
| `filesystem` | Local only | None | Yes |
| `git_cli` | Local | Git credentials configured | Yes |
| `github_api` | Local + Cloud | Personal Access Token | Yes |
| `manual` | Local + Cloud | None | Yes |

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

### First-Run Setup

When no existing configuration is found, the skill prompts the user to select a persistence backend. The agent presents the available options:

> **Agent:** "I don't have a memory configuration yet. Which persistence backend would you like to use?
>
> 1. **filesystem** — Store memories in local files (best for local agents like Claude Code)
> 2. **git_cli** — Sync to a Git repository using command-line Git (local agents only)
> 3. **github_api** — Sync to GitHub via REST API (works in cloud and local)
> 4. **manual** — You upload/download memory files each session (simplest, works anywhere)
>
> Which option works best for your environment?"

The user's choice determines the initial configuration. The skill cannot reliably auto-detect whether it's running in a cloud or local environment, so explicit selection ensures the correct backend is used.

## Configuration

### Default Configuration

After the user selects a backend, the skill generates an appropriate configuration. Example for filesystem backend:

```yaml
# config.yaml

persistence:
  backend: filesystem
  filesystem:
    path: ~/.local/share/agent-memory/

backup:
  checkpoint_interval: 5

memory:
  consolidation_threshold: 50
```

Example for github_api backend:

```yaml
# config.yaml

persistence:
  backend: github_api
  github_api:
    repo: username/agent-memory
    path: memories/

backup:
  checkpoint_interval: 5

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
| `manual` | User uploads each session |

### Interactive Configuration

Users can modify configuration through conversation:

> **User:** "Let's set up GitHub persistence"
>
> **Agent:** "I'll configure GitHub as your persistence backend. You'll need:
> 1. A GitHub repo (can be private)
> 2. A Personal Access Token with 'repo' scope
>
> What repository should I use? (e.g., 'username/agent-memory')"
>
> **User:** "fran/my-agent-memory"
>
> **Agent:** "And what's your Personal Access Token? I can store it in config.yaml, or if you prefer, you can set the GITHUB_TOKEN environment variable yourself."
>
> **User:** "ghp_xxxxxxxxxxxx"
>
> **Agent:** *updates config.yaml with repo and token*
>
> "Done. GitHub persistence is configured."

## Memory Schema

### File Structure

Memory is organized in a directory structure following the three-tier model:

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

## user_location
**Current:** Massachusetts

**History:**
- 2025-01-03T00:46:00Z: Massachusetts

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

## Session Lifecycle

### Session Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     Session Start                           │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ Search for config:    │
              │ - env var path        │
              │ - uploaded files      │
              │ - default locations   │
              └───────────┬───────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
          Found                   Not Found
              │                       │
              ▼                       ▼
    ┌─────────────────┐    ┌─────────────────────┐
    │ Load config     │    │ Prompt user to      │
    │ Load core.md    │    │ select backend      │
    │ Load index.md   │    │ Generate config     │
    └────────┬────────┘    └──────────┬──────────┘
             │                        │
             └──────────┬─────────────┘
                        ▼
              ┌─────────────────┐
              │ Session Active  │
              │ (queries parse  │
              │  markdown)      │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    On write     Checkpoint     Session end
         │        interval           │
         ▼             │             ▼
    ┌─────────────┐    │      ┌─────────────────┐
    │ Update      │    │      │ Final save      │
    │ markdown    │    │      │ to backend      │
    │ (atomic)    │    │      └─────────────────┘
    └─────┬───────┘    │
          │            │
          └─────┬──────┘
                ▼
       ┌────────────────┐
       │ Checkpoint to  │
       │ backend        │
       └────────────────┘
```

Backend-specific behaviors:
- **filesystem/git_cli**: Automatic persistence, no user action required
- **github_api**: Automatic sync via REST API
- **manual**: User must download files before session end; agent reminds at natural breakpoints

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

### Checkpoint Strategy

Regardless of backend, the skill implements defensive checkpointing:

- Every N memory writes (configurable, default 5)
- Checkpoints go to `/mnt/user-data/outputs/` with timestamps
- Even if user forgets final download, they lose at most a few updates

## Concurrency Considerations

### Local Agents

Multiple Claude Code sessions may access the same memory store simultaneously. Without a database, file-based locking is required.

**Approach:**
- Use OS-level file locking (`fcntl` on Unix, `msvcrt` on Windows)
- Atomic writes via temp file + rename
- Accept last-write-wins for simplicity (matching cloud behavior)

Best practices for scripts:
- Acquire lock before reading, release after writing
- Keep lock duration minimal
- Use atomic rename for safe file updates

**Trade-offs:**
- Less sophisticated than database concurrency
- May occasionally lose updates if sessions write simultaneously
- Acceptable for typical use (infrequent writes, human-scale interactions)

### Cloud Agents

Each conversation has isolated ephemeral storage—no concurrency concerns within a session. However, if the user has multiple conversations using the same GitHub/Drive backend, conflicts could occur.

Mitigation strategies:
- Last-write-wins for simple cases
- Markdown format allows manual conflict resolution
- Git-based backends preserve both versions in history

## Skill File Structure

```
/mnt/skills/user/stateful-memory/
├── SKILL.md                    # Instructions, identity, behavioral rules
├── scripts/
│   ├── __init__.py
│   ├── initialize.py           # Session startup, config discovery
│   ├── memory.py               # Core memory operations (markdown-native)
│   └── backends/
│       ├── __init__.py
│       ├── base.py             # Abstract backend interface
│       ├── filesystem.py       # Local filesystem backend
│       ├── git_cli.py          # Git CLI backend
│       ├── github_api.py       # GitHub REST API backend
│       └── manual.py           # Manual upload/download backend
└── templates/
    └── config.yaml.template    # Template for generating backend configs
```

## SKILL.md Outline

The skill's instruction file should cover:

1. **Identity & Purpose**
   - What this skill does
   - The three-tier memory model

2. **Session Startup**
   - Run initialization script
   - If no config found, prompt user to select a backend
   - Load or generate configuration
   - Load core.md and index.md into context

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
   - Offer backup to GitHub if configured

6. **User Interactions**
   - How to respond to "what do you remember about X?"
   - How to handle memory corrections
   - Configuration wizard for backend setup

## Open Questions

### Memory Consolidation

1. As memories accumulate, how should old content be consolidated?

   - Automatic summarization after N entries?
   - User-triggered "consolidate memories" command?
   - Tiered aging (recent → summarized → archived)?

### Memory Categories

1. The current design proposes: facts, patterns, episodes, projects, insights. Are these the right categories? Should users be able to define custom categories?

1. ...

### Cross-Session Learning

1. Can the agent observe patterns in its own memory evolution? Tim's Strix does this via journal analysis. Should this skill include similar self-reflection capabilities?

1. If multiple conversation happen concurrently, how will the persistence layer synchronize writes without data loss/corruption?

### Conflict Resolution

When markdown files are edited externally while a session is active, what's the resolution strategy? Current proposal: always re-read files before writing to minimize conflicts, but this deserves more thought.

### Query Performance

Without database indexes, finding a specific memory requires parsing markdown files:

1. For typical memory sizes (hundreds of entries), is direct parsing acceptably fast?

1. Should the skill recommend maximum file sizes or entry counts?

1. Would in-memory caching within a session (dict built on first load) provide meaningful benefit?

### Concurrent Write Handling

File-based storage lacks SQLite's built-in concurrency handling:

1. Is OS-level file locking (`fcntl`/`msvcrt`) sufficient for typical usage?

1. Should the skill simply accept last-write-wins semantics (matching cloud behavior)?

1. How should the skill handle lock acquisition failures?

### Atomic Updates

Partial file writes could corrupt markdown:

1. Is write-to-temp-then-rename sufficient on all target platforms?

1. Should the skill keep checkpoint copies for recovery?

1. How should the skill handle interrupted writes (recoverable from history section)?

### Large Memory Stores

As memories accumulate, file-based operations may become slow:

1. What are reasonable scale limits to document (files, entries, total size)?

1. Should the skill proactively recommend consolidation when thresholds are exceeded?

1. Is splitting into multiple smaller block files preferable to one large file?

## Future Enhancements

- **MCP Memory Server**: For environments that support MCP, expose memory operations as tools
- **Selective Loading**: Smarter retrieval of content blocks based on conversation context
- **Memory Sharing**: Export subsets of memories for sharing between agents or users
- **Encryption**: Optional encryption for sensitive memories (especially on shared backends)

## References

- [claude_life_assistant](https://github.com/lout33/claude_life_assistant) — Luis Fernando's minimal stateful agent
- [Memory Architecture for a Synthetic Being](https://timkellogg.me/blog/2025/12/30/memory-arch) — Tim Kellogg's Strix architecture
- [PEP 723](https://peps.python.org/pep-0723/) — Inline script metadata for self-contained Python scripts
