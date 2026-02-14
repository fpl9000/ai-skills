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
- [Implementation Roadmap](#implementation-roadmap)
- [Risks and Mitigations](#risks-and-mitigations)
- [Relation to Existing Design](#relation-to-existing-design)
- [Open Questions](#open-questions)

## Executive Summary

The goal is to use Claude — accessed through Anthropic's own UIs rather than a custom harness like LettaBot — as a **stateful agent** with persistent memory, full local system access (filesystem, network, command execution), and a graphical user interface. No single Claude environment currently provides all of these capabilities simultaneously. This proposal evaluates four architectures that bridge the gaps, with a recommendation to pursue **Architecture B** (Local MCP Bridge) as the primary strategy. Architecture B has two variants: **B1** uses the Claude Desktop App with a local MCP bridge (no tunnel required, simpler setup, available today) and **B2** uses Claude.ai with the same MCP bridge exposed via a secure tunnel (best UI, but adds tunnel complexity). **Architecture A** (Claude Code Desktop + Stateful Memory Skill) remains as a fallback that requires no MCP infrastructure at all.

Because Anthropic's built-in memory is limited (~500–2,000 tokens — adequate for identity and preferences, but far too small for deep project context, episodic recall, or technical notes), this proposal also defines a **two-layer memory strategy**. Layer 1 is Anthropic's built-in memory (automatic, compact, always present). Layer 2 is a supplementary system using the three-tier markdown memory model from the [existing design document](stateful-agent-skill-design.md), accessed via the MCP bridge's filesystem tools. This layered approach brings Claude closer to the deep memory capabilities of systems like Letta (formerly MemGPT) while maintaining transparency (human-readable markdown files) and portability (Git-backed, no vendor lock-in).

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

**The MCP bridge server** is a relatively simple program (likely written in TypeScript or Python, since MCP SDKs exist for both) that:

- Exposes tools for filesystem operations (`read_file`, `write_file`, `list_dir`, `search`), network requests (`http_get`, `http_post`), and command execution (`run_command`, `run_script`).
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
│  │        Local MCP Bridge Server                    │      │
│  │        (launched as subprocess by Desktop App)     │     │
│  │                                                   │      │
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

### Primary Strategy (Now): Architecture B1

**Build a local MCP bridge server and connect it to the Claude Desktop App via stdio.**

This is the simplest path to satisfying all five requirements. The Claude Desktop App provides built-in memory and a rich GUI. A local MCP bridge server provides local filesystem, network, and command access. No tunnel is needed — the Desktop App launches the bridge as a local subprocess.

Specific actions:

1. **Build the local MCP bridge server** using the TypeScript or Python MCP SDK. Implement stdio transport with tools for filesystem operations, network requests, and command execution.
2. **Register the bridge** in the Desktop App's MCP configuration file (`claude_desktop_config.json`).
3. **Implement security controls**: directory allowlists, command allowlists, and operation logging.
4. **Test and iterate** on the tool set — start with filesystem and command execution, then add network tools as needed.

### Upgrade Path: Architecture B2

**If the Desktop App's UI limitations or stability issues become frustrating, upgrade to B2 by adding a tunnel and switching to Claude.ai.**

The same MCP bridge codebase supports both stdio (B1) and Streamable HTTP (B2) transports. The upgrade path is:

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

**Strategy:** Store the three-tier memory structure (from the existing design document) as markdown files on the local filesystem, and access them via the MCP bridge's existing filesystem tools (`read_file`, `write_file`, `list_dir`, `search_files`). A Claude skill (.zip) provides the instructions that teach Claude how to manage the memory lifecycle.

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

## Implementation Roadmap

```
2026 Q1 (Now) — Deploy Architecture B1 + Supplementary Memory (Option 1)
├── Build local MCP bridge server (TypeScript or Python)
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

2026 Q2 — Expand tools, evaluate B2 upgrade, iterate on memory
├── Expand MCP bridge tool set
│   ├── Network tools (HTTP requests, curl-equivalent)
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

1. **MCP tunnel security (B2 only):** Architecture B2 requires a tunnel service to make the local MCP server reachable from Claude.ai. What are the security implications of exposing local filesystem and command execution behind a public URL? Cloudflare Tunnel offers access policies and authentication; ngrok offers IP allowlisting and webhook verification. Which approach provides the best security-to-convenience tradeoff? Note: This question does not apply to B1, which uses stdio with no network exposure.

2. **Custom connector limitations (B2 only):** Claude.ai's custom connector support is relatively new. Are there rate limits, timeout restrictions, or tool-count limits that could constrain the MCP bridge's usefulness? The help docs mention that Advanced Research cannot invoke tools from connectors — are there other feature restrictions? Note: This question does not apply to B1, which uses the Desktop App's native MCP support.

3. **Desktop App MCP limitations (B1 only):** Are there tool-count limits, timeout restrictions, or other constraints on local MCP servers in the Claude Desktop App? How does the Desktop App handle MCP server crashes or restarts? Can the Desktop App be configured to auto-reconnect to a restarted MCP server?

4. **Memory migration between layers:** With the two-layer memory system, Layer 1 (Anthropic's built-in) and Layer 2 (supplementary markdown files) will inevitably contain overlapping or contradictory information. What happens when they diverge? Should there be a periodic reconciliation process? Additionally, if transitioning from Architecture A (where the skill *is* the entire memory) to Architecture B (where the skill becomes Layer 2 only), some content currently in `core.md` should migrate into Layer 1 (built-in memory) — but Anthropic's import mechanism (if one exists) is undocumented. Anthropic has added experimental memory import/export support; monitor its maturity.

5. **MCP authentication best practices (B2 only):** Claude.ai's custom connector flow supports OAuth 2.1 with optional client ID and secret. For a personal MCP bridge server, is full OAuth overkill? Would a simpler shared-secret approach suffice, or does the tunnel service's own authentication layer (e.g., Cloudflare Access) make application-level auth unnecessary? Note: B1 does not need authentication since the bridge is only accessible to the local Desktop App process.

6. **Desktop App UI convergence:** The Claude Desktop App already supports local MCP servers via stdio, which is what makes B1 possible without a tunnel. Is Anthropic actively working to converge the Desktop App's UI with Claude.ai's (artifacts, tool widgets, cloud VM features)? If the gap narrows significantly, B1 becomes the clear winner over B2 with no meaningful tradeoff.

7. **~~Memory skill as supplementary store~~** *(Resolved — see [Supplementary Memory Strategy](#supplementary-memory-strategy)):* Yes, the three-tier markdown memory system is valuable as a Layer 2 supplement to Anthropic's built-in Layer 1 memory. The new section details three options for implementing this, with Option 1 (filesystem-only) recommended as the starting point.

8. **Supplementary memory skill compliance:** The Layer 2 memory system depends on Claude reliably following the skill's instructions to read memory at session start and persist updates at session end. How reliable is this in practice? What prompting strategies maximize compliance? Is there a way to detect when Claude has failed to persist changes (e.g., by comparing file timestamps before and after a session)?

9. **Layer 1 / Layer 2 content boundary:** What content belongs in Layer 1 (built-in memory) vs. Layer 2 (supplementary)? The design says Layer 1 handles identity/preferences and Layer 2 handles project context/episodic memory, but the boundary is fuzzy. For example, should "Fran is working on an MCP bridge server" live in Layer 1 (high-level project awareness) or Layer 2 (project detail)? Should the memory skill explicitly instruct Claude on how to allocate content between layers?

10. **Concurrent write detection — should the MCP bridge enforce it?** The [Concurrent Conversation Writes](#concurrent-conversation-writes) section recommends read-before-write as the primary mitigation, relying on Claude following the skill's instructions. But the bridge could enforce this at the infrastructure level using optimistic concurrency: track each file's `mtime` (via the OS's standard `stat()` call) when the bridge serves a `read_file` request, then reject a subsequent `write_file` to the same path if `mtime` has advanced since the read (meaning another conversation modified the file in the interim). This would make stale-write detection automatic rather than depending on Claude's compliance. The tradeoff is added complexity in the bridge (per-session state tracking for `mtime` values) and the need to handle the rejection gracefully (Claude would need to re-read, merge, and retry). Is this worth building into the bridge from the start, or should it be deferred until concurrent writes prove to be a problem in practice?

11. **Supplementary memory portability across Claude interfaces:** The Layer 2 memory files live on the local filesystem. They are accessible from B1 (Desktop App via MCP bridge), B2 (Claude.ai via tunnel), and Architecture A (Claude Code Desktop via native filesystem). But what about Claude.ai's cloud VM (used for file creation and code execution)? The cloud VM cannot access the local filesystem. If Claude is asked to reference supplementary memory during a cloud VM task, it would need to read the memory via MCP tools *before* switching to VM execution. Is this workflow ergonomic, or does it create friction?
