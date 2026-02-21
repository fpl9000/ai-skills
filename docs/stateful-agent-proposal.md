# Proposal: Claude as a Stateful Agent with Full Local Access

**Version:** 0.1 (Draft)<br/>
**Date:** February 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)

## Contents

- [Executive Summary](#executive-summary)
- [Requirements](#requirements)
- [The Problem: No Single Environment Has Everything](#the-problem-no-single-environment-has-everything)
- [Proposed Architectures](#proposed-architectures)
  - [Architecture A: Claude Code Desktop + Stateful Memory Skill](#architecture-a-claude-code-desktop--stateful-memory-skill)
  - [Architecture B: Local MCP Bridge](#architecture-b-local-mcp-bridge)
    - [Variant B1: Claude Desktop App + Local MCP Bridge (No Tunnel)](#variant-b1-claude-desktop-app--local-mcp-bridge-no-tunnel)
    - [Variant B2: Claude.ai + Local MCP Bridge via Tunnel](#variant-b2-claudeai--local-mcp-bridge-via-tunnel)
  - [Architecture C: Claude Code CLI + Web Terminal UI](#architecture-c-claude-code-cli--web-terminal-ui)
  - [Architecture D: Hybrid — Claude.ai Primary with Local Agent Sidecar](#architecture-d-hybrid--claudeai-primary-with-local-agent-sidecar)
- [Architecture Comparison](#architecture-comparison)
- [Recommendation](#recommendation)
- [Supplementary Memory Strategy](#supplementary-memory-strategy)
  - [The Limitation](#the-limitation-built-in-memory-is-not-enough)
  - [Design Principle: Layered Memory](#design-principle-layered-memory)
  - [Option 1: Tiered Memory via MCP Filesystem Tools](#option-1-tiered-memory-via-mcp-filesystem-tools)
  - [Option 2: Dedicated MCP Memory Server](#option-2-dedicated-mcp-memory-server)
  - [Option 3: Hybrid — Filesystem Core with Search Index](#option-3-hybrid--filesystem-core-with-search-index)
  - [Concurrent Conversation Writes](#concurrent-conversation-writes)
  - [Supplementary Memory Recommendation](#supplementary-memory-recommendation)
- [Sub-Agent Architecture](#sub-agent-architecture)
  - [Design Constraints](#design-constraints)
  - [The spawn_agent Tool](#the-spawn_agent-tool)
  - [Execution Model: Hybrid Sync/Async with Sequential Spawning](#execution-model-hybrid-syncasync-with-sequential-spawning)
  - [Default System Preamble](#default-system-preamble)
  - [Sub-Agent Memory Access](#sub-agent-memory-access)
  - [Relationship to Claude Code's Built-in Memory](#relationship-to-claude-codes-built-in-memory)
  - [Recommended CLAUDE.md Content for Sub-Agents](#recommended-claudemd-content-for-sub-agents)
- [Implementation Roadmap](#implementation-roadmap)
- [Risks and Mitigations](#risks-and-mitigations)
- [Relation to Existing Design](#relation-to-existing-design)
- [Open Questions](#open-questions)

## Executive Summary

The goal is to use Claude — accessed through Anthropic's own UIs rather than a custom harness like LettaBot — as a **stateful agent** with persistent memory, full local system access (filesystem, network, command execution), and a graphical user interface. No single Claude environment currently provides all of these capabilities simultaneously. This proposal evaluates four architectures that bridge the gaps. The chosen architecture is **B1: Claude Desktop App + Local MCP Bridge** — a Go-based MCP bridge server running locally via stdio, providing filesystem, network, and command access to the Claude Desktop App. No tunnel, no cloud dependency for local operations, and a single static binary with no runtime dependencies. **Architecture A** (Claude Code Desktop + Stateful Memory Skill) remains as a fallback that requires no MCP infrastructure at all. **Architecture B2** (Claude.ai + tunnel) is documented as a potential future upgrade if the Desktop App's UI proves insufficient, but is not planned for initial implementation.

Because Anthropic's built-in memory is limited (~500–2,000 tokens — adequate for identity and preferences, but far too small for deep project context, episodic recall, or technical notes), this proposal also defines a **two-layer memory strategy**. Layer 1 is Anthropic's built-in memory (automatic, compact, always present). Layer 2 is a supplementary system using the three-tier markdown memory model from the [existing design document](stateful-agent-skill-design.md), accessed via the MCP bridge's filesystem tools. This layered approach brings Claude closer to the deep memory capabilities of systems like Letta (formerly MemGPT) while maintaining transparency (human-readable markdown files) and portability (Git-backed, no vendor lock-in).

The proposal additionally defines a **sub-agent architecture** for delegating focused tasks to ephemeral Claude Code CLI instances via a `spawn_agent` MCP tool. Sub-agents are one-shot (fire-and-forget), have no memory of their own, and return results to the primary agent for incorporation into the conversation and optional persistence to Layer 2 memory.

## Requirements

| # | Requirement | Description |
|---|-------------|-------------|
| R1 | **Persistent memory** | Knowledge survives across conversations. Includes identity, user facts, episodic memories, and project context. |
| R2 | **Local filesystem access** | Read and write files on the user's local machine (not just a cloud VM). |
| R3 | **Local network access** | Make HTTP requests, call APIs, and reach services running on the local machine or LAN. |
| R4 | **Local command execution** | Run shell commands, scripts, and programs on the user's local machine. |
| R5 | **Graphical UI** | A visual interface with rich text rendering, code highlighting, file previews, and artifact display. A terminal UI (TUI) is acceptable as a fallback. |

## The Problem: No Single Environment Has Everything

Each Claude environment provides a subset of the requirements:

| Capability | Claude.ai (Web) | Claude Desktop App | Claude Code CLI | Claude Code Desktop |
|------------|-----------------|--------------------|-----------------|---------------------|
| **R1: Persistent memory** | ✅ Built-in | ✅ Built-in | ❌ None | ❌ None |
| **R2: Local filesystem** | ❌ Cloud VM only | ✅ Full | ✅ Full | ✅ Full |
| **R3: Local network** | ❌ Cloud VM only | ❌ Cloud VM only | ✅ Full | ✅ Full |
| **R4: Local commands** | ❌ Cloud VM only | ❌ Cloud VM only | ✅ Full | ✅ Full |
| **R5: Graphical UI** | ✅ Rich web UI | ✅ Rich desktop UI | ❌ Terminal only | ✅ GUI wrapper |
| **MCP server support** | ✅ Remote only | ✅ Remote + Local | ✅ Remote + Local | ✅ Remote + Local |
| **Skills support** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |

Key observations:

- **Claude.ai** has the best memory and the best UI, but is completely isolated from the local machine. It supports **remote** MCP servers via the "Connectors" feature (Settings > Connectors), including custom connectors where you provide a remote MCP server URL. However, it cannot connect to **locally-running** MCP servers directly — the server must be reachable over the network.
- **Claude Desktop App** has built-in memory, a rich GUI, and supports both remote and **local** MCP servers (via stdio). Natively, its command execution and network access happen on the cloud VM, but a **local MCP server** can bridge these gaps — providing local filesystem, network, and command access without needing a tunnel. This makes the Desktop App a strong candidate when paired with a local MCP bridge, with the only tradeoff being a slightly less feature-rich UI than Claude.ai (e.g., no cloud VM for code execution/file creation, fewer tool widgets).
- **Claude Code Desktop** has the best local access and has a GUI, but lacks persistent memory and lacks certain rich UI features (artifacts, file previews, tool widgets).
- The **MCP protocol** is the key bridge between Claude's UIs and local machine capabilities. The Claude Desktop App can connect to local MCP servers directly (no tunnel needed). Claude.ai can connect to remote MCP servers, which requires making a local server reachable via a tunnel service (Cloudflare Tunnel, ngrok, or Tailscale Funnel).

The central tension is: **memory and rich UI live in the cloud; local access lives on the user's machine.** The MCP protocol bridges that gap, and every architecture below is a strategy for deploying that bridge.

## Proposed Architectures

### Architecture A: Claude Code Desktop + Stateful Memory Skill

**Strategy:** Use the environment that already has full local access and a GUI, then add the missing piece (persistent memory) via the stateful memory skill described in the [existing design document](stateful-agent-skill-design.md).

```
┌──────────────────────────────────────────────────┐
│            Claude Code Desktop (GUI)             │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │  Stateful Memory Skill                      │ │
│  │  ┌────────┐ ┌────────┐ ┌────────────────┐   │ │
│  │  │Core.md │ │Index.md│ │ blocks/*.md    │   │ │
│  │  └────────┘ └────────┘ └────────────────┘   │ │
│  │         │         │             │           │ │
│  │         └─────────┼─────────────┘           │ │
│  │                   ▼                         │ │
│  │        GitHub API (persistence)             │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  Local filesystem ✅  Local network ✅          │
│  Local commands ✅    GUI ✅ (basic)            │
│  Persistent memory ✅ (via skill)                │
└──────────────────────────────────────────────────┘
```

**How it works:**

1. Claude Code Desktop is launched as the primary interface.
2. On session start, the stateful memory skill loads `core.md` and `index.md` from the local filesystem (or syncs from GitHub).
3. During the conversation, memory updates are written to local markdown files and periodically checkpointed to GitHub.
4. On session end, final state is persisted.
5. The next session starts by loading the latest state, providing continuity.

**Pros:**
- Available today — no waiting on Anthropic feature releases.
- Full local access (filesystem, network, commands) is native.
- Memory skill is under your control and fully transparent (markdown files).
- No cloud VM involved — everything runs locally.
- Skills are loaded at session start, so the memory skill integrates naturally.

**Cons:**
- Claude Code Desktop's GUI is more basic than Claude.ai's. It lacks artifacts, rich tool widgets (maps, weather, recipes), file preview rendering, and other UI features.
- The memory skill consumes context window space. Loading `core.md`, `index.md`, and the skill instructions on every session reduces the available context for actual conversation. This overhead is user-managed and can grow unbounded, unlike Anthropic's built-in memory which is automatically kept compact (~500–800 tokens). (Note: Architecture B also has context overhead from MCP tool definitions and built-in memory injection, but these are fixed and Anthropic-managed costs.)
- Memory quality depends entirely on the skill's prompting and the model's compliance. Anthropic's built-in memory system uses purpose-built infrastructure that may produce higher quality results.
- Each new session requires the skill to "boot up" by reading memory files, which adds latency and cost to the start of every conversation.
- Claude Code Desktop is itself a beta product and may have stability issues.

**Verdict:** This is the **pragmatic choice** available today. It satisfies all five requirements, albeit with a less polished UI and a memory system that is more manual and context-hungry than Anthropic's built-in offering.

---

### Architecture B: Local MCP Bridge

**Strategy:** Run a local MCP server that provides tools for filesystem operations, network requests, and command execution, then connect a Claude UI to it. The same MCP bridge server codebase supports two deployment variants, depending on which Claude UI you prefer.

**The MCP bridge server** is a relatively simple program written in **Go**, compiled to a single static binary with no runtime dependencies. The Go MCP ecosystem (notably [`mark3labs/mcp-go`](https://github.com/mark3labs/mcp-go)) provides the necessary SDK support, and Go's standard library covers all other requirements (filesystem operations, HTTP server, JSON handling, process spawning, concurrency via goroutines). The bridge:

- Exposes tools for filesystem operations (`read_file`, `write_file`, `edit_file`, `append_file`, `list_dir`, `search`), network requests (`http_get`, `http_post`), and command execution (`run_command`, `run_script`). The `edit_file` tool performs surgical find-and-replace edits within a file (Claude specifies the old text and new text; the bridge handles the read-modify-write), avoiding full-file rewrites for small changes to structured memory files like `core.md` or project blocks. The `append_file` tool supports the append-only pattern used for episodic memory logs and other accumulative content (see [Concurrent Conversation Writes](#concurrent-conversation-writes)).
- Implements a configurable allowlist of permitted directories, commands, and network destinations (for security).
- Logs all operations for auditability.
- Supports **both** stdio transport (for the Desktop App) and Streamable HTTP transport (for Claude.ai), so a single codebase serves both variants.

#### Variant B1: Claude Desktop App + Local MCP Bridge (No Tunnel)

```
┌─────────────────────────────────────────────────────────────┐
│              Claude Desktop App (GUI)                       │
│                                                             │
│  Built-in memory ✅    Rich UI ✅    Skills ✅             │
│  Local MCP ✅ (stdio)                                       │
│                                                             │
│           │  MCP Protocol (stdio — local, no tunnel)        │
│           ▼                                                 │
│  ┌──────────────────────────────────────────────────┐       │
│  │        Local MCP Bridge Server                   │       │
│  │        (launched as subprocess by Desktop App)   │       │
│  │                                                  │       │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │       │
│  │  │Filesystem│  │ Network  │  │Command Exec   │   │       │
│  │  │  Tools   │  │  Tools   │  │   Tools       │   │       │
│  │  └──────────┘  └──────────┘  └───────────────┘   │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Local filesystem ✅  Local network ✅  Local commands ✅  │
└─────────────────────────────────────────────────────────────┘
```

**How B1 works:**

1. The MCP bridge server is registered in the Claude Desktop App's MCP configuration file (`claude_desktop_config.json`).
2. The Desktop App launches the bridge server as a local subprocess using stdio transport — no network exposure, no tunnel.
3. Claude uses the bridge's tools to perform local filesystem, network, and command operations.
4. The Desktop App's built-in memory system handles persistence automatically.
5. Skills are uploaded as .zip files via Settings > Capabilities and work normally.

**B1 Pros:**
- **No tunnel required** — the MCP bridge runs locally via stdio. No network exposure, no public URL, no tunnel service dependency.
- Built-in memory — Anthropic's memory system, which manages memory budget automatically. Built-in memory is still injected into the context window, but Anthropic controls its size (typically a compact summary of ~500–800 tokens), unlike a skill-based approach where memory files can grow unbounded.
- Rich GUI — not quite Claude.ai-grade, but has artifacts, file handling, and most UI features.
- Skills support — custom skills can be uploaded and used alongside the MCP bridge.
- Simplest setup of any Architecture B variant — just configure the Desktop App's MCP settings and point it at the bridge server binary.
- Lowest security surface — the bridge is only accessible to the Desktop App process, not to the network.

**B1 Cons:**
- The Desktop App's UI is slightly less feature-rich than Claude.ai. It lacks the cloud VM for code execution/file creation (though the MCP bridge can provide equivalent local functionality), and may lack some of Claude.ai's specialized tool widgets.
- The Desktop App has reported stability issues (crashes related to connectors/extensions). These may improve over time as the app matures.
- The Desktop App is available on macOS and Windows, but may have platform-specific quirks.

**B1 Verdict:** This is the **simplest and most self-contained** variant of Architecture B. It satisfies all five requirements with minimal infrastructure — no tunnel, no cloud dependency for local operations, and lower context window overhead than a skill-based approach (Anthropic manages memory compactness). The only tradeoff is a slightly less polished UI compared to Claude.ai.

#### Variant B2: Claude.ai + Local MCP Bridge via Tunnel

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude.ai (Web UI)                      │
│                                                             │
│  Built-in memory ✅    Rich UI ✅    Artifacts ✅          │
│  Tool widgets ✅       File previews ✅                    │
│                                                             │
│           │  MCP Protocol (Streamable HTTP)                 │
│           ▼                                                 │
│  ┌──────────────────────────────────────────────────┐       │
│  │  Secure Tunnel (Cloudflare/ngrok/Tailscale)      │       │
│  └──────────────────────────────────────────────────┘       │
│           │                                                 │
└───────────┼─────────────────────────────────────────────────┘
            │
┌───────────┼──────────────────────────────────────────────────┐
│           ▼                                                  │
│  ┌──────────────────────────────────────────────────┐        │
│  │        Local MCP Bridge Server                   │        │
│  │        (long-running daemon)                     │        │
│  │                                                  │        │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │        │
│  │  │Filesystem│  │ Network  │  │Command Exec   │   │        │
│  │  │  Tools   │  │  Tools   │  │   Tools       │   │        │
│  │  └──────────┘  └──────────┘  └───────────────┘   │        │
│  └──────────────────────────────────────────────────┘        │
│                                                              │
│  User's Local Machine                                        │
│  Local filesystem ✅  Local network ✅  Local commands ✅   │
└──────────────────────────────────────────────────────────────┘
```

**How B2 works:**

1. The same MCP bridge server runs on the user's local machine as a long-lived background process (daemon/service), but using Streamable HTTP transport instead of stdio.
2. A secure tunnel service (Cloudflare Tunnel, ngrok, or Tailscale Funnel) makes the bridge reachable at a stable public URL.
3. The user adds this URL as a custom connector in Claude.ai (Settings > Connectors > Add custom connector). This only needs to be done once.
4. Claude uses the bridge's tools just as it uses any other connector tool — making tool calls that are routed through the tunnel to the local bridge.
5. Claude.ai's built-in memory system handles persistence automatically.

**B2 Pros:**
- Best possible UI — Claude.ai's full web interface with artifacts, widgets, cloud VM code execution, and rich rendering.
- Best possible memory — Anthropic's built-in memory system.
- Same MCP bridge codebase as B1 — just a different transport layer.
- Optionally supports OAuth 2.1 authentication for access control.

**B2 Cons:**
- Requires a tunnel service, which adds operational complexity and a reliability dependency.
- Latency — typically 50–200ms round-trip through a tunnel vs. near-zero for B1's stdio.
- Larger security surface — the bridge is reachable from the internet (though protected by tunnel auth and application-level allowlists).
- Tunnel services may have their own rate-limiting, cost, or uptime considerations.

**B2 Verdict:** This is the **premium variant** — it provides the best possible UI and memory at the cost of tunnel complexity. It is the right choice if Claude.ai's UI advantages (cloud VM, tool widgets, etc.) are important to your workflow, and the tunnel proves reliable.

#### Architecture B: Shared Pros

- Clean separation of concerns: Claude handles reasoning and conversation; the MCP bridge handles local access.
- The MCP bridge is a general-purpose tool — once built, it benefits all MCP-compatible AI agents, not just Claude.
- Lower context window overhead than Architecture A. Built-in memory is still injected into context, but Anthropic manages its size (typically ~500–800 tokens of compact summary). The skill-based approach in Architecture A loads user-managed markdown files whose size can grow unbounded. Note that MCP tool definitions also consume context (roughly 200–500 tokens per tool), but this is a fixed, predictable cost that does not grow over time.
- The bridge server can be hardened with allowlists and logging, providing a security boundary.
- A single codebase supports both variants, so you can switch between B1 and B2 at will.

#### Architecture B: Overall Verdict

Architecture B is the **recommended approach**. Start with **B1** (Desktop App, no tunnel) for simplicity, and upgrade to **B2** (Claude.ai, with tunnel) if you need Claude.ai's superior UI features or if the Desktop App's stability proves insufficient. Both variants are achievable today.

---

### Architecture C: Claude Code CLI + Web Terminal UI

**Strategy:** Use Claude Code CLI for its full local access and skills support, but replace the raw terminal with a web-based terminal UI for a better visual experience.

```
┌─────────────────────────────────────────────────────────┐
│              Web Browser (localhost:8080)               │
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Web Terminal UI                                   │ │
│  │  (e.g., ttyd, xterm.js, custom React app)          │ │
│  │                                                    │ │
│  │  Features:                                         │ │
│  │  - Rich text / Markdown rendering                  │ │
│  │  - Syntax-highlighted code blocks                  │ │
│  │  - Scrollback with search                          │ │
│  │  - Session history sidebar                         │ │
│  │  - Copy-paste with formatting                      │ │
│  │  └─────────────────────────────────────────────┘   │ │
│  │              │                                     │ │
│  │              │  stdin/stdout                       │ │
│  │              ▼                                     │ │
│  │  ┌─────────────────────────────────────────────┐   │ │
│  │  │  Claude Code CLI                            │   │ │
│  │  │  + Stateful Memory Skill                    │   │ │
│  │  │                                             │   │ │
│  │  │  Local filesystem ✅  Local network ✅     │   | │
│  │  │  Local commands ✅    Memory ✅ (skill)    │   | │
│  │  └─────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────┘ │
│                                                         │
│  GUI ⚠️ (terminal-grade, not Claude.ai-grade)          │
└─────────────────────────────────────────────────────────┘
```

**How it works:**

1. Claude Code CLI runs as a subprocess behind a web-based terminal emulator.
2. The web terminal renders Claude's Markdown output with syntax highlighting and rich formatting.
3. The stateful memory skill provides persistence (same as Architecture A).
4. The user interacts via a browser tab at `localhost:8080`.

**Candidate web terminal tools:**

| Tool | Description | Effort |
|------|-------------|--------|
| **[ttyd](https://github.com/nicehash/ttyd)** | Share terminal over web. Zero-config, but renders as a raw terminal — no markdown rendering. | Minimal |
| **Custom React app with xterm.js** | A purpose-built web UI that wraps Claude Code's output, parsing markdown and rendering it richly. Could include a sidebar for session history, memory inspector, etc. | Significant |
| **[Textual](https://textual.textualize.io/) TUI** | A Python-based rich terminal UI framework. Could build a dedicated Claude Code frontend with panels, markdown rendering, and scrollback. | Moderate |

**Pros:**
- Full local access (inherits everything from Claude Code CLI).
- Could build a highly customized UI tailored to your workflow.
- No dependency on Anthropic's UI development timeline.
- A custom web UI could integrate a memory inspector panel, showing current memory state alongside the conversation.

**Cons:**
- Significant development effort if you want anything beyond a raw terminal. A custom React app is a non-trivial project to build and maintain.
- Even a good web terminal UI will not match Claude.ai's native features (artifacts, tool widgets, drag-and-drop file handling, etc.).
- You are now maintaining a UI in addition to the memory skill — two pieces of custom infrastructure.
- ttyd and similar tools are "thin" wrappers — they give you a terminal in a browser, but the experience is still fundamentally terminal-grade.

**Verdict:** This is the **DIY option**. It is technically feasible and offers maximum control, but the development and maintenance cost is high relative to the benefit. It makes most sense if you enjoy building custom tools and want a project to work on. For most users, it is not the best use of time.

---

### Architecture D: Hybrid — Claude.ai Primary with Local Agent Sidecar

**Strategy:** Use Claude.ai as the primary conversational interface (for its UI and memory), and run a local Claude Code agent as a "sidecar" that handles local operations on demand.

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  ┌─────────────────────────┐    ┌───────────────────────────┐  │
│  │  Claude.ai (Web UI)     │    │ Local Sidecar Agent       │  │
│  │                         │    │ (Claude Code CLI)         │  │
│  │  Primary conversation   │    │                           │  │
│  │  Built-in memory        │◄──►│  Local filesystem         │  │
│  │  Rich UI                │    │  Local network            │  │
│  │  Artifacts              │    │  Local commands           │  │
│  │                         │    │  Stateful Memory Skill    │  │
│  │  When local access is   │    │                           │  │
│  │  needed, instructs user │    │  Runs tasks, returns      │  │
│  │  or sidecar agent.      │    │  results to clipboard or  │  │
│  │                         │    │  shared file location.    │  │
│  └─────────────────────────┘    └───────────────────────────┘  │
│           │                              │                     │
│           └──────── Coordination ────────┘                     │
│           (manual copy-paste, shared files,                    │
│            or automated via MCP/webhook)                       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**How it works:**

1. The user's primary conversation happens in Claude.ai's web UI.
2. When a task requires local access, the user switches to a local Claude Code session (running in a terminal or Claude Code Desktop) to execute the local portion.
3. Results are transferred back to the Claude.ai conversation via copy-paste, file upload, or (if automated) a shared coordination mechanism.
4. Note: If you build an MCP bridge for automated coordination, you have effectively implemented Architecture B, which supersedes this approach.

**Coordination mechanisms (from manual to automated):**

| Mechanism | Effort | Seamlessness |
|-----------|--------|--------------|
| **Copy-paste** | None | Low — manual context-switching |
| **Shared filesystem** (e.g., Dropbox/OneDrive folder) | Minimal | Medium — Claude.ai can read uploaded files |
| **GitHub as intermediary** | Minimal | Medium — both agents can access GitHub |
| **Local webhook/API** | Moderate | High — Claude.ai triggers local work via API call |
| **MCP bridge** (available now) | Moderate | Highest — native tool integration |

**Pros:**
- Uses the best UI (Claude.ai) and the best memory (built-in) for the primary conversation.
- Local access is available when needed, without compromising the primary experience.
- Gradual migration path: starts manual, can become fully automated by adopting Architecture B's MCP bridge.
- The sidecar agent can be specialized — loaded with skills for local operations, while the primary agent focuses on conversation and reasoning.

**Cons:**
- Context-switching between two interfaces is friction-heavy and error-prone.
- The two agents do not share context automatically. The Claude.ai agent and the local agent are separate conversations with separate memories.
- Manual coordination (copy-paste) is tedious for frequent local operations.
- Even with automated coordination, there is inherent latency and complexity in a two-agent system.
- The user must maintain two mental models of what each agent knows.

**Verdict:** This is a **transitional architecture** — useful if you primarily need Claude.ai's UI and memory, and only occasionally need local access. Note that the MCP bridge coordination mechanism listed above is now achievable (see Architecture B), which largely supersedes this architecture. Architecture D remains relevant only if you want to avoid building or running an MCP bridge server at all, accepting manual coordination as the tradeoff.

## Architecture Comparison

| Criterion | A: CC Desktop + Skill | B1: Desktop App + MCP | B2: Claude.ai + MCP | C: CLI + Web UI | D: Hybrid Sidecar |
|-----------|----------------------|----------------------|--------------------|-----------------|-------------------|
| **Available today** | ✅ Yes | ✅ Yes (needs MCP bridge) | ✅ Yes (needs MCP bridge + tunnel) | ⚠️ Requires dev work | ✅ Yes (manual) |
| **R1: Persistent memory** | ⚠️ Skill-based | ✅ Built-in | ✅ Built-in | ⚠️ Skill-based | ✅ Built-in (primary) |
| **R2: Local filesystem** | ✅ Native | ✅ Via MCP | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R3: Local network** | ✅ Native | ✅ Via MCP | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R4: Local commands** | ✅ Native | ✅ Via MCP | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R5: Graphical UI** | ⚠️ Basic GUI | ✅ Rich (near Claude.ai) | ✅ Best-in-class | ⚠️ Terminal-grade | ✅ Best-in-class |
| **Context window cost** | ⚠️ High (skill + memory files) | ⚠️ Low (built-in memory + MCP tools) | ⚠️ Low (built-in memory + MCP tools) | ⚠️ High (skill + memory files) | ⚠️ Low (built-in memory) |
| **Setup complexity** | Low | Low–Moderate | Moderate | High | Low–Moderate |
| **Maintenance burden** | Low | Low | Low–Moderate | High | Moderate |
| **Tunnel required** | No | No | Yes | No | No |
| **Future-proof** | ⚠️ May be superseded | ✅ Aligned with Anthropic's direction | ✅ Aligned with Anthropic's direction | ❌ Custom dead-end | ⚠️ Largely superseded by B |

## Recommendation

### Chosen Architecture: B1 (Claude Desktop App + Local MCP Bridge)

**Build a local MCP bridge server in Go and connect it to the Claude Desktop App via stdio.**

This is the chosen architecture for implementation. It is the simplest path to satisfying all five requirements. The Claude Desktop App provides built-in memory and a rich GUI. A local MCP bridge server provides local filesystem, network, and command access. No tunnel is needed — the Desktop App launches the bridge as a local subprocess.

Specific actions:

1. **Build the local MCP bridge server** in Go using the `mark3labs/mcp-go` SDK. Implement stdio transport with tools for filesystem operations, network requests, and command execution. The result is a single static binary with no runtime dependencies — no Node.js, no Python, no installation steps beyond copying the binary.
2. **Register the bridge** in the Desktop App's MCP configuration file (`claude_desktop_config.json`).
3. **Implement security controls**: directory allowlists, command allowlists, and operation logging.
4. **Test and iterate** on the tool set — start with filesystem and command execution, then add network tools as needed.

### Potential Future Upgrade: Architecture B2

**Not planned for initial implementation.** If the Desktop App's UI limitations or stability issues become frustrating, B2 remains available as an upgrade path — add a tunnel and switch to Claude.ai.

The same MCP bridge codebase supports both stdio (B1) and Streamable HTTP (B2) transports. The upgrade steps would be:

1. **Add Streamable HTTP transport** to the bridge (or enable it if already built with dual-transport support).
2. **Configure a secure tunnel** (Cloudflare Tunnel is recommended for stability and zero-cost for personal use; ngrok or Tailscale Funnel are alternatives) to expose the bridge at a stable URL.
3. **Add the tunnel URL as a custom connector** in Claude.ai (Settings > Connectors > Add custom connector).
4. **Optionally add OAuth 2.1 authentication** for access control.

This gives you Claude.ai's best-in-class UI and tool widgets while keeping the same bridge and tools.

### Fallback Strategy: Architecture A

**If the MCP bridge approach proves unworkable for any reason, fall back to Claude Code Desktop with the Stateful Memory Skill.**

Architecture A requires no MCP infrastructure at all. It works entirely locally using native Claude Code Desktop capabilities plus the stateful memory skill. It is the simplest to set up but has a less polished UI and requires the memory skill to consume context window space.

Specific actions:

1. **Implement the stateful memory skill** with the `filesystem` backend for local persistence and `github_api` backend for backup/sync.
2. **Configure Claude Code Desktop** with the skill loaded on startup.
3. **Establish a GitHub repo** (e.g., `fpl9000/agent-memory`) for memory persistence and version history.

### Long-term (6–12 months): Simplification

Anthropic is actively developing memory, MCP, and tool integration features (including MCP Apps for interactive in-conversation UIs, announced January 2026). The long-term trajectory is that the MCP bridge server becomes the only piece of custom infrastructure — a clean, maintainable, general-purpose tool. As the Desktop App's UI matures and converges with Claude.ai, the gap between B1 and B2 will narrow, potentially eliminating the need for the tunnel altogether. As Anthropic's built-in memory improves (potentially increasing Layer 1 capacity for structured project context, episodic recall, and search), the Layer 2 supplementary memory system may eventually become unnecessary — but the markdown files will remain as a portable archive regardless. See the [Supplementary Memory Strategy](#supplementary-memory-strategy) section for the detailed design of the two-layer memory approach.

## Supplementary Memory Strategy

### The Limitation: Built-in Memory Is Not Enough

Anthropic's built-in memory system (available in Claude.ai and the Claude Desktop App) is designed to store a compact summary of user identity, preferences, and high-level project context. Based on observation, the memory summary injected into context is roughly **500–2,000 tokens** — approximately 500 words or ~4,000 characters. Anthropic does not publicly document a hard limit, but the system is clearly designed to keep the summary small, since it is injected into the system prompt on every conversation turn.

This is adequate for "who am I talking to?" context — the user's name, role, communication preferences, and active projects. But it is far too small for the kind of deep, structured, project-aware memory that systems like **Letta** (formerly MemGPT) provide. Letta's architecture supports essentially unlimited structured memory with semantic search, episodic recall, and multi-tier storage. For Claude to function as a comparable stateful agent, we need a **supplementary memory layer** that works alongside the built-in memory.

This supplementary layer is especially important for:

- **Project context** — architectural decisions, design rationale, implementation status, open issues, and technical debt across multiple active projects.
- **Episodic memory** — what happened in past conversations, what was decided, what was tried and abandoned, and why.
- **Technical notes** — detailed reference material (API patterns, code conventions, environment configurations) that the user shouldn't have to re-explain each session.
- **Long-term goals and plans** — roadmaps, milestones, and evolving strategies that span weeks or months.

### Design Principle: Layered Memory

The recommended approach is a **two-layer memory system**:

| Layer | Provider | Storage | Capacity | Loaded When | Purpose |
|-------|----------|---------|----------|-------------|--------|
| **Layer 1: Identity & Preferences** | Anthropic's built-in memory | Cloud (opaque) | ~500–2,000 tokens | Every turn (automatic) | User identity, communication style, role, high-level project list |
| **Layer 2: Deep Context** | Supplementary system (via MCP) | Local filesystem (+ optional GitHub backup) | Unbounded (loaded on demand) | On request or at session start | Project details, episodic memories, technical notes, decision history |

Layer 1 is always present and requires no user effort — Anthropic maintains it automatically. Layer 2 is opt-in and managed by Claude via the MCP bridge's tools, guided by a skill that teaches Claude the memory structure and lifecycle.

The key insight is that **Layer 2 content does not need to be loaded all at once**. The three-tier model from the [existing design document](stateful-agent-skill-design.md) — core summary, index, and on-demand content blocks — is designed precisely for this. Claude loads only the core summary and index at session start (a bounded cost), then retrieves specific content blocks as needed during the conversation.

### Option 1: Tiered Memory via MCP Filesystem Tools

**Strategy:** Store the three-tier memory structure (from the existing design document) as markdown files on the local filesystem, and access them via the MCP bridge's existing filesystem tools (`read_file`, `write_file`, `edit_file`, `append_file`, `list_dir`, `search_files`). A Claude skill (.zip) provides the instructions that teach Claude how to manage the memory lifecycle.

```
Local Filesystem:
~/.claude-agent-memory/
├── core.md              # Identity, active projects, key facts (~500–1,000 tokens)
├── index.md             # Topic index with one-line summaries + block references
└── blocks/
    ├── project-foo.md   # Deep context for Project Foo
    ├── project-bar.md   # Deep context for Project Bar
    ├── decisions.md     # Key decisions and rationale
    ├── episodic-2026-02.md  # What happened in Feb 2026
    └── ...              # Additional blocks as needed
```

**Session lifecycle:**

1. **Session start:** The skill instructs Claude to read `core.md` and `index.md` via the MCP bridge. These are small, bounded files (~500–1,000 tokens each) that give Claude a high-level picture of who the user is and what topics are available.
2. **During conversation:** When a topic comes up that matches an index entry, Claude reads the relevant content block on demand. Only the needed block is loaded, not the entire memory store.
3. **Session end (or periodically):** Claude updates `core.md`, `index.md`, and any modified content blocks via the MCP bridge's `write_file` tool. New topics get new blocks; existing blocks are updated or summarized.
4. **Backup (optional):** A background script or cron job periodically commits the memory directory to a GitHub repo for versioning and backup.

**Pros:**
- No new infrastructure — uses the same MCP bridge filesystem tools already built for Architecture B.
- Fully transparent — all memory is human-readable markdown files editable with any text editor.
- Works identically with both B1 (Desktop App) and B2 (Claude.ai).
- The three-tier structure (core/index/blocks) bounds the per-session context cost while allowing unbounded total storage.
- Versioning via Git/GitHub provides complete history and rollback.

**Cons:**
- Retrieval is keyword/filename-based, not semantic. Claude must scan the index to decide which block to load, which works for a moderate number of blocks but may degrade as the memory grows to hundreds of topics.
- Memory quality depends on Claude's compliance with the skill's instructions for updating files. The model may forget to persist changes or may summarize poorly.
- The skill instructions themselves consume context (~200–500 tokens), adding to the per-session overhead.

### Option 2: Dedicated MCP Memory Server

**Strategy:** Build (or adopt) a separate MCP server specifically designed for memory operations — semantic search, structured CRUD, and automatic summarization. This server runs alongside the general-purpose MCP bridge (or as additional tools within it).

```
MCP Memory Server Tools:
├── memory_search(query, top_k)       # Semantic or full-text search over all memories
├── memory_read(topic_id)             # Retrieve a specific memory block
├── memory_write(topic_id, content)   # Create or update a memory block
├── memory_list(category?)            # List available topics, optionally filtered
├── memory_summarize(topic_id)        # Trigger summarization of a block
└── memory_delete(topic_id)           # Remove a memory block

Backend Storage:
├── SQLite + FTS5 (full-text search)   # Simple, local, no external dependencies
├── ── or ──
└── SQLite + vector embeddings         # Semantic search via local embedding model
```

**How it works:**

1. The memory server exposes MCP tools that Claude calls just like any other tool.
2. On session start, Claude calls `memory_search("active projects")` or `memory_list()` to get an overview of what's in memory — analogous to reading `core.md` + `index.md`, but with search.
3. During conversation, Claude calls `memory_search(query)` to find relevant context, and `memory_read(topic_id)` to load specific blocks.
4. Claude calls `memory_write()` to persist new information.
5. The server can optionally run background summarization (e.g., compressing old episodic entries).

**Backend options:**

| Backend | Search Type | Complexity | Dependencies |
|---------|------------|------------|-------------|
| **SQLite + FTS5** | Full-text keyword search | Low | None (SQLite is built-in everywhere) |
| **SQLite + vector embeddings** | Semantic similarity search | Medium | Local embedding model (e.g., `all-MiniLM-L6-v2` via `sentence-transformers`) |
| **Existing MCP memory servers** | Varies | Low (if pre-built) | NPM/Python packages (e.g., `@modelcontextprotocol/server-memory`) |

**Pros:**
- Semantic or full-text search scales much better than filename-based retrieval. Claude can find relevant memories even when it doesn't know the exact topic name.
- Structured API — memory operations are explicit tool calls, not ad-hoc file reads. This makes it easier to enforce consistency and logging.
- The server can handle background tasks (summarization, deduplication, archival) that would be awkward to do via filesystem operations alone.
- Existing open-source MCP memory servers (e.g., the `@modelcontextprotocol/server-memory` package) provide a starting point.

**Cons:**
- More infrastructure to build and maintain — a dedicated memory server is a non-trivial project, especially if semantic search is desired.
- Adds MCP tool definitions to context (each tool ~200–500 tokens), increasing the fixed per-session overhead.
- Less transparent than plain markdown files — the user can't just open a text editor to review or correct memories (though a CLI or web UI could be built).
- If using vector embeddings, requires a local embedding model, which has its own resource requirements.

### Option 3: Hybrid — Filesystem Core with Search Index

**Strategy:** Combine the transparency of Option 1 with the search capability of Option 2. Store memories as markdown files (human-readable, Git-friendly), but maintain a search index alongside them.

```
~/.claude-agent-memory/
├── core.md              # Always loaded at session start
├── index.md             # Human-readable topic index
├── blocks/              # Markdown content blocks (same as Option 1)
│   ├── project-foo.md
│   ├── decisions.md
│   └── ...
└── .search-index.db     # SQLite FTS5 index over block contents
```

**How it works:**

1. The MCP bridge (or a thin wrapper) provides both filesystem tools and a `memory_search(query)` tool.
2. The search tool queries the SQLite FTS5 index and returns ranked snippets with block filenames.
3. Claude uses the search results to decide which blocks to read in full via `read_file`.
4. When Claude writes or updates a block via `write_file`, a filesystem watcher or post-write hook updates the search index.
5. The markdown files remain the source of truth — the search index is a derived artifact that can be rebuilt from the files at any time.

**Pros:**
- Best of both worlds: human-readable markdown files + fast search retrieval.
- The search index is a derived artifact, not the source of truth. If it gets corrupted, rebuild it from the markdown files.
- Git-friendly — the markdown files can be committed to GitHub; the `.search-index.db` goes in `.gitignore`.
- Minimal additional infrastructure — SQLite FTS5 requires no external dependencies.

**Cons:**
- Slightly more complex than Option 1 (need to maintain the search index).
- Full-text search is not semantic search. It finds keyword matches, not conceptual similarities. (Could be upgraded to vector search later if needed.)
- The post-write indexing hook adds a small amount of complexity to the MCP bridge.

### Concurrent Conversation Writes

A subtle but important issue arises when **multiple conversations are active simultaneously** and both attempt to update the supplementary memory. This can happen when you have two Claude windows open (e.g., a Desktop App session and a Claude.ai session, or two Desktop App windows), or even when a long-running conversation overlaps with a quick one.

**The problem is not torn writes** — a mutex or file lock in the MCP bridge can prevent two writes from interleaving at the byte level. The problem is **semantic divergence**: each conversation loads memory files at session start, works with a stale snapshot while the other conversation evolves, and then writes back its version of the files. The second write may silently overwrite changes from the first.

**Severity depends on the overlap pattern:**

| Scenario | Conflict Risk | Impact |
|----------|--------------|--------|
| **Non-overlapping topics** — Conversation A discusses Project Foo, Conversation B discusses Project Bar | Low | Content blocks are separate files (`blocks/project-foo.md` vs. `blocks/project-bar.md`). The only shared files are `core.md` and `index.md`, which are summaries — a later write that includes both projects' status is a superset of the earlier write. Minor information loss is possible if one conversation's `core.md` update overwrites the other's before it has learned about the other's changes. |
| **Overlapping topics** — Both conversations discuss the same project | High | Both conversations load the same `blocks/project-foo.md` at session start, make independent changes, and write back their version. The second write clobbers the first, potentially losing decisions, context, or corrections from the other conversation. |
| **Sequential with gap** — One conversation ends before the other starts | None | No conflict. The second conversation loads the first's final state. This is the common case for a single user. |
| **Sequential with overlap** — One conversation is idle (no writes) while the other is active | Very Low | The idle conversation's stale snapshot only matters if it writes again later. If it does, it may overwrite the active conversation's changes to shared files. |

**The `core.md` and `index.md` problem is the most common risk.** These files are updated by every conversation (they are global summaries). If Conversation A adds a new topic to the index and Conversation B doesn't know about it, B's next index write will lose A's new entry.

**Mitigation strategies (from simplest to most complex):**

1. **Operational discipline (recommended for now):** Avoid running memory-intensive conversations in parallel. For most single-user scenarios, this is natural — you focus on one conversation at a time, and the other is idle. The memory skill should include an instruction: *"Before writing to core.md or index.md, re-read the current version from disk to incorporate any changes made by other sessions since you last loaded it."* This "read-before-write" pattern dramatically reduces the stale snapshot window.

2. **Append-only episodic logs:** For episodic memory (`blocks/episodic-*.md`), use an append-only pattern rather than overwriting. Each conversation appends a timestamped entry to the current month's episodic file. Appends from concurrent conversations interleave harmlessly (each entry is self-contained). The MCP bridge can implement this as an `append_file` tool or by reading, appending, and writing atomically under a lock.

3. **Per-conversation session files with background merge:** Instead of writing directly to `core.md` and `index.md`, each conversation writes to a session-scoped file (e.g., `sessions/session-<id>.md`) containing its proposed updates. A background process (cron job or filesystem watcher) periodically merges session files into the canonical `core.md` and `index.md`, resolving conflicts by taking the union of changes. This is more complex but eliminates the "second write clobbers first" problem entirely.

4. **Git-based merge:** Each conversation commits its changes to a Git branch. A background process merges branches into `main`, using Git's merge machinery (or a simple "accept both" strategy for independent line changes). This leverages Git's conflict detection and provides full audit trails. It requires the MCP bridge to support Git operations or a background script that watches for changes and commits them.

5. **Move to Option 2 (dedicated memory server):** A dedicated MCP memory server can handle concurrent writes at the application level — e.g., by accepting fine-grained updates ("add this fact to Project Foo's block") rather than full-file overwrites. This is the cleanest solution but requires the most infrastructure.

**Recommendation:** Start with strategy 1 (operational discipline + read-before-write) and strategy 2 (append-only episodic logs). These are sufficient for a single user who occasionally has overlapping conversations. If concurrent writes become a recurring problem in practice, upgrade to strategy 3 (session files with background merge) or strategy 4 (Git-based merge). Strategy 5 is a natural consequence of upgrading to Option 2, which is already on the deferred roadmap.

### Supplementary Memory Recommendation

**Start with Option 1 (filesystem-only), plan for Option 3 (filesystem + search index).**

Option 1 requires no new infrastructure beyond the MCP bridge already being built for Architecture B. The three-tier markdown structure is proven (described in the existing design document), transparent, and easy to debug. It is sufficient for a moderate number of topics (perhaps 20–50 content blocks), which is likely adequate for the first several months of use.

If the memory grows to the point where keyword/filename-based retrieval becomes cumbersome (hundreds of blocks), add the SQLite FTS5 search index (Option 3). This is a relatively small upgrade — a single `memory_search` tool added to the MCP bridge, plus a post-write indexing hook.

Option 2 (dedicated MCP memory server) is the most powerful but also the most complex. It makes sense if you want to build a general-purpose memory infrastructure for multiple AI agents, or if semantic search proves essential. Defer this unless the simpler options prove insufficient.

**How this works with Architecture B:**

- In **B1** (Desktop App): The memory files live on the local filesystem. Claude accesses them via the MCP bridge's filesystem tools (stdio). The skill (.zip) provides the memory management instructions. Anthropic's built-in memory handles Layer 1 (identity/preferences) automatically.
- In **B2** (Claude.ai): Identical, except the MCP bridge is accessed via tunnel. The memory files still live on the local filesystem.
- In **Architecture A** (fallback): The same memory files are accessed directly by Claude Code Desktop's native filesystem access, guided by the same skill. No MCP bridge needed.

**Comparison with Letta:**

| Capability | Letta (MemGPT) | Proposed Supplementary Memory |
|-----------|---------------|------------------------------|
| **Core memory** (identity, key facts) | ✅ In-context, bounded | ✅ `core.md` (~500–1,000 tokens) + Anthropic built-in |
| **Archival memory** (long-term storage) | ✅ Vector DB, semantic search | ✅ Markdown blocks + FTS5 search (Option 3) |
| **Recall memory** (conversation history) | ✅ Automatic, searchable | ⚠️ Depends on Claude's built-in chat search + episodic blocks |
| **Automatic memory management** | ✅ Agent-managed (model decides what to store) | ⚠️ Skill-guided (model follows instructions, but compliance varies) |
| **Transparency** | ⚠️ DB-backed, requires tools to inspect | ✅ Human-readable markdown, editable with any text editor |
| **Semantic search** | ✅ Native | ❌ Not in Options 1/3 (upgrade path: add embeddings) |
| **Self-hosted, no vendor lock-in** | ✅ Open source | ✅ Plain files + open-source tools |

The proposed system is less automated than Letta (Claude must be instructed to manage memory, while Letta's agent does it autonomously) and lacks semantic search out of the box. But it is simpler, more transparent, and integrates naturally with Architecture B's MCP bridge without requiring a separate agent framework.

## Sub-Agent Architecture

The primary design focuses on a single Claude conversation interacting with the local machine via the MCP bridge. But some workflows benefit from **delegating focused tasks to sub-agents** — ephemeral Claude instances that perform a specific job and return the result. For example, the primary conversation might spawn a sub-agent to search a codebase for a pattern, review a document for errors, or run a test suite and summarize the results, all without leaving the main conversation flow.

### Design Constraints

The sub-agent design follows these principles:

1. **One-shot execution.** Each sub-agent receives a task, performs it, and terminates. It does not maintain an ongoing dialogue with the user or the primary agent. If it cannot complete the task, it returns a response explaining what additional information is needed — and the primary agent decides whether to retry with more context.

2. **No memory of its own.** Sub-agents do not have Layer 1 memory (they are invoked via Claude Code CLI, which does not receive Anthropic's built-in memory injection) and do not write to Layer 2 memory. They are stateless workers. The primary agent is the sole writer to the supplementary memory store, preserving the concurrency model described in [Concurrent Conversation Writes](#concurrent-conversation-writes).

3. **Read-only access to Layer 2 (optional).** Sub-agents *may* read Layer 2 memory files for context (e.g., to understand a project's architecture before reviewing its code), but they never write to them. The primary agent controls what context to provide — either by passing it inline in the task prompt, or by instructing the sub-agent to read specific files from `~/.claude-agent-memory/`.

4. **Full local access via native Claude Code capabilities.** Sub-agents are invoked via `claude -p` (Claude Code CLI in pipe/prompt mode), which natively provides filesystem access, command execution, and network access. They do **not** go through the MCP bridge — they run directly on the local machine as Claude Code processes. This means sub-agents have the same local access as Architecture A, with no MCP overhead.

5. **Scoped and sandboxed via Claude Code's directory sandbox.** Claude Code has a built-in security sandbox that restricts filesystem access to the working directory and its subdirectories by default. When `spawn_agent` sets `working_directory` for the subprocess, the sub-agent is automatically sandboxed to that directory — it cannot read or write files outside it, even if instructed to. This is **enforcement-level** security provided by Claude Code's own infrastructure, not a compliance-based preamble instruction. Additional directories can be granted via Claude Code's `--add-dir` flag (see `allow_memory_read` and `additional_dirs` parameters below). This directory sandbox was confirmed through empirical testing of `claude -p` behavior.

### The `spawn_agent` Tool

The MCP bridge exposes a `spawn_agent` tool that the primary Claude conversation can call like any other tool. Under the hood, it invokes Claude Code CLI in non-interactive mode.

**Tool interfaces:**

```
spawn_agent(
  task: string,                    // The task description (becomes the prompt to claude -p)
  system_prompt: string | null,    // Optional task-specific instructions (appended to default preamble)
                                   //   The combined preamble + system_prompt is passed via
                                   //   --system-prompt, which REPLACES Claude Code's default
                                   //   system prompt. Claude Code's native tools (bash, file
                                   //   editing) remain available regardless. See Open Question #18.
  model: string | null,            // Model for the sub-agent (default: Claude Code's configured model)
                                   //   e.g., "sonnet" for routine tasks, "opus" for complex analysis
                                   //   Passed to claude -p via --model flag
  working_directory: string | null, // Working directory for the sub-agent (default: user's home)
                                   //   Also sets Claude Code's directory sandbox — the sub-agent
                                   //   CANNOT access files outside this directory (or its children)
                                   //   unless explicitly granted via additional_dirs or allow_memory_read
  additional_dirs: string[] | null, // Additional directories the sub-agent may access (default: none)
                                   //   Each entry is passed as --add-dir to claude -p
                                   //   Use when the sub-agent needs to read/write across multiple repos
  timeout_seconds: number | null,  // Maximum execution time for the sub-agent process (default: 300)
                                   //   This is the sub-agent's own timeout, NOT the MCP timeout.
                                   //   The bridge handles the MCP timeout separately (see below).
  max_output_tokens: number | null, // Truncate sub-agent response to this many tokens (default: 4000)
                                   //   Approximate: uses chars/4 heuristic, not a tokenizer
                                   //   Truncated responses get a marker appended
  allow_memory_read: boolean       // Whether sub-agent may read ~/.claude-agent-memory/ (default: false)
                                   //   When true, adds --add-dir ~/.claude-agent-memory to the
                                   //   invocation, granting read access via the directory sandbox.
                                   //   Write protection is preamble-based (compliance), not enforced.
) -> {                             // Returns immediately OR after completion (see hybrid execution below)
  status: "complete" | "running",  //   "complete" if the sub-agent finished within the sync window
  job_id: string | null,           //   Non-null if status is "running" (use with check_agent to poll)
  result: string | null            //   The sub-agent's text response if status is "complete"
}

check_agent(
  job_id: string                   // Job ID returned by spawn_agent when status was "running"
) -> {
  status: "running" | "complete" | "failed" | "timed_out",
  result: string | null,           // The sub-agent's text response if status is "complete"
  error: string | null             // Error description if status is "failed" or "timed_out"
}
```

**Execution flow (hybrid sync/async):**

Claude Desktop has a **hardcoded ~60-second timeout** for MCP tool calls (see [Open Question #3](#open-questions)). Tool calls completing under ~30 seconds reliably succeed; 30–60 seconds is unreliable; 60+ seconds consistently fails with the server's response silently dropped. Since sub-agent tasks can easily exceed this limit, the bridge uses a **hybrid sync/async execution model** that transparently handles both fast and slow sub-agents:

1. The primary agent calls `spawn_agent(task, ...)` via the MCP bridge.
2. The bridge constructs a `claude -p` invocation:
   - The `task` becomes the prompt.
   - The default system preamble (see below) plus any `system_prompt` are passed via `--system-prompt`, which **replaces** Claude Code's default behavioral prompt. Claude Code's native tools (bash, file editing) remain available regardless — they are injected separately from the system prompt.
   - `working_directory` sets the CWD for the subprocess **and** activates Claude Code's directory sandbox (the sub-agent cannot access files outside this directory or its children).
   - If `allow_memory_read` is `true`, `--add-dir ~/.claude-agent-memory` is added.
   - Each entry in `additional_dirs` is added as a separate `--add-dir` flag.
3. The bridge launches the Claude Code CLI subprocess and starts a **sync window timer** (default: 25 seconds — safely under the ~30-second reliability threshold for Claude Desktop's MCP timeout).
4. **If the sub-agent completes within the sync window:** The bridge applies output truncation if needed (see step 7) and returns `{ status: "complete", job_id: null, result: "..." }` directly. The primary agent receives the result in a single tool call — no polling needed. This is the fast path for simple tasks.
5. **If the sub-agent is still running when the sync window expires:** The bridge assigns a job ID, lets the subprocess continue running in the background, and immediately returns `{ status: "running", job_id: "abc123", result: null }`. This response reaches Claude Desktop well within the MCP timeout.
6. **For running jobs:** The primary agent calls `check_agent(job_id)` to poll for the result. Each `check_agent` call returns immediately with the current status (`"running"`, `"complete"`, `"failed"`, or `"timed_out"`). When `status` is `"complete"`, the `result` field contains the sub-agent's output. The primary agent may need to poll multiple times for long-running tasks; each poll is a fast MCP round-trip.
7. **Output truncation:** When the sub-agent completes (whether via the sync path or async path), if the captured output exceeds `max_output_tokens` (estimated via a chars/4 heuristic), the bridge truncates from the end and appends: `\n\n[Output truncated at ~{N} tokens. Original output was ~{M} tokens.]`
8. The primary agent incorporates the result into its conversation — summarizing it, acting on it, or persisting relevant findings to Layer 2 memory.

**Bridge implementation notes:** The bridge maintains a map of active jobs (job ID → subprocess handle + captured output). Jobs are cleaned up after the result is retrieved via `check_agent`, or after a configurable expiry period (e.g., 10 minutes) if never retrieved. The `timeout_seconds` parameter controls how long the subprocess is allowed to run (default: 300 seconds) — this is independent of the MCP timeout and the sync window.

**Example invocations from the primary agent's perspective:**

Simple file search (completes within sync window — single tool call):
```
// Primary agent calls spawn_agent:
spawn_agent(
  task: "Find all Python files under ~/projects/foo that import the `requests` library. List each file with the line number of the import.",
  working_directory: "~/projects/foo"
)
// Bridge returns in ~10 seconds (sync path):
// -> { status: "complete", job_id: null, result: "Found 3 files:\n  src/api.py:4 ..." }
```

Architecture review with memory read access (may exceed sync window):
```
// Primary agent calls spawn_agent:
spawn_agent(
  task: "Review the architecture described in ~/.claude-agent-memory/blocks/mcp-bridge.md and identify any gaps in error handling. Focus on the command execution tools.",
  system_prompt: "Return your analysis as a markdown list. Each finding should have a severity (high/medium/low) and a one-line recommendation.",
  allow_memory_read: true
)
// Bridge returns after 25 seconds (async path — sub-agent still running):
// -> { status: "running", job_id: "review-a1b2c3", result: null }

// Primary agent polls:
check_agent(job_id: "review-a1b2c3")
// -> { status: "running", result: null, error: null }

// Primary agent polls again after a delay:
check_agent(job_id: "review-a1b2c3")
// -> { status: "complete", result: "## Error Handling Gaps\n\n- **High:** ...", error: null }
```

Test suite runner (long-running, will use async path):
```
// Primary agent calls spawn_agent:
spawn_agent(
  task: "Run `npm test` in this directory. If any tests fail, analyze the failures and suggest fixes.",
  working_directory: "~/projects/mcp-bridge",
  timeout_seconds: 300
)
// Bridge returns after 25 seconds (async path):
// -> { status: "running", job_id: "test-d4e5f6", result: null }

// Primary agent polls periodically until complete or timed_out.
```

### Execution Model: Hybrid Sync/Async with Sequential Spawning

The execution model is driven by a hard platform constraint: Claude Desktop has a **hardcoded ~60-second timeout** for MCP tool calls, with reliability degrading above ~30 seconds (see [Open Question #3](#open-questions)). Since sub-agent tasks can easily exceed this, the bridge uses a **hybrid sync/async model** where `spawn_agent` transparently adapts based on how long the sub-agent takes:

- **Fast tasks (under ~25 seconds):** `spawn_agent` blocks, waits for the sub-agent to finish, and returns the result directly. The primary agent gets the result in a single tool call. This is the common case for simple file searches, quick data extraction, and other lightweight tasks.
- **Slow tasks (over ~25 seconds):** `spawn_agent` returns a job ID after the sync window expires, and the sub-agent continues running in the background. The primary agent polls with `check_agent(job_id)` until the result is ready. Each poll is a fast MCP round-trip (well under the timeout). This handles complex code reviews, test suite runs, and other long-running tasks without hitting the MCP timeout.

The primary agent does not need to predict which path will be taken. It always calls `spawn_agent` the same way and inspects the returned `status` field to decide whether to poll.

**Sequential spawning.** Even with the hybrid model, the primary agent typically spawns sub-agents one at a time and waits for results before proceeding. This is natural for most workflows where tasks are dependent or where the primary agent needs to reason about one result before deciding the next step.

**Parallel spawning (future extension).** The hybrid model enables a natural extension for embarrassingly parallel tasks: the primary agent could call `spawn_agent` multiple times in succession, collecting job IDs for any that go async, then poll all of them. Since each `spawn_agent` call returns within the sync window (either with a result or a job ID), the MCP timeout is never hit. The bridge manages the subprocess lifecycle for all active jobs. If this pattern is implemented, a **configurable cap on concurrent sub-agents** should be enforced (e.g., `max_concurrent_agents: 5` in the bridge config) to limit API cost and system load (see [Open Question #14](#open-questions)).

### Default System Preamble

The MCP bridge injects a default system preamble into every sub-agent invocation via `--system-prompt`. Because `--system-prompt` **replaces** Claude Code's entire default behavioral prompt (empirically confirmed — see [Open Question #18](#open-questions)), the preamble is the **sole** set of behavioral instructions the sub-agent receives. Claude Code's native tools (bash, file editing, etc.) remain available regardless — tool definitions are injected separately from the system prompt at the infrastructure level.

This gives us clean, complete control over sub-agent behavior with no conflicting base prompt. The sub-agent will not exhibit Claude Code's default behaviors (terse 4-line responses, action-oriented coding style, parallel tool batching) unless the preamble explicitly instructs it to.

```
You are a sub-agent performing a focused task on behalf of a primary Claude conversation.

Rules:
- Complete the assigned task and return your findings as text output.
- Be concise and structured. Prefer markdown formatting for readability.
- Keep your response under 2,000 words unless the task requires more detail. Your output
  will be truncated if it exceeds a token budget, so prioritize the most important findings.
- Do NOT modify files under ~/.claude-agent-memory/. This directory is read-only for you.
- Do NOT commit to Git or push to any remote repository unless the task explicitly asks for it.
- If you cannot complete the task with the information provided, return a clear explanation
  of what additional information or context you need.
- Do NOT engage in open-ended exploration. Stay focused on the assigned task.
```

Note: The prohibition on modifying `~/.claude-agent-memory/` is a compliance-based instruction. The enforcement-level protection comes from Claude Code's directory sandbox — if `allow_memory_read` is `false`, the sub-agent cannot even *read* the memory directory because it is not included via `--add-dir`. If `allow_memory_read` is `true`, the directory is readable but the preamble instructs against writes. For additional hardening, the bridge could mount the memory directory read-only at the OS level.

The primary agent's optional `system_prompt` parameter is appended after this preamble, allowing task-specific instructions to override or extend the defaults.

### Sub-Agent Memory Access

The sub-agent memory model is intentionally restrictive:

| Memory Layer | Sub-Agent Access | Enforcement | Rationale |
|-------------|-----------------|-------------|----------|
| **Layer 1** (Anthropic built-in) | ❌ Not available | Platform | Claude Code CLI does not receive built-in memory injection. This is an Anthropic platform limitation, not a design choice. |
| **Layer 2** (supplementary files) | 🔒 Read-only (optional) | **Directory sandbox** (read) + preamble (write) | Controlled by `allow_memory_read`. When `false` (default), Claude Code's directory sandbox **blocks all access** — the sub-agent cannot read the memory directory. When `true`, `--add-dir ~/.claude-agent-memory` grants read access; the preamble instructs against writes (compliance-based). |
| **Claude Code auto-memory** | ⚠️ Available but separate | None (automatic) | `~/.claude/CLAUDE.md` and project-level `CLAUDE.md` files are loaded automatically by Claude Code regardless of `--system-prompt` or directory sandbox settings. See below, including security implications. |

**Why no write access?** Allowing sub-agents to write to Layer 2 would reintroduce the concurrent write problem — potentially worse than with multiple conversations, because sub-agents are automated and could be spawned in parallel. By making the primary agent the sole writer, we maintain a clean single-writer model for Layer 2.

**What if a sub-agent discovers something worth remembering?** It returns the finding in its text response. The primary agent decides whether to persist it to Layer 2 memory. This is the fire-and-forget pattern: the sub-agent does the work, the primary agent manages the knowledge.

### Relationship to Claude Code's Built-in Memory

Claude Code has its own memory system (`~/.claude/CLAUDE.md`, `~/.claude/projects/<project>/memory/MEMORY.md`, and project-level `.claude/CLAUDE.md` files). These are **entirely separate** from our Layer 2 supplementary memory at `~/.claude-agent-memory/`.

This separation is intentional:

- **Different purposes.** Claude Code's memory is designed for coding instructions, project patterns, and tool preferences (e.g., "use pnpm, not npm"). Our Layer 2 memory is designed for deep project context, episodic recall, decision history, and cross-project knowledge.
- **Different lifecycles.** Claude Code's auto-memory is managed by Claude Code itself (it writes to `MEMORY.md` as it discovers patterns). Our Layer 2 memory is managed by the primary agent following the memory skill's session lifecycle.
- **Coupling risk.** Piggybacking on Claude Code's memory locations would couple our design to Claude Code's conventions, which Anthropic could change at any time. An independent directory (`~/.claude-agent-memory/`) is under our control.
- **Scope isolation.** Claude Code's memory is loaded automatically at Claude Code session start (first 200 lines of `MEMORY.md`). If we put our Layer 2 content there, it would be loaded into every Claude Code session — including sub-agents that don't need it, wasting context window space.

Sub-agents invoked via `claude -p` *will* receive Claude Code's own memory if it exists (e.g., `~/.claude/CLAUDE.md` user-level instructions). This loading happens automatically regardless of `--system-prompt` or directory sandbox settings — it is part of Claude Code's startup sequence, not controlled by our bridge. Those instructions are typically useful for any Claude Code session (coding conventions, tool preferences). The key point is that our Layer 2 memory is loaded only when explicitly requested, not automatically.

**Security implication: Do not store credentials in `CLAUDE.md` files.** Because every sub-agent automatically receives `~/.claude/CLAUDE.md` (and any project-level CLAUDE.md), sensitive data in these files — API tokens, passwords, private keys — is exposed to every sub-agent invocation, including sub-agents running cheaper/less-trusted models on broad tasks. Store credentials in environment variables instead, and reference them from `CLAUDE.md` as `$ENV_VAR_NAME` rather than embedding the values directly. This was confirmed through empirical testing: a sub-agent invoked with `--system-prompt` (replacing Claude Code's default prompt) still loaded and reported contents from `~/.claude/CLAUDE.md`.

### Recommended CLAUDE.md Content for Sub-Agents

Since `~/CLAUDE.md` is loaded into every Claude Code invocation — including every sub-agent spawned by the MCP bridge — its content should be optimized for the sub-agent use case. In the B1 architecture, Claude Code CLI is used exclusively as a sub-agent runtime, not as a primary UI. The CLAUDE.md content should therefore be:

- **Lean.** Every token in CLAUDE.md is a fixed tax on every sub-agent invocation, regardless of task relevance. The file should contain only what is broadly useful across sub-agent tasks. Aim for under 500 tokens (~400 words).
- **Environment-focused.** Sub-agents need to know how to operate correctly on the host machine: OS type, shell behavior, pathname conventions, available tools. This prevents common errors (wrong path separators, missing executables, incorrect shell syntax).
- **Free of credentials.** No API tokens, passwords, or keys. Use environment variables instead (see security note above).
- **Free of interactive instructions.** Sub-agents are one-shot and non-interactive. Instructions like "confirm with the user before..." or "ask the user for..." are confusing in a sub-agent context. Remove or reframe them.
- **Free of service-specific instructions.** Sub-agents performing code review or file search don't need to know Bluesky posting conventions or GitHub profile URLs. Service-specific context should be passed via the `system_prompt` parameter of `spawn_agent` when relevant to the task, not baked into every invocation.

**Recommended CLAUDE.md structure for sub-agent use:**

```markdown
# OS Environment

- This is a Windows 11 system with Cygwin installed.
- Bash commands are executed by the Cygwin Bash shell.
- Most Linux commands are available: cd, cat, ls, grep, find, cp, mv, sed, awk, git, python, etc.
- To execute `rm`, use the full pathname `/bin/rm` (avoids a wrapper script's confirmation prompt).
- Cygwin symlinks for drive letters exist: /c -> /cygdrive/c, /d -> /cygdrive/d, etc.
  Native Windows apps cannot follow Cygwin symlinks.

## Pathname Conventions

- Cygwin apps: use forward slashes. Absolute paths start with /c/ (drive letter).
  Example: /c/franl/git/project/file.txt
- Native Windows apps: use backslashes, single-quoted to escape.
  Example: 'C:\franl\git\project\file.txt'
- If a pathname contains spaces or shell metacharacters, always single-quote it.

## Available Tools

- Compilers/runtimes: gcc, g++, go, rustc, cargo, python, node, npm, npx.
- Package managers: uv, uvx (Python), npm/npx (Node.js).
- Utilities: git, gh (GitHub CLI).
- Do not install additional tools without explicit task instructions to do so.

# Source Code Conventions

- Line width: under 100 columns.
- Use meaningful variable/loop names (not single characters).
- Newlines: UNIX-style (LF) for new files. Match existing convention when editing.
- Encoding: UTF-8 for new files. Match existing encoding when editing.
- Comments: write well-commented code. Aim for nearly as many comment lines as code lines.
  Comments should explain purpose and rationale, not restate what the code does.
  Place comments on the line above the code they reference.
- Prefer Python and Bash for scripts. Use PEP 723 metadata in Python scripts.
- Bash variables: UPPERCASE for globals, _UPPERCASE for function locals.
- When building executables, always use .exe extension (Windows).
```

This is roughly 350 tokens — well within budget. It gives every sub-agent the environment awareness needed to operate correctly on the host machine, plus coding conventions for consistent output, without any irrelevant context.

**Content that should NOT be in CLAUDE.md (and where it goes instead):**

| Content | Why not in CLAUDE.md | Where it goes |
|---------|---------------------|---------------|
| GitHub credentials or profile | Credential exposure; not needed for most tasks | Environment variables for tokens; `spawn_agent`'s `system_prompt` for profile context when needed |
| Bluesky credentials or posting conventions | Credential exposure; irrelevant to most sub-agents | Environment variables; `system_prompt` for Bluesky-specific tasks |
| "Confirm with the user" instructions | Sub-agents are non-interactive | Remove entirely; the `--system-prompt` preamble controls sub-agent behavior |
| Skill-writing guidelines | Niche; irrelevant to most sub-agent tasks | `system_prompt` for skill-writing tasks, or a project-level CLAUDE.md in the skills repo |
| GUI application build flags | Niche | `system_prompt` for GUI build tasks, or a project-level CLAUDE.md |

Note: Project-level CLAUDE.md files (placed in a project's `.claude/CLAUDE.md`) are also loaded by Claude Code when the sub-agent's `working_directory` is set to that project. These are a good place for project-specific conventions that don't belong in the global file.

## Implementation Roadmap

```
2026 Q1 (Now) — Deploy Architecture B1 + Supplementary Memory (Option 1)
├── Build local MCP bridge server (Go, single static binary)
│   ├── Stdio transport (for Desktop App)
│   ├── Filesystem tools (read, write, list, search)
│   ├── Command execution tools (run_command, run_script)
│   └── Security: directory/command allowlists, operation logging
├── Register bridge in Claude Desktop App (claude_desktop_config.json)
├── Test end-to-end: Desktop App → stdio → MCP bridge → local operations
├── Deploy supplementary memory (Option 1: filesystem-only)
│   ├── Create ~/.claude-agent-memory/ directory structure (core.md, index.md, blocks/)
│   ├── Write memory management skill (.zip) with session lifecycle instructions
│   ├── Seed core.md and index.md with initial context from existing conversations
│   ├── Verify Claude can read/write memory files via MCP bridge filesystem tools
│   └── Set up GitHub repo for memory backup (optional cron job for auto-commit)
└── Begin using Architecture B1 with layered memory for daily work

2026 Q2 — Expand tools, evaluate B2 upgrade, iterate on memory, add sub-agents
├── Expand MCP bridge tool set
│   ├── Network tools (HTTP requests, curl-equivalent)
│   ├── spawn_agent tool (invoke `claude -p` as subprocess)
│   │   ├── Implement default system preamble (role, constraints, no-memory-writes)
│   │   ├── Support optional system_prompt, working_directory, timeout, allow_memory_read
│   │   ├── Test with representative tasks (file search, code review, test runner)
│   │   └── Verify sub-agents cannot write to ~/.claude-agent-memory/
│   └── Optional: confirmation prompts for destructive operations
├── Iterate on supplementary memory based on real-world usage
│   ├── Tune memory skill prompts for better compliance (update frequency, summarization quality)
│   ├── Evaluate whether block count exceeds comfortable filename-based retrieval (~50 blocks)
│   ├── If retrieval is becoming cumbersome: upgrade to Option 3 (add FTS5 search index)
│   │   ├── Add memory_search(query) tool to MCP bridge
│   │   ├── Implement post-write indexing hook (rebuild .search-index.db on file change)
│   │   └── Test search quality against real memory content
│   └── Review memory quality: manually audit core.md, index.md, and sample blocks
├── Evaluate Desktop App stability and UI adequacy
├── If Desktop App proves limiting: upgrade to B2
│   ├── Add Streamable HTTP transport to bridge
│   ├── Configure secure tunnel (Cloudflare Tunnel recommended)
│   ├── Add tunnel URL as custom connector in Claude.ai
│   └── Optional: OAuth 2.1 authentication for the bridge endpoint
├── If MCP bridge approach is unworkable: implement Architecture A fallback
│   ├── Stateful memory skill (per existing design doc)
│   └── Claude Code Desktop as alternative environment
└── Contribute MCP bridge server as open-source project

2026 Q3–Q4 — Long-term evaluation
├── Evaluate Anthropic's evolving MCP Apps support
├── Evaluate Desktop App UI convergence with Claude.ai
├── Evaluate built-in memory improvements
│   └── If Anthropic's built-in memory grows substantially, reassess whether Layer 2 is still needed
├── Evaluate supplementary memory maturity
│   ├── Assess total block count and search effectiveness
│   ├── If Option 3 (FTS5) proves insufficient: evaluate Option 2 (dedicated memory server)
│   └── If semantic search is needed: evaluate local embedding model (e.g., all-MiniLM-L6-v2)
└── Evaluate emerging capabilities (agentic browsing, etc.)
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Claude Desktop App has stability issues (crashes, connector bugs) | Medium | Medium — degrades B1 | Monitor Anthropic's release notes for Desktop App improvements. Upgrade to B2 (Claude.ai + tunnel) if instability is persistent, or fall back to Architecture A. |
| Tunnel service unreliable for sustained use (B2 only) | Medium | Medium — degrades B2 | Does not affect B1 (no tunnel). For B2: evaluate multiple tunnel providers; Tailscale Funnel may be more reliable for personal use than ngrok. Fall back to B1 if tunnel proves unreliable. |
| Claude Code Desktop is discontinued or deprioritized | Low | High — blocks Architecture A | Architecture A's skill also works in Claude Code CLI. Build Architecture C as fallback. |
| MCP protocol undergoes breaking changes | Medium | Medium — requires bridge updates | Pin to stable MCP SDK versions; the bridge is small enough to update quickly. |
| Supplementary memory degrades in quality over time (all architectures) | Medium | Medium — memory becomes unreliable | Regular manual audits of `core.md`, `index.md`, and sample blocks. Markdown format makes manual correction easy. Git history provides rollback if a bad update corrupts memory. Periodic review cadence (e.g., monthly) to prune stale entries and fix inaccuracies. |
| Claude fails to follow memory skill instructions consistently | Medium | Medium — memories not persisted or poorly summarized | Iterate on skill prompts for clarity. Add explicit "end of session" reminders. Consider a wrapper script that prompts Claude to save memory before session close. Monitor compliance by checking file modification timestamps after sessions. |
| Supplementary memory grows too large for filename-based retrieval (Option 1) | Medium | Low — degrades retrieval, not data | Planned upgrade path: add FTS5 search index (Option 3) when block count exceeds ~50. The index is a derived artifact and can be added without restructuring the memory files. |
| Security incident via MCP bridge (unintended file access/command execution) | Low | High | Strict allowlists, operation logging, optional confirmation prompts for destructive operations. Run the bridge under a restricted user account. B1 has lower risk than B2 (no network exposure). Memory files in `~/.claude-agent-memory/` should be included in the allowlist but backed up via Git in case of accidental corruption. |
| Context window consumed by supplementary memory reduces conversation quality | Medium | Medium | Layer 1 (built-in memory) is Anthropic-managed and compact (~500–2,000 tokens). Layer 2 overhead is bounded: `core.md` + `index.md` loaded at session start (~1,000–2,000 tokens), content blocks loaded on demand only. Aggressive summarization in `core.md` keeps the fixed cost low. Total per-session overhead (both layers + MCP tool definitions) should remain under ~4,000 tokens. |
| Sub-agent escapes scope constraints (modifies files or memory it shouldn't) | Low | Medium — unintended side effects | Claude Code's built-in directory sandbox provides **enforcement-level** protection: the sub-agent cannot access files outside its `working_directory` (or explicitly granted `additional_dirs`). Memory directory access is controlled by `allow_memory_read` (maps to `--add-dir`), defaulting to `false` (no access). Write protection within granted directories is preamble-based (compliance). For additional hardening, the bridge could mount memory directories read-only at the OS level. Timeout prevents runaway sub-agents. |
| Sub-agent inherits credentials from `CLAUDE.md` | Medium | Medium — credential exposure | `~/.claude/CLAUDE.md` and project-level `CLAUDE.md` files are loaded automatically by every Claude Code invocation, including sub-agents. Any credentials stored in these files are visible to all sub-agents. **Mitigation:** Store credentials in environment variables, not in CLAUDE.md. Reference them as `$ENV_VAR_NAME`. |
| Sub-agent costs accumulate unexpectedly (API usage) | Medium | Low — financial, not data loss | Each `claude -p` invocation consumes API credits (or usage quota). The primary agent could spawn many sub-agents for a complex task. Mitigate with timeout limits, a per-session sub-agent count cap in the bridge, and monitoring of Claude Code usage in Settings > Usage. |
| Concurrent conversations corrupt supplementary memory via interleaved writes | Medium | Medium — silent data loss in shared files | Operational discipline (avoid parallel memory-intensive conversations) + read-before-write pattern in the memory skill. Append-only pattern for episodic logs eliminates conflicts for that file type. Upgrade to session-file merge or Git-based merge if concurrent writes become a recurring problem. See [Concurrent Conversation Writes](#concurrent-conversation-writes). |
| Anthropic's built-in memory improves enough to make Layer 2 unnecessary | Low | Low — positive outcome | Monitor Anthropic's memory improvements. If built-in memory grows to support structured project context, episodic recall, and search, the supplementary layer can be retired gracefully. Markdown files remain as a portable archive regardless. |

## Relation to Existing Design

This proposal is a **companion to** the [Stateful Agent Skill Design Document](stateful-agent-skill-design.md), not a replacement for it. The design document specifies *how the memory skill works internally* (three-tier model, markdown storage, pluggable backends, session lifecycle). This proposal specifies *which Claude environment to run it in* and *what additional infrastructure is needed* to satisfy the full set of requirements.

The key design decisions from the existing document that carry forward into **all** architectures, including Architecture B:

- **Three-tier memory model** (core, index, content blocks) — serves as the Layer 2 supplementary memory in all architectures. In Architecture B, it complements Anthropic's built-in memory (Layer 1) by providing deep project context, episodic memory, and technical notes that exceed Layer 1's ~500–2,000 token capacity.
- **Markdown storage** — unchanged; the format works in all architectures and provides the transparency advantage over Letta's opaque database storage.
- **GitHub API backend** — used for memory backup and version history in all architectures. In Architecture B, a cron job or manual process periodically commits `~/.claude-agent-memory/` to a GitHub repo.
- **Pluggable backends** — the backend interface makes it straightforward to add new backends. The upgrade path from Option 1 (filesystem-only) to Option 3 (filesystem + FTS5 search) is a concrete example of this flexibility.
- **Session lifecycle** (load at start, update during conversation, persist at end) — the skill's session lifecycle instructions carry forward directly. In Architecture B, the skill (.zip) teaches Claude when and how to interact with the supplementary memory files via the MCP bridge.

The [Supplementary Memory Strategy](#supplementary-memory-strategy) section above details how the existing design document's three-tier model integrates with Architecture B's layered memory approach. The key shift is that the memory skill is no longer the *entire* memory system (as it would be in Architecture A) — it is now the *Layer 2 supplement* to Anthropic's built-in Layer 1 memory. This is a narrower but still critical role: Layer 1 handles identity and preferences automatically, while Layer 2 handles everything that requires more depth, structure, or capacity than Layer 1 can provide.

## Open Questions

1. **~~MCP tunnel security (B2 only)~~** *(Resolved — not applicable):* B1 is the chosen architecture. B1 uses stdio with no network exposure, so tunnel security is not a concern. If B2 is pursued in the future, this question would need to be revisited.

2. **~~Custom connector limitations (B2 only)~~** *(Resolved — not applicable):* B1 is the chosen architecture. B1 uses the Desktop App's native local MCP support, not Claude.ai's custom connector feature. If B2 is pursued in the future, this question would need to be revisited.

3. **~~Desktop App MCP limitations (B1 only)~~** *(Resolved via research — significant timeout constraint identified):* Research into Claude Desktop's MCP behavior reveals several concrete limitations:

    - **Hardcoded ~60-second tool call timeout.** Claude Desktop uses the MCP TypeScript SDK default of `DEFAULT_REQUEST_TIMEOUT_MSEC = 60000`. Tool calls completing under ~30 seconds reliably succeed; 30–60 seconds is unreliable; 60+ seconds consistently fails with "No result received from client-side tool execution." The MCP server's response is silently dropped — the server completes successfully but Claude Desktop has stopped listening. This timeout is **not configurable** in Claude Desktop (unlike Claude Code CLI, which supports `MCP_TIMEOUT`). Feature requests for configurability (GitHub issues #5221, #22542) have been closed as "not planned" or marked "external."

    - **Impact on `spawn_agent`.** This is the most significant constraint. Sub-agents performing complex tasks (test suites, code reviews, large file searches) can easily exceed 60 seconds. **Mitigation:** The bridge's `spawn_agent` implementation must account for this. Options include: (a) setting the `spawn_agent` default `timeout_seconds` to 55 (under the 60s cliff) and documenting the limitation; (b) implementing a progress-reporting pattern where the bridge sends periodic MCP progress notifications to keep the connection alive (if Claude Desktop supports MCP progress tokens); (c) for long-running tasks, having the bridge return a "task started" acknowledgment quickly and provide a separate `check_result` tool for polling (similar to the async pattern in Open Question #14, but driven by the timeout constraint rather than parallelism). The best approach depends on whether Claude Desktop supports MCP progress notifications — this requires empirical testing during implementation.

    - **No documented tool-count limit.** Multiple MCP servers can be configured simultaneously in `claude_desktop_config.json`, and each can expose multiple tools. No hard limit on tool count has been reported.

    - **Known stability issues.** Bug reports describe tool call responses being dropped (race conditions in MCP message routing after handshake), UI freezing until user clicks/expands the tool panel, and stdio pipe failures when using `npx` as the command (workaround: use `node` directly or a compiled binary). These are active bugs being tracked by the community.

    - **No documented auto-reconnect.** If the MCP server subprocess crashes, Claude Desktop does not appear to automatically restart it. The user must restart the Desktop App. The bridge should be designed for robustness (crash recovery, clean error messages) but cannot rely on the client to handle server failures gracefully.

4. **~~Memory migration between layers~~** *(Resolved):* Reconciliation between Layer 1 (Anthropic's built-in memory) and Layer 2 (supplementary markdown files) is handled by a **periodic two-step audit**. First, a sub-agent is spawned with `allow_memory_read: true` to read all Layer 2 files and produce a structured digest of what Layer 2 contains — active projects, key facts, decisions, status summaries, and any Layer 2 bloat (blocks that could be summarized or archived). The sub-agent does not have access to Layer 1 (it runs as Claude Code CLI, which does not receive Anthropic's built-in memory). Second, the primary agent (Claude Desktop) receives the digest as a tool result. Because the primary agent already has Layer 1 in its context window (injected automatically), it can compare both layers and identify contradictions, gaps (important Layer 2 facts that Layer 1 should summarize), and stale entries (Layer 1 references completed/outdated projects). The primary agent then applies fixes — adding **steering edits** to Layer 1 via the `memory_user_edits` tool, and editing Layer 2 directly via MCP filesystem tools (`edit_file`, `write_file`). **Important:** Layer 1 edits are indirect. The `memory_user_edits` tool does not rewrite the Layer 1 summary directly — it adds steering instructions (e.g., "Fran completed the MCP bridge project in March 2026") that Anthropic's nightly background process incorporates when it regenerates the summary. This means Layer 1 corrections have up to ~24 hours of lag before they appear in the auto-generated summary. Layer 2 edits take effect immediately. The goal is *consistency*, not *parity*: Layer 1 is intentionally compact (~500–2,000 tokens) while Layer 2 is intentionally detailed. This reconciliation can run during an unattended wake period (see Open Question #17) to avoid blocking the user, or be triggered manually at the start of a session. For initial migration from Architecture A to Architecture B (where content in `core.md` should be reflected in Layer 1), the same process applies — the primary agent reads the existing `core.md` and adds steering edits to Layer 1 accordingly.

5. **~~MCP authentication best practices (B2 only)~~** *(Resolved — not applicable):* B1 is the chosen architecture. B1 does not need authentication since the bridge is only accessible to the local Desktop App process via stdio. If B2 is pursued in the future, this question would need to be revisited.

6. **Desktop App UI convergence (monitoring):** B1 is the chosen architecture. The Desktop App's UI is adequate but not as feature-rich as Claude.ai's. Monitor Anthropic's efforts to converge the Desktop App's UI with Claude.ai's (artifacts, tool widgets, cloud VM features). If the gap narrows, B1's position as the right choice is further strengthened. If the Desktop App stagnates, B2 becomes the fallback upgrade path.

7. **~~Memory skill as supplementary store~~** *(Resolved — see [Supplementary Memory Strategy](#supplementary-memory-strategy)):* Yes, the three-tier markdown memory system is valuable as a Layer 2 supplement to Anthropic's built-in Layer 1 memory. The new section details three options for implementing this, with Option 1 (filesystem-only) recommended as the starting point.

8. **~~Supplementary memory skill compliance~~** *(Resolved — strategies defined, empirical validation deferred to implementation):* The Layer 2 memory system depends on Claude reliably following the skill's instructions. Full empirical validation requires building and testing the skill, but the following compliance strategies are planned:

    - **Session-start loading.** The skill's instructions should be front-loaded and explicit: "At the start of every conversation, read `core.md` and `index.md` via the MCP bridge before responding to the user's first message." This is high-compliance because it's a concrete, verifiable action at a natural trigger point (conversation start).

    - **Session-end persistence.** This is the harder compliance challenge — conversations often end abruptly (user closes the window, context fills up, network disconnects). Strategies: (a) instruct Claude to persist incrementally during the conversation (after significant decisions, discoveries, or topic changes), not just at session end; (b) include a standing instruction: "If the user says goodbye or the conversation is winding down, persist any pending memory updates before your final response"; (c) the bridge could log `write_file` timestamps for memory files, allowing the user to verify after a session whether memory was updated.

    - **Incremental persistence over batch persistence.** Rather than accumulating changes and writing everything at session end, the skill should instruct Claude to update memory files as significant information emerges. This reduces the risk of losing an entire session's worth of updates if the conversation ends unexpectedly.

    - **Detection of compliance failures.** The bridge can log all `read_file` and `write_file` operations on `~/.claude-agent-memory/`. A simple post-session check: if the bridge log shows memory files were read at session start but never written during the session, and the conversation lasted more than a few turns, compliance likely failed. This could be surfaced as a notification or log entry for the user to review.

    - **Empirical tuning.** The specific wording of skill instructions, the frequency of persistence prompts, and the triggers for memory updates will need iterative tuning based on observed behavior during implementation. This is expected and normal for skill development.

9. **~~Layer 1 / Layer 2 content boundary~~** *(Resolved):* The boundary between Layer 1 and Layer 2 does not need to be explicitly managed because the two layers have fundamentally different control models. **Layer 1 is not directly editable.** Its auto-generated summary is produced by Anthropic's nightly background process, which decides what to extract from conversations using its own heuristics. The user and Claude can only influence Layer 1 indirectly via steering edits (the `memory_user_edits` tool), which the nightly process incorporates at regeneration time. **Layer 2 is fully under our control** — it's markdown files on disk, readable and writable at any time via the MCP bridge. Given this, the right approach is: let Layer 1's automatic system do what it does well (extracting identity, preferences, and high-level project awareness from conversations), and use Layer 2 for everything that needs more depth, structure, precision, or immediacy than Layer 1 provides. Overlap between layers is harmless — if both layers note that "Fran is working on an MCP bridge server," that's redundancy, not a conflict. Contradictions (e.g., Layer 1 says a project is active, Layer 2 says it's completed) are handled by the periodic reconciliation process (see Open Question #4), where the primary agent adds a steering edit to correct Layer 1. The memory skill does not need to instruct Claude on how to allocate content between layers — it only needs to instruct Claude on how to manage Layer 2, since Layer 1 manages itself.

10. **~~Concurrent write detection — should the MCP bridge enforce it?~~** *(Resolved — not needed for B1):* In the B1 architecture, concurrent write detection is unnecessary because the architecture naturally serializes all memory writes. Claude Desktop is a **single-instance application** — launching it a second time activates the existing instance rather than creating a new one. This means there is exactly one Desktop App process, which launches exactly one MCP bridge subprocess, connected via a single stdio pipe. Within a single conversation, Claude's inference is sequential (call tool, wait for result, decide next action), so two `write_file` calls cannot race. Across conversations within the same Desktop App instance, the stdio transport serializes requests through a single byte stream — even if two conversations were generating responses in parallel (e.g., the user switches conversations quickly), their tool calls would serialize through the same stdin/stdout pipe. For belt-and-suspenders safety, the bridge could add a simple mutex around file-write operations (trivial in Go), but even this is likely unnecessary given the natural serialization. The mtime-based optimistic concurrency mechanism originally considered (tracking file modification times to detect stale writes) is deferred indefinitely — it adds significant complexity (per-session state tracking, graceful rejection handling, re-read/merge/retry logic) for a scenario that cannot occur in the B1 single-instance architecture. If the design later moves to B2 (Claude.ai, where multiple browser tabs could connect to the bridge simultaneously via HTTP), this question should be revisited.

11. **~~Supplementary memory portability across Claude interfaces~~** *(Resolved — simplified by B1 choice):* B1 is the chosen architecture. In B1, all operations happen locally via the MCP bridge — there is no cloud VM involved. The Desktop App does not use a cloud VM for code execution or file creation (unlike Claude.ai). Layer 2 memory files at `~/.claude-agent-memory/` are directly accessible via the bridge's filesystem tools at all times. The cloud VM portability concern only applied to B2 (Claude.ai), which is not planned for initial implementation.

12. **~~Use of sub-agents~~** *(Resolved — see [Sub-Agent Architecture](#sub-agent-architecture)):* Sub-agents are implemented as one-shot Claude Code CLI invocations via a `spawn_agent` MCP tool. They have no memory of their own, optional read-only access to Layer 2, and return their results as text to the primary agent.

13. **~~Sub-agent model selection~~** *(Resolved):* The `spawn_agent` tool includes an optional `model` parameter. The primary agent (running in Claude Desktop, typically on a capable model like Opus) selects the appropriate model for each sub-agent based on the task's complexity — e.g., Haiku or Sonnet for simple file searches and data extraction, Opus for complex analysis or code review. The bridge passes this to `claude -p` via the `--model` flag. This pattern — a smarter orchestrator model delegating to less capable (faster, cheaper) models for routine sub-tasks — is a well-established practice in multi-agent systems. If `model` is omitted, the sub-agent uses whatever model Claude Code is configured to use by default.

14. **~~Sub-agent parallelism~~** *(Resolved — see [Execution Model](#execution-model-hybrid-syncasync-with-sequential-spawning)):* The hybrid sync/async execution model (required to work around Claude Desktop's ~60-second MCP timeout — see Open Question #3) provides the async infrastructure needed for parallel sub-agents as a natural extension. The primary agent can call `spawn_agent` multiple times in succession, collecting job IDs for any that go async, then poll all of them with `check_agent`. Each `spawn_agent` call returns within the sync window, so the MCP timeout is never hit. If parallel spawning is used, **yes, there should be a cap on concurrent sub-agents** to limit API cost and system load. The cap should be configurable in the bridge (e.g., `max_concurrent_agents: 5` in the bridge config), with `spawn_agent` returning an error if the cap is reached. The specific default value is deferred to implementation.

15. **~~Sub-agent output size~~** *(Resolved):* The `spawn_agent` tool includes a `max_output_tokens` parameter (default: 4,000 tokens, estimated via a chars/4 heuristic). If a sub-agent's output exceeds this limit, the bridge truncates from the end and appends a marker indicating the truncation and original size. The default system preamble also includes a soft instruction ("keep your response under 2,000 words") so sub-agents self-limit before the hard truncation kicks in. The two mechanisms are complementary: the preamble is a soft hint, `max_output_tokens` is the hard ceiling that protects the primary agent's context window regardless of sub-agent behavior.

16. **~~Coding Language for MCP Bridge~~** *(Resolved):* **Go** is the chosen language. It compiles to a single static binary with no runtime dependencies (no Node.js, no Python), has excellent subprocess management and concurrency primitives (goroutines), fast startup, and low memory footprint. The Go MCP ecosystem is supported by [`mark3labs/mcp-go`](https://github.com/mark3labs/mcp-go). SQLite FTS5 integration (for Option 3) is available via `modernc.org/sqlite` (pure Go, no CGO) or `mattn/go-sqlite3` (CGO wrapper). The single-binary deployment model means installation is just copying the executable — no package managers, no virtual environments, no version conflicts.

17. **Remote access via Telegram, Discord, and Signal (watch this space):** It would be valuable to have remote access to the agent from a phone via messaging apps, similar to what LettaBot and OpenClaw provide. Two implementation paths were explored:

    - **`claude -p` bot:** A messaging bot receives inbound messages and invokes Claude Code CLI (`claude -p`) with Layer 2 memory loaded via `--append-system-prompt`. This is fully programmatic and reliable, but sub-agents invoked this way have no Layer 1 memory, no Claude Desktop UI, and limited conversational continuity (each message is either a one-shot invocation or requires the bot to manage conversation history). Output is restricted to plain text/markdown — no artifacts, though images could be sent via the messaging API.

    - **UI automation via AutoHotkey (inbound) + MCP tool (outbound):** An AutoHotkey script injects Telegram messages directly into Claude Desktop via `SendInput`, giving the bot full access to the Desktop App's capabilities (Layer 1 memory, MCP bridge, artifacts). Claude sends its response back to Telegram via a `send_message` MCP tool. This reuses the entire existing infrastructure but is fragile — UI automation depends on timing (`Sleep`), window focus, and app UI stability, with no reliable way to detect when Claude Desktop is ready for input.

    A deeper problem blocks both paths from being ideal: **MCP is strictly client-initiated.** The bridge cannot asynchronously push a prompt into Claude Desktop — it can only respond when Claude calls a tool. There is no server-initiated prompting capability in the MCP protocol. Until Anthropic adds such a capability (or the Claude Desktop App exposes a programmatic interface for injecting prompts, e.g., via an IPC channel or local HTTP endpoint), fully seamless remote access through the Desktop App is not achievable.

    **Status: Not implementing now.** Revisit if any of the following change: (a) the MCP protocol adds server-initiated prompting or a push notification mechanism, (b) Claude Desktop exposes a local API or automation interface, or (c) `claude -p` gains session resumption support (`--continue`) that works reliably enough to provide conversational continuity for a messaging bot.

18. **~~System prompt differences between Claude Desktop and Claude Code~~** *(Resolved via empirical testing):* Claude Desktop and Claude Code have significantly different system prompts. Anthropic officially publishes Claude Desktop's system prompt at https://docs.claude.com/en/release-notes/system-prompts — it emphasizes warm conversational tone, natural prose, minimal formatting, and broad tool integration (web search, memory, file creation, etc.). Claude Code's system prompt is **not** officially published, but has been extracted from the compiled source code by the community (see [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts) for the most comprehensive and actively maintained collection). Claude Code's prompt is dramatically different: it enforces terse output ("fewer than 4 lines of text unless user asks for detail"), emphasizes action-oriented tool use (batch calls, parallel execution), and is assembled dynamically from 110+ prompt fragments covering tool descriptions, sub-agent prompts, utility functions, and context-specific variables.

    **Empirical findings from testing `claude -p --system-prompt`:**

    - **(a) `--system-prompt` fully replaces the behavioral prompt.** A test with `--system-prompt "You are a haiku poet. Respond only in haiku."` produced a pure haiku response with no trace of Claude Code's default behavior (no tool use, no terse coding-agent style, no "fewer than 4 lines" constraint).
    - **(b) Claude Code's native tools survive the replacement.** A test with a minimal system prompt ("You are a helpful assistant. Complete the task and report your findings.") confirmed the sub-agent could successfully use bash (`ls`), read files (`cat`/native file tools), and report results. Tool definitions are injected separately from the system prompt at the infrastructure level.
    - **(c) File reading tools also work.** A test asking the sub-agent to read and summarize a `README.md` file confirmed that file reading tools function correctly with a replacement system prompt.
    - **(d) Claude Code's directory sandbox is enforced independently.** A test attempting to read a file outside the working directory was blocked by Claude Code's security sandbox, confirming that directory access restrictions operate at the infrastructure level regardless of the system prompt.
    - **(e) `~/.claude/CLAUDE.md` is loaded regardless.** Claude Code's startup sequence loads `~/.claude/CLAUDE.md` and project-level `CLAUDE.md` files automatically, independent of `--system-prompt` or directory sandbox settings. This has security implications for credentials — see [Relationship to Claude Code's Built-in Memory](#relationship-to-claude-codes-built-in-memory).

    **Design decision:** The `spawn_agent` tool uses `--system-prompt` (not `--append-system-prompt`) to pass the default preamble plus any task-specific instructions. This gives complete control over sub-agent personality and constraints with no conflicting base prompt. The Sub-Agent Architecture section has been updated throughout to reflect this.

19. **~~Contents of my CLAUDE.md~~** *(Resolved — see [Recommended CLAUDE.md Content for Sub-Agents](#recommended-claudemd-content-for-sub-agents)):* The current `CLAUDE.md` was written for interactive Claude Code CLI use as a primary UI. In the B1 architecture, Claude Code CLI is used exclusively as a sub-agent runtime, so the file should be optimized for that use case. The current file (~1,500–2,000 tokens) contains credential references, interactive instructions ("confirm with the user"), and service-specific content (Bluesky posting conventions, GitHub profile) that are unnecessary or counterproductive for sub-agents. A new section in the Sub-Agent Architecture provides a recommended lean CLAUDE.md (~350 tokens) focused on OS environment, pathname conventions, available tools, and source code conventions. Niche and service-specific content should move to `spawn_agent`'s `system_prompt` parameter or project-level CLAUDE.md files.

20. What is the precise format for individual memory entries?  Should memories be JSON for structure?

21. Claude Desktop already has built-in filesystem access: it was used to write this file. What benefits/drawbacks does MCP filesystem access have compared to the built-in functionality?

22. How to guarantee that network access happens from the local machine (via MCP) instead of from the cloud VM, where egress restrictions exist?

23. Same question as #22 for GitHub access: how to guarantee use of the local `git` command instead of the `github` skill's scripts in the cloud VM?

24. Will folder `~/.claude-agent-memory/blocks/` contain both files named `episodic-YYYY-MM.md` (for each month) and files named `episodic-YYYY-MM-DD.md` (for each day)?

25. Under what conditions will Claude create new memory block files not named in this proposal?

26. What exactly is a 'block reference' in `index.md`?
