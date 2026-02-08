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
- [Implementation Roadmap](#implementation-roadmap)
- [Risks and Mitigations](#risks-and-mitigations)
- [Relation to Existing Design](#relation-to-existing-design)
- [Open Questions](#open-questions)

## Executive Summary

The goal is to use Claude — accessed through Anthropic's own UIs rather than a custom harness like LettaBot — as a **stateful agent** with persistent memory, full local system access (filesystem, network, command execution), and a graphical user interface. No single Claude environment currently provides all of these capabilities simultaneously. This proposal evaluates four architectures that bridge the gaps, with a recommendation to pursue **Architecture B** (Local MCP Bridge) as the primary strategy. Architecture B has two variants: **B1** uses the Claude Desktop App with a local MCP bridge (no tunnel required, simpler setup, available today) and **B2** uses Claude.ai with the same MCP bridge exposed via a secure tunnel (best UI, but adds tunnel complexity). **Architecture A** (Claude Code Desktop + Stateful Memory Skill) remains as a fallback that requires no MCP infrastructure at all.

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
- The memory skill consumes context window space. Loading `core.md` and `index.md` on every session reduces the available context for actual conversation.
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
- Built-in memory — Anthropic's memory system, no context window overhead.
- Rich GUI — not quite Claude.ai-grade, but has artifacts, file handling, and most UI features.
- Skills support — custom skills can be uploaded and used alongside the MCP bridge.
- Simplest setup of any Architecture B variant — just configure the Desktop App's MCP settings and point it at the bridge server binary.
- Lowest security surface — the bridge is only accessible to the Desktop App process, not to the network.

**B1 Cons:**
- The Desktop App's UI is slightly less feature-rich than Claude.ai. It lacks the cloud VM for code execution/file creation (though the MCP bridge can provide equivalent local functionality), and may lack some of Claude.ai's specialized tool widgets.
- The Desktop App has reported stability issues (crashes related to connectors/extensions). These may improve over time as the app matures.
- The Desktop App is available on macOS and Windows, but may have platform-specific quirks.

**B1 Verdict:** This is the **simplest and most self-contained** variant of Architecture B. It satisfies all five requirements with minimal infrastructure — no tunnel, no cloud dependency for local operations, and no context window overhead for memory. The only tradeoff is a slightly less polished UI compared to Claude.ai.

#### Variant B2: Claude.ai + Local MCP Bridge via Tunnel

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude.ai (Web UI)                       │
│                                                              │
│  Built-in memory ✅    Rich UI ✅    Artifacts ✅            │
│  Tool widgets ✅       File previews ✅                      │
│                                                              │
│           │  MCP Protocol (Streamable HTTP)                   │
│           ▼                                                  │
│  ┌──────────────────────────────────────────────────┐        │
│  │  Secure Tunnel (Cloudflare/ngrok/Tailscale)       │        │
│  └──────────────────────────────────────────────────┘        │
│           │                                                  │
└───────────┼──────────────────────────────────────────────────┘
            │
┌───────────┼──────────────────────────────────────────────────┐
│           ▼                                                  │
│  ┌──────────────────────────────────────────────────┐        │
│  │        Local MCP Bridge Server                    │        │
│  │        (long-running daemon)                      │        │
│  │                                                   │        │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │        │
│  │  │Filesystem│  │ Network  │  │Command Exec   │   │        │
│  │  │  Tools   │  │  Tools   │  │   Tools       │   │        │
│  │  └──────────┘  └──────────┘  └───────────────┘   │        │
│  └──────────────────────────────────────────────────┘        │
│                                                              │
│  User's Local Machine                                        │
│  Local filesystem ✅  Local network ✅  Local commands ✅     │
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
- No context window overhead for memory (unlike Architecture A's skill-based approach).
- The bridge server can be hardened with allowlists and logging, providing a security boundary.
- A single codebase supports both variants, so you can switch between B1 and B2 at will.

#### Architecture B: Overall Verdict

Architecture B is the **recommended approach**. Start with **B1** (Desktop App, no tunnel) for simplicity, and upgrade to **B2** (Claude.ai, with tunnel) if you need Claude.ai's superior UI features or if the Desktop App's stability proves insufficient. Both variants are achievable today.

---

### Architecture C: Claude Code CLI + Web Terminal UI

**Strategy:** Use Claude Code CLI for its full local access and skills support, but replace the raw terminal with a web-based terminal UI for a better visual experience.

```
┌─────────────────────────────────────────────────────────┐
│              Web Browser (localhost:8080)                 │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Web Terminal UI                                   │  │
│  │  (e.g., ttyd, xterm.js, custom React app)          │  │
│  │                                                    │  │
│  │  Features:                                         │  │
│  │  - Rich text / Markdown rendering                  │  │
│  │  - Syntax-highlighted code blocks                  │  │
│  │  - Scrollback with search                          │  │
│  │  - Session history sidebar                         │  │
│  │  - Copy-paste with formatting                      │  │
│  │  └─────────────────────────────────────────────┘   │  │
│  │              │                                     │  │
│  │              │  stdin/stdout                       │  │
│  │              ▼                                     │  │
│  │  ┌─────────────────────────────────────────────┐   │  │
│  │  │  Claude Code CLI                            │   │  │
│  │  │  + Stateful Memory Skill                    │   │  │
│  │  │                                             │   │  │
│  │  │  Local filesystem ✅  Local network ✅       │   │  │
│  │  │  Local commands ✅    Memory ✅ (skill)      │   │  │
│  │  └─────────────────────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  GUI ⚠️ (terminal-grade, not Claude.ai-grade)            │
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
│  │                         │    │ (Claude Code CLI)          │  │
│  │  Primary conversation   │    │                            │  │
│  │  Built-in memory        │◄──►│  Local filesystem          │  │
│  │  Rich UI                │    │  Local network              │  │
│  │  Artifacts              │    │  Local commands             │  │
│  │                         │    │  Stateful Memory Skill     │  │
│  │  When local access is   │    │                            │  │
│  │  needed, instructs user │    │  Runs tasks, returns       │  │
│  │  or sidecar agent.      │    │  results to clipboard or   │  │
│  │                         │    │  shared file location.     │  │
│  └─────────────────────────┘    └───────────────────────────┘  │
│           │                              │                      │
│           └──────── Coordination ────────┘                      │
│           (manual copy-paste, shared files,                     │
│            or automated via MCP/webhook)                        │
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
|-----------|:--------------------:|:--------------------:|:------------------:|:---------------:|:-----------------:|
| **Available today** | ✅ Yes | ✅ Yes (needs MCP bridge) | ✅ Yes (needs MCP bridge + tunnel) | ⚠️ Requires dev work | ✅ Yes (manual) |
| **R1: Persistent memory** | ⚠️ Skill-based | ✅ Built-in | ✅ Built-in | ⚠️ Skill-based | ✅ Built-in (primary) |
| **R2: Local filesystem** | ✅ Native | ✅ Via MCP | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R3: Local network** | ✅ Native | ✅ Via MCP | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R4: Local commands** | ✅ Native | ✅ Via MCP | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R5: Graphical UI** | ⚠️ Basic GUI | ✅ Rich (near Claude.ai) | ✅ Best-in-class | ⚠️ Terminal-grade | ✅ Best-in-class |
| **Context window cost** | ⚠️ Skill overhead | ✅ None | ✅ None | ⚠️ Skill overhead | ✅ Minimal |
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

Anthropic is actively developing memory, MCP, and tool integration features (including MCP Apps for interactive in-conversation UIs, announced January 2026). The long-term trajectory is that the MCP bridge server becomes the only piece of custom infrastructure — a clean, maintainable, general-purpose tool. As the Desktop App's UI matures and converges with Claude.ai, the gap between B1 and B2 will narrow, potentially eliminating the need for the tunnel altogether. As Anthropic's built-in memory improves, the supplementary memory skill (if used in Architecture A) may become unnecessary.

## Implementation Roadmap

```
2026 Q1 (Now) — Deploy Architecture B1
├── Build local MCP bridge server (TypeScript or Python)
│   ├── Stdio transport (for Desktop App)
│   ├── Filesystem tools (read, write, list, search)
│   ├── Command execution tools (run_command, run_script)
│   └── Security: directory/command allowlists, operation logging
├── Register bridge in Claude Desktop App (claude_desktop_config.json)
├── Test end-to-end: Desktop App → stdio → MCP bridge → local operations
└── Begin using Architecture B1 for daily work

2026 Q2 — Expand tools, evaluate B2 upgrade
├── Expand MCP bridge tool set
│   ├── Network tools (HTTP requests, curl-equivalent)
│   └── Optional: confirmation prompts for destructive operations
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
├── Assess whether supplementary memory skill adds value
└── Evaluate emerging capabilities (agentic browsing, etc.)
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Claude Desktop App has stability issues (crashes, connector bugs) | Medium | Medium — degrades B1 | Monitor Anthropic's release notes for Desktop App improvements. Upgrade to B2 (Claude.ai + tunnel) if instability is persistent, or fall back to Architecture A. |
| Tunnel service unreliable for sustained use (B2 only) | Medium | Medium — degrades B2 | Does not affect B1 (no tunnel). For B2: evaluate multiple tunnel providers; Tailscale Funnel may be more reliable for personal use than ngrok. Fall back to B1 if tunnel proves unreliable. |
| Claude Code Desktop is discontinued or deprioritized | Low | High — blocks Architecture A | Architecture A's skill also works in Claude Code CLI. Build Architecture C as fallback. |
| MCP protocol undergoes breaking changes | Medium | Medium — requires bridge updates | Pin to stable MCP SDK versions; the bridge is small enough to update quickly. |
| Stateful memory skill produces low-quality memories (Architecture A only) | Medium | Medium — defeats the purpose | Iterate on prompts; add user-facing memory review/edit commands. Markdown format makes manual correction easy. Does not affect Architecture B (uses built-in memory). |
| Security incident via MCP bridge (unintended file access/command execution) | Low | High | Strict allowlists, operation logging, optional confirmation prompts for destructive operations. Run the bridge under a restricted user account. B1 has lower risk than B2 (no network exposure). |
| Context window consumed by memory skill reduces conversation quality (Architecture A only) | Medium | Medium | Aggressive summarization in `core.md` and `index.md`. Load content blocks on demand only. Does not affect Architecture B (uses built-in memory). |

## Relation to Existing Design

This proposal is a **companion to** the [Stateful Agent Skill Design Document](stateful-agent-skill-design.md), not a replacement for it. The design document specifies *how the memory skill works internally* (three-tier model, markdown storage, pluggable backends, session lifecycle). This proposal specifies *which Claude environment to run it in* and *what additional infrastructure is needed* to satisfy the full set of requirements.

The key design decisions from the existing document that carry forward:

- **Three-tier memory model** (core, index, content blocks) — used in Architectures A, C, and D.
- **Markdown storage** — unchanged; the format works in all architectures.
- **GitHub API backend** — critical for Architecture A (primary persistence) and useful for Architecture B (memory backup/migration).
- **Pluggable backends** — the backend interface makes it straightforward to add new backends (e.g., an MCP-aware backend for Architecture B).

The one piece of the design document that becomes unnecessary in Architecture B is the memory skill itself — both the Claude Desktop App (B1) and Claude.ai (B2) provide built-in memory that replaces the skill-based approach. However, the three-tier model and markdown format could still be valuable as a *supplementary* knowledge store (e.g., for project-specific context that exceeds what Anthropic's built-in memory is designed to hold), accessible to Claude via the MCP bridge's filesystem tools.

## Open Questions

1. **MCP tunnel security (B2 only):** Architecture B2 requires a tunnel service to make the local MCP server reachable from Claude.ai. What are the security implications of exposing local filesystem and command execution behind a public URL? Cloudflare Tunnel offers access policies and authentication; ngrok offers IP allowlisting and webhook verification. Which approach provides the best security-to-convenience tradeoff? Note: This question does not apply to B1, which uses stdio with no network exposure.

2. **Custom connector limitations (B2 only):** Claude.ai's custom connector support is relatively new. Are there rate limits, timeout restrictions, or tool-count limits that could constrain the MCP bridge's usefulness? The help docs mention that Advanced Research cannot invoke tools from connectors — are there other feature restrictions? Note: This question does not apply to B1, which uses the Desktop App's native MCP support.

3. **Desktop App MCP limitations (B1 only):** Are there tool-count limits, timeout restrictions, or other constraints on local MCP servers in the Claude Desktop App? How does the Desktop App handle MCP server crashes or restarts? Can the Desktop App be configured to auto-reconnect to a restarted MCP server?

4. **Memory migration:** If starting with Architecture A (skill-based memory) and transitioning to Architecture B (built-in memory), how do we migrate the accumulated markdown memory into Anthropic's built-in system? Is there a way to "seed" built-in memory from structured data?

5. **MCP authentication best practices (B2 only):** Claude.ai's custom connector flow supports OAuth 2.1 with optional client ID and secret. For a personal MCP bridge server, is full OAuth overkill? Would a simpler shared-secret approach suffice, or does the tunnel service's own authentication layer (e.g., Cloudflare Access) make application-level auth unnecessary? Note: B1 does not need authentication since the bridge is only accessible to the local Desktop App process.

6. **Desktop App UI convergence:** The Claude Desktop App already supports local MCP servers via stdio, which is what makes B1 possible without a tunnel. Is Anthropic actively working to converge the Desktop App's UI with Claude.ai's (artifacts, tool widgets, cloud VM features)? If the gap narrows significantly, B1 becomes the clear winner over B2 with no meaningful tradeoff.

7. **Memory skill as supplementary store:** Even with Architecture B, is there value in keeping the three-tier markdown memory system as a supplementary knowledge store? Anthropic's built-in memory is opaque and has limited capacity. A transparent, user-controlled supplementary store (accessible via the MCP bridge) could hold project context, technical notes, and other detailed information that exceeds what built-in memory is designed for.
