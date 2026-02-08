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
  - [Architecture B: Claude.ai + Local MCP Bridge](#architecture-b-claudeai--local-mcp-bridge)
  - [Architecture C: Claude Code CLI + Web Terminal UI](#architecture-c-claude-code-cli--web-terminal-ui)
  - [Architecture D: Hybrid — Claude.ai Primary with Local Agent Sidecar](#architecture-d-hybrid--claudeai-primary-with-local-agent-sidecar)
- [Architecture Comparison](#architecture-comparison)
- [Recommendation](#recommendation)
- [Implementation Roadmap](#implementation-roadmap)
- [Risks and Mitigations](#risks-and-mitigations)
- [Relation to Existing Design](#relation-to-existing-design)
- [Open Questions](#open-questions)

## Executive Summary

The goal is to use Claude — accessed through Anthropic's own UIs rather than a custom harness like LettaBot — as a **stateful agent** with persistent memory, full local system access (filesystem, network, command execution), and a graphical user interface. No single Claude environment currently provides all of these capabilities simultaneously. This proposal evaluates four architectures that bridge the gaps, with a recommendation to pursue **Architecture B** (Claude.ai + Local MCP Bridge) as the primary strategy — which is achievable today using Claude.ai's existing custom connector support — with **Architecture A** (Claude Code Desktop + Stateful Memory Skill) as a fallback if the tunnel-based approach proves unreliable.

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
|------------|:---------------:|:------------------:|:---------------:|:-------------------:|
| **R1: Persistent memory** | ✅ Built-in | ✅ Built-in | ❌ None | ❌ None |
| **R2: Local filesystem** | ❌ Cloud VM only | ✅ Full | ✅ Full | ✅ Full |
| **R3: Local network** | ❌ Cloud VM only | ❌ Cloud VM only | ✅ Full | ✅ Full |
| **R4: Local commands** | ❌ Cloud VM only | ❌ Cloud VM only | ✅ Full | ✅ Full |
| **R5: Graphical UI** | ✅ Rich web UI | ✅ Rich desktop UI | ❌ Terminal only | ✅ GUI wrapper |
| **MCP server support** | ✅ Remote only | ✅ Remote + Local | ✅ Remote + Local | ✅ Remote + Local |
| **Skills support** | ✅ Yes | ❌ No | ✅ Yes | ✅ Yes |

Key observations:

- **Claude.ai** has the best memory and the best UI, but is completely isolated from the local machine. It supports **remote** MCP servers via the "Connectors" feature (Settings > Connectors), including custom connectors where you provide a remote MCP server URL. However, it cannot connect to **locally-running** MCP servers directly — the server must be reachable over the network.
- **Claude Code Desktop** has the best local access and has a GUI, but lacks persistent memory and lacks certain rich UI features (artifacts, file previews, tool widgets).
- **Claude Desktop App** supports both remote and local MCP servers, but command execution and network access still happen on the cloud VM (not locally), limiting its usefulness for local operations.
- The **MCP protocol** is the most promising bridge between Claude's cloud-based UIs and local machine capabilities. Claude.ai already supports remote MCP servers. The remaining challenge for local access is making a locally-running MCP server reachable from the cloud (via a tunnel service like Cloudflare Tunnel, ngrok, or Tailscale Funnel).

The central tension is: **memory and rich UI live in the cloud; local access lives on the user's machine.** Every architecture below is a strategy for bridging that gap.

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

### Architecture B: Claude.ai + Local MCP Bridge

**Strategy:** Use Claude.ai for its superior UI and built-in memory, and run a local MCP server that bridges the gap to local filesystem, network, and command execution. Claude.ai already supports custom remote MCP servers via the "Connectors" feature (Settings > Connectors > Add custom connector), so the primary engineering task is making a locally-running MCP server reachable from the cloud via a secure tunnel.

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
│  │        (runs on user's machine)                   │        │
│  │                                                   │        │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │        │
│  │  │Filesystem│  │ Network  │  │Command Exec   │   │        │
│  │  │  Tools   │  │  Tools   │  │   Tools       │   │        │
│  │  └──────────┘  └──────────┘  └───────────────┘   │        │
│  │                                                   │        │
│  │  Exposed as MCP tool endpoints:                   │        │
│  │  - read_file, write_file, list_dir               │        │
│  │  - http_get, http_post, curl                     │        │
│  │  - run_command, run_script                       │        │
│  └──────────────────────────────────────────────────┘        │
│                                                              │
│  User's Local Machine                                        │
│  Local filesystem ✅  Local network ✅  Local commands ✅    │
└──────────────────────────────────────────────────────────────┘
```

**How it works:**

1. A lightweight MCP server runs on the user's local machine as a long-lived background process (daemon/service).
2. The MCP server exposes tools for filesystem operations, network requests, and command execution over the MCP protocol using Streamable HTTP transport.
3. A secure tunnel service (Cloudflare Tunnel, ngrok, or Tailscale Funnel) makes the local MCP server reachable at a stable public URL.
4. The user adds this URL as a custom connector in Claude.ai (Settings > Connectors > Add custom connector). This only needs to be done once.
5. Claude uses these MCP tools just as it uses any other connector tool — making tool calls that are routed through the tunnel to the local MCP bridge server.
6. Claude.ai's built-in memory system handles persistence automatically.

**The MCP bridge server** would be a relatively simple program (likely written in TypeScript or Python, since MCP SDKs exist for both) that:

- Implements the MCP protocol over Streamable HTTP (the transport Claude.ai's Connectors feature uses for remote servers).
- Listens on a local port, fronted by a secure tunnel for cloud reachability.
- Implements a configurable allowlist of permitted directories, commands, and network destinations (for security).
- Optionally supports OAuth 2.1 authentication (Claude.ai's custom connector flow supports OAuth) for access control.
- Logs all operations for auditability.

**Pros:**
- Best possible UI — Claude.ai's full web interface with artifacts, widgets, and rich rendering.
- Best possible memory — Anthropic's built-in memory system, which is tuned and maintained by Anthropic.
- Clean separation of concerns: Claude handles reasoning and conversation; the MCP bridge handles local access.
- The MCP bridge is a general-purpose tool — once built, it benefits all MCP-compatible AI agents, not just Claude.
- No context window overhead for memory (unlike Architecture A's skill-based approach).
- The bridge server can be hardened with allowlists and logging, providing a security boundary.

**Cons:**
- Requires running a persistent local service (the MCP bridge) and a tunnel service, which adds operational complexity. If the tunnel goes down, Claude.ai loses access to local tools.
- The connection between Claude.ai (cloud) and the local MCP server introduces latency (typically 50–200ms round-trip through a tunnel) and requires a reliable network path.
- Security surface: exposing local filesystem and command execution to a cloud-reachable endpoint requires careful access controls. A misconfigured bridge or tunnel could be dangerous. OAuth 2.1 support and strict allowlists are essential.
- MCP protocol is still evolving. Breaking changes in the protocol could require bridge updates.
- Tunnel services (ngrok, Cloudflare Tunnel) may have their own reliability, rate-limiting, or cost considerations for sustained use.

**Verdict:** This is the **ideal architecture** and is **achievable today**. Claude.ai already supports custom remote MCP servers via the Connectors feature. The remaining engineering work is building the local MCP bridge server and configuring a secure tunnel. This combines the best UI, the best memory, and full local access with a relatively small amount of custom infrastructure.

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
4. Over time, as MCP support matures, the coordination could become seamless — the Claude.ai session could invoke the local sidecar's tools directly.

**Coordination mechanisms (from manual to automated):**

| Mechanism | Effort | Seamlessness |
|-----------|--------|--------------|
| **Copy-paste** | None | Low — manual context-switching |
| **Shared filesystem** (e.g., Dropbox/OneDrive folder) | Minimal | Medium — Claude.ai can read uploaded files |
| **GitHub as intermediary** | Minimal | Medium — both agents can access GitHub |
| **Local webhook/API** | Moderate | High — Claude.ai triggers local work via API call |
| **MCP bridge** (future) | Moderate | Highest — native tool integration |

**Pros:**
- Uses the best UI (Claude.ai) and the best memory (built-in) for the primary conversation.
- Local access is available when needed, without compromising the primary experience.
- Gradual migration path: starts manual, becomes more automated as MCP matures.
- The sidecar agent can be specialized — loaded with skills for local operations, while the primary agent focuses on conversation and reasoning.

**Cons:**
- Context-switching between two interfaces is friction-heavy and error-prone.
- The two agents do not share context automatically. The Claude.ai agent and the local agent are separate conversations with separate memories.
- Manual coordination (copy-paste) is tedious for frequent local operations.
- Even with automated coordination, there is inherent latency and complexity in a two-agent system.
- The user must maintain two mental models of what each agent knows.

**Verdict:** This is a **transitional architecture** — useful if you primarily need Claude.ai's UI and memory, and only occasionally need local access. It becomes more attractive as MCP support matures and coordination becomes automated. It is not ideal for workflows that require frequent local operations.

## Architecture Comparison

| Criterion | A: CC Desktop + Skill | B: Claude.ai + MCP | C: CLI + Web UI | D: Hybrid Sidecar |
|-----------|:--------------------:|:------------------:|:---------------:|:-----------------:|
| **Available today** | ✅ Yes | ✅ Yes (needs MCP bridge + tunnel) | ⚠️ Requires dev work | ✅ Yes (manual) |
| **R1: Persistent memory** | ⚠️ Skill-based | ✅ Built-in | ⚠️ Skill-based | ✅ Built-in (primary) |
| **R2: Local filesystem** | ✅ Native | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R3: Local network** | ✅ Native | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R4: Local commands** | ✅ Native | ✅ Via MCP | ✅ Native | ✅ Via sidecar |
| **R5: Graphical UI** | ⚠️ Basic GUI | ✅ Best-in-class | ⚠️ Terminal-grade | ✅ Best-in-class |
| **Context window cost** | ⚠️ Skill overhead | ✅ None | ⚠️ Skill overhead | ✅ Minimal |
| **Setup complexity** | Low | Moderate | High | Low–Moderate |
| **Maintenance burden** | Low | Low–Moderate | High | Moderate |
| **Future-proof** | ⚠️ May be superseded | ✅ Aligned with Anthropic's direction | ❌ Custom dead-end | ⚠️ Transitional |

## Recommendation

### Primary Strategy (Now): Architecture B

**Build a local MCP bridge server and connect it to Claude.ai via a secure tunnel.**

Since Claude.ai already supports custom remote MCP servers via the Connectors feature, Architecture B is achievable today. This provides the best UI, the best memory, and full local access. The engineering work is building the MCP bridge server and configuring a tunnel.

Specific actions:

1. **Build the local MCP bridge server** using the TypeScript or Python MCP SDK. Implement Streamable HTTP transport with tools for filesystem operations, network requests, and command execution.
2. **Configure a secure tunnel** (Cloudflare Tunnel is recommended for stability and zero-cost for personal use; ngrok or Tailscale Funnel are alternatives) to expose the local MCP server at a stable URL.
3. **Add the tunnel URL as a custom connector** in Claude.ai (Settings > Connectors > Add custom connector).
4. **Implement security controls**: directory allowlists, command allowlists, operation logging, and optionally OAuth 2.1 authentication.
5. **Test and iterate** on the tool set — start with filesystem and command execution, then add network tools as needed.

### Fallback Strategy: Architecture A

**If the MCP bridge + tunnel approach proves unreliable, fall back to Claude Code Desktop with the Stateful Memory Skill.**

Architecture A requires no networking infrastructure and works entirely locally. It is simpler to set up but has a less polished UI and requires the memory skill to consume context window space.

Specific actions:

1. **Implement the stateful memory skill** with the `filesystem` backend for local persistence and `github_api` backend for backup/sync.
2. **Configure Claude Code Desktop** with the skill loaded on startup.
3. **Establish a GitHub repo** (e.g., `fpl9000/agent-memory`) for memory persistence and version history.

### Long-term (6–12 months): Simplification

Anthropic is actively developing memory, MCP, and tool integration features (including MCP Apps for interactive in-conversation UIs, announced January 2026). The long-term trajectory is that the MCP bridge server becomes the only piece of custom infrastructure — a clean, maintainable, general-purpose tool. As Anthropic's built-in memory improves, the supplementary memory skill (if used) may become unnecessary.

## Implementation Roadmap

```
2026 Q1 (Now)
├── Build local MCP bridge server (TypeScript or Python)
│   ├── Filesystem tools (read, write, list, search)
│   ├── Command execution tools (run_command, run_script)
│   └── Security: directory/command allowlists, operation logging
├── Configure secure tunnel (Cloudflare Tunnel recommended)
├── Add tunnel URL as custom connector in Claude.ai
├── Test end-to-end: Claude.ai → tunnel → MCP bridge → local operations
└── Begin using Architecture B for daily work

2026 Q2
├── Expand MCP bridge tool set
│   ├── Network tools (HTTP requests, curl-equivalent)
│   ├── OAuth 2.1 authentication for the bridge endpoint
│   └── Optional: confirmation prompts for destructive operations
├── Evaluate tunnel reliability and latency over sustained use
├── If tunnel approach is unreliable: implement Architecture A fallback
│   ├── Stateful memory skill (per existing design doc)
│   └── Claude Code Desktop as alternative environment
└── Contribute MCP bridge server as open-source project

2026 Q3–Q4
├── Evaluate Anthropic's evolving MCP Apps support
├── Evaluate built-in memory improvements
├── Assess whether supplementary memory skill adds value
└── Evaluate emerging capabilities (agentic browsing, etc.)
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Tunnel service unreliable for sustained use | Medium | Medium — degrades Architecture B | Evaluate multiple tunnel providers; fall back to Architecture A if needed. Tailscale Funnel may be more reliable for personal use than ngrok. |
| Claude Code Desktop is discontinued or deprioritized | Low | High — blocks Architecture A | Architecture A's skill also works in Claude Code CLI. Build Architecture C as fallback. |
| MCP protocol undergoes breaking changes | Medium | Medium — requires bridge updates | Pin to stable MCP SDK versions; the bridge is small enough to update quickly. |
| Stateful memory skill produces low-quality memories | Medium | Medium — defeats the purpose | Iterate on prompts; add user-facing memory review/edit commands. Markdown format makes manual correction easy. |
| Security incident via MCP bridge (unintended file access/command execution) | Low | High | Strict allowlists, operation logging, optional confirmation prompts for destructive operations. Run the bridge under a restricted user account. |
| Context window consumed by memory skill reduces conversation quality | Medium | Medium | Aggressive summarization in `core.md` and `index.md`. Load content blocks on demand only. Monitor and tune. |

## Relation to Existing Design

This proposal is a **companion to** the [Stateful Agent Skill Design Document](stateful-agent-skill-design.md), not a replacement for it. The design document specifies *how the memory skill works internally* (three-tier model, markdown storage, pluggable backends, session lifecycle). This proposal specifies *which Claude environment to run it in* and *what additional infrastructure is needed* to satisfy the full set of requirements.

The key design decisions from the existing document that carry forward:

- **Three-tier memory model** (core, index, content blocks) — used in Architectures A, C, and D.
- **Markdown storage** — unchanged; the format works in all architectures.
- **GitHub API backend** — critical for Architecture A (primary persistence) and useful for Architecture B (memory backup/migration).
- **Pluggable backends** — the backend interface makes it straightforward to add new backends (e.g., an MCP-aware backend for Architecture B).

The one piece of the design document that becomes unnecessary in Architecture B is the memory skill itself — Claude.ai's built-in memory replaces it. However, the three-tier model and markdown format could still be valuable as a *supplementary* knowledge store (e.g., for project-specific context that exceeds what Anthropic's built-in memory is designed to hold).

## Open Questions

1. **MCP tunnel security:** Architecture B requires a tunnel service to make the local MCP server reachable from Claude.ai. What are the security implications of exposing local filesystem and command execution behind a public URL? Cloudflare Tunnel offers access policies and authentication; ngrok offers IP allowlisting and webhook verification. Which approach provides the best security-to-convenience tradeoff? Is there a way for Anthropic to eventually support locally-hosted MCP servers without a public tunnel (e.g., a browser extension or desktop relay agent)?

2. **Custom connector limitations:** Claude.ai's custom connector support is relatively new. Are there rate limits, timeout restrictions, or tool-count limits that could constrain the MCP bridge's usefulness? The help docs mention that Advanced Research cannot invoke tools from connectors — are there other feature restrictions?

3. **Memory migration:** If starting with Architecture A (skill-based memory) and transitioning to Architecture B (built-in memory), how do we migrate the accumulated markdown memory into Anthropic's built-in system? Is there a way to "seed" built-in memory from structured data?

4. **MCP authentication best practices:** Claude.ai's custom connector flow supports OAuth 2.1 with optional client ID and secret. For a personal MCP bridge server, is full OAuth overkill? Would a simpler shared-secret approach suffice, or does the tunnel service's own authentication layer (e.g., Cloudflare Access) make application-level auth unnecessary?

5. **Anthropic's own plans for local access:** Is Anthropic working on native local access features for Claude.ai (beyond MCP)? The Claude Desktop App already supports local MCP servers via stdio — if the Desktop App's UI converges with Claude.ai, the tunnel requirement could be eliminated entirely.

6. **Memory skill as supplementary store:** Even with Architecture B, is there value in keeping the three-tier markdown memory system as a supplementary knowledge store? Anthropic's built-in memory is opaque and has limited capacity. A transparent, user-controlled supplementary store (accessible via the MCP bridge) could hold project context, technical notes, and other detailed information that exceeds what built-in memory is designed for.
