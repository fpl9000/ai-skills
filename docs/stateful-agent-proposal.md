# Proposal: Claude as a Stateful Agent with Full Local Access

**Version:** 0.1 (Draft)
**Date:** February 2026
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

The goal is to use Claude — accessed through Anthropic's own UIs rather than a custom harness like LettaBot — as a **stateful agent** with persistent memory, full local system access (filesystem, network, command execution), and a graphical user interface. No single Claude environment currently provides all of these capabilities simultaneously. This proposal evaluates four architectures that bridge the gaps, with a recommendation to pursue **Architecture B** (Claude.ai + Local MCP Bridge) as the primary strategy, with **Architecture A** (Claude Code Desktop + Stateful Memory Skill) as an interim solution available today.

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
| **R2: Local filesystem** | ❌ Cloud VM only | ⚠️ Read-only | ✅ Full | ✅ Full |
| **R3: Local network** | ❌ Cloud VM only | ❌ Cloud VM only | ✅ Full | ✅ Full |
| **R4: Local commands** | ❌ Cloud VM only | ❌ Cloud VM only | ✅ Full | ✅ Full |
| **R5: Graphical UI** | ✅ Rich web UI | ✅ Rich desktop UI | ❌ Terminal only | ✅ GUI wrapper |
| **MCP server support** | ❌ Not yet | ✅ Yes | ✅ Yes | ✅ Yes |
| **Skills support** | ✅ Yes | ❌ No | ✅ Yes | ✅ Yes |

Key observations:

- **Claude.ai** has the best memory and the best UI, but is completely isolated from the local machine.
- **Claude Code Desktop** has the best local access and has a GUI, but lacks persistent memory and lacks certain rich UI features (artifacts, file previews, tool widgets).
- **Claude Desktop App** can read local files via MCP, but command execution and network access still happen on the cloud VM, limiting its usefulness.
- The **MCP protocol** is the most promising bridge between Claude's cloud-based UIs and local machine capabilities, but Claude.ai does not yet support user-configured MCP servers (the Desktop App does).

The central tension is: **memory and rich UI live in the cloud; local access lives on the user's machine.** Every architecture below is a strategy for bridging that gap.

## Proposed Architectures

### Architecture A: Claude Code Desktop + Stateful Memory Skill

**Strategy:** Use the environment that already has full local access and a GUI, then add the missing piece (persistent memory) via the stateful memory skill described in the [existing design document](stateful-agent-skill-design.md).

```
┌──────────────────────────────────────────────────┐
│            Claude Code Desktop (GUI)              │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │  Stateful Memory Skill                      │  │
│  │  ┌────────┐ ┌────────┐ ┌────────────────┐   │  │
│  │  │Core.md │ │Index.md│ │ blocks/*.md    │   │  │
│  │  └────────┘ └────────┘ └────────────────┘   │  │
│  │         │         │             │            │  │
│  │         └─────────┼─────────────┘            │  │
│  │                   ▼                          │  │
│  │        GitHub API (persistence)              │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  Local filesystem ✅  Local network ✅             │
│  Local commands ✅    GUI ✅ (basic)               │
│  Persistent memory ✅ (via skill)                  │
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

**Strategy:** Use Claude.ai for its superior UI and built-in memory, and run a local MCP (Model Context Protocol) server that bridges the gap to local filesystem, network, and command execution.

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude.ai (Web UI)                       │
│                                                              │
│  Built-in memory ✅    Rich UI ✅    Artifacts ✅             │
│  Tool widgets ✅       File previews ✅                       │
│                                                              │
│           │  MCP Protocol (WebSocket/SSE)                    │
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
│  Persistent memory ✅ (built-in)                              │
│  Local filesystem ✅ (via MCP)                                │
│  Local network ✅ (via MCP)                                   │
│  Local commands ✅ (via MCP)                                  │
│  GUI ✅ (Claude.ai's full-featured web UI)                    │
└─────────────────────────────────────────────────────────────┘
```

**How it works:**

1. A lightweight MCP server runs on the user's local machine as a long-lived background process (daemon/service).
2. The MCP server exposes tools for filesystem operations, network requests, and command execution over the MCP protocol.
3. Claude.ai connects to this MCP server (once Claude.ai supports user-configured remote MCP servers, which is on Anthropic's roadmap).
4. Claude uses these MCP tools just as it uses any other tool — making tool calls that are routed through the MCP bridge to the local machine.
5. Claude.ai's built-in memory system handles persistence automatically.

**The MCP bridge server** would be a relatively simple program (likely written in TypeScript or Python, since MCP SDKs exist for both) that:

- Listens for MCP connections on a local port.
- Optionally uses a secure tunnel (e.g., Cloudflare Tunnel, ngrok, or Tailscale Funnel) to make the local server reachable from the cloud, OR Anthropic provides a native mechanism for Claude.ai to connect to locally-hosted MCP servers.
- Implements a configurable allowlist of permitted directories, commands, and network destinations (for security).
- Logs all operations for auditability.

**Pros:**
- Best possible UI — Claude.ai's full web interface with artifacts, widgets, and rich rendering.
- Best possible memory — Anthropic's built-in memory system, which is tuned and maintained by Anthropic.
- Clean separation of concerns: Claude handles reasoning and conversation; the MCP bridge handles local access.
- The MCP bridge is a general-purpose tool — once built, it benefits all MCP-compatible AI agents, not just Claude.
- No context window overhead for memory (unlike Architecture A's skill-based approach).
- The bridge server can be hardened with allowlists and logging, providing a security boundary.

**Cons:**
- **Blocked on Anthropic:** Claude.ai does not yet support user-configured remote MCP servers. The Claude Desktop App does, but it lacks some of Claude.ai's UI features. This is the biggest risk — the timeline is uncertain.
- Requires running a persistent local service, which adds operational complexity.
- The connection between Claude.ai (cloud) and the local MCP server introduces latency and requires a reliable network path. If using a tunnel service, there is an additional dependency.
- Security surface: exposing local filesystem and command execution to a cloud service requires careful access controls. A misconfigured bridge could be dangerous.
- MCP protocol is still evolving. Breaking changes in the protocol could require bridge updates.

**Verdict:** This is the **ideal long-term architecture**. It combines the best UI, the best memory, and full local access. The blocking dependency is Claude.ai's MCP support, which is under active development at Anthropic. In the meantime, the Claude Desktop App can serve as a partial substitute (it supports MCP but has a less feature-rich UI than Claude.ai).

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
| **Available today** | ✅ Yes | ⚠️ Partial (Desktop App only) | ⚠️ Requires dev work | ✅ Yes (manual) |
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

### Short-term (Now): Architecture A

**Use Claude Code Desktop with the Stateful Memory Skill.**

This is available today and satisfies all five requirements. The UI is less polished than Claude.ai, and the memory system requires context window space, but it works. Build the stateful memory skill as described in the [existing design document](stateful-agent-skill-design.md), targeting Claude Code Desktop as the primary environment.

Specific actions:

1. **Implement the stateful memory skill** with the `filesystem` backend for local persistence and `github_api` backend for backup/sync.
2. **Configure Claude Code Desktop** with the skill loaded on startup.
3. **Establish a GitHub repo** (e.g., `fpl9000/agent-memory`) for memory persistence and version history.
4. **Iterate on memory quality** — tune the skill's prompts to produce useful, well-structured memories.

### Medium-term (3–6 months): Transition to Architecture B

**Monitor Anthropic's MCP rollout for Claude.ai and prepare a local MCP bridge server.**

As Claude.ai gains support for user-configured MCP servers (or as the Claude Desktop App's UI catches up to Claude.ai), transition to Architecture B.

Specific actions:

1. **Build the local MCP bridge server** in advance. Use the TypeScript MCP SDK. Implement filesystem, network, and command execution tools with configurable allowlists.
2. **Test with Claude Desktop App** (which already supports MCP) to validate the bridge server before Claude.ai support arrives.
3. **When Claude.ai supports MCP**, connect the bridge server and migrate the primary workflow from Claude Code Desktop to Claude.ai.
4. **Retire the stateful memory skill** — Claude.ai's built-in memory replaces it.

### Long-term (6–12 months): Full Integration

Anthropic is actively developing memory, MCP, and tool integration features. The long-term trajectory is that Claude.ai will natively support the kind of local access that currently requires workarounds. At that point, the local MCP bridge server becomes the only piece of custom infrastructure — a clean, maintainable, general-purpose tool.

## Implementation Roadmap

```
2026 Q1 (Now)
├── Implement stateful memory skill (per existing design doc)
├── Set up agent-memory GitHub repo
├── Configure Claude Code Desktop as primary environment
└── Begin using the system for daily work

2026 Q2
├── Build local MCP bridge server (TypeScript)
│   ├── Filesystem tools (read, write, list, search)
│   ├── Network tools (HTTP requests, curl-equivalent)
│   ├── Command execution tools (run_command, run_script)
│   └── Security: allowlists, logging, confirmation prompts
├── Test MCP bridge with Claude Desktop App
└── Monitor Anthropic announcements re: Claude.ai MCP support

2026 Q3
├── If Claude.ai supports MCP: migrate primary workflow
├── If not: continue with Claude Code Desktop + skill
├── Evaluate: has Anthropic's built-in memory improved enough
│   to retire the skill?
└── Contribute MCP bridge server as open-source project

2026 Q4
├── Full Architecture B deployment (if MCP available)
├── Retire stateful memory skill if built-in memory is sufficient
└── Evaluate emerging capabilities (agentic browsing, etc.)
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Anthropic delays Claude.ai MCP support | Medium | High — blocks Architecture B | Continue with Architecture A; it works today. |
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

1. **MCP tunnel security:** If Architecture B requires a tunnel service (ngrok, Cloudflare Tunnel) to make the local MCP server reachable from Claude.ai, what are the security implications? Is there a way for Anthropic to support locally-hosted MCP servers without a public tunnel (e.g., a browser extension or desktop agent that acts as a local relay)?

2. **Memory migration:** When transitioning from Architecture A (skill-based memory) to Architecture B (built-in memory), how do we migrate the accumulated markdown memory into Anthropic's built-in system? Is there a way to "seed" built-in memory from structured data?

3. **Claude Desktop App trajectory:** Is the Claude Desktop App converging with Claude.ai in terms of UI features? If so, Architecture B could become viable sooner using the Desktop App instead of waiting for Claude.ai MCP support.

4. **MCP authentication:** How will Claude.ai authenticate with user-hosted MCP servers? Shared secrets? OAuth? Mutual TLS? This affects the security architecture of the bridge server.

5. **Anthropic's own plans for local access:** Is Anthropic working on native local access features for Claude.ai (beyond MCP)? If so, the local MCP bridge may become unnecessary, simplifying the architecture further.

6. **Memory skill as supplementary store:** Even after transitioning to Architecture B, is there value in keeping the three-tier markdown memory system as a supplementary knowledge store? Anthropic's built-in memory is opaque and has limited capacity. A transparent, user-controlled supplementary store could hold project context, technical notes, and other detailed information that exceeds what built-in memory is designed for.
