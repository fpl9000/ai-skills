# Stateful Agent System: Detailed Design – Chapter 7

**Version:** 2.0  
**Date:** February - June 2026  
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)  
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.

## Contents

- [7. Build and Deployment](#7-build-and-deployment)
  - [7.1 Build the Bridge](#71-build-the-bridge)
  - [7.2 Claude Desktop Configuration](#72-claude-desktop-configuration)
  - [7.3 Filesystem Extension Configuration](#73-filesystem-extension-configuration)
  - [7.4 Memory Directory Setup](#74-memory-directory-setup)
  - [7.5 Initial Memory Seeding](#75-initial-memory-seeding)
  - [7.6 Skill Installation](#76-skill-installation)
  - [7.7 CLAUDE.md Update](#77-claudemd-update)
  - [7.8 Claude Code Deployment](#78-claude-code-deployment)
  - [7.9 Running Multiple Clients Concurrently](#79-running-multiple-clients-concurrently)

## 7. Build and Deployment

### 7.1 Build the Bridge

```bash
# Clone the repo
cd C:\franl\git
git clone https://github.com/fpl9000/mcp-bridge

# Build (produces single static binary)
cd mcp-bridge
go build -o mcp-bridge.exe .

# Verify
./mcp-bridge.exe --version
```

No CGO, no external dependencies. The binary is self-contained.

Install the bridge with these Bash commands:

```bash
$ mkdir -p ~/.claude-agent-memory/bin
$ cp mcp-bridge.exe ~/.claude-agent-memory/bin
```

### 7.2 Claude Desktop Configuration

Edit Claude Desktop's MCP configuration file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **MacOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json` (no official support for Claude Desktop on Linux)

Add the bridge server entry:

```json
{
  "mcpServers": {
    "mcp-bridge": {
      "command": "C:\\franl\\.claude-agent-memory\\bin\\mcp-bridge\\mcp-bridge.exe",
      "args": ["--config", "C:\\franl\\.claude-agent-memory\\bridge-config.yaml"]
    }
  }
}
```

The Desktop App will launch the bridge as a subprocess on startup, communicating via stdio.

If any other MCP client will also run the bridge against the same memory root, add
`"--client-id", "desktop"` to `args` — see [Section 7.9](#79-running-multiple-clients-concurrently)
and [Chapter 3, Section 3.25.4](stateful-agent-design-chapter3.md#3254-per-client-state-files). The
value defaults to `desktop`, so a Desktop-only deployment may omit it.

**Note:** The Filesystem extension does **not** appear in `claude_desktop_config.json` and should **not** be added there. It is a first-party Claude Desktop extension developed by Anthropic and distributed through Claude Desktop's built-in extensions gallery (Settings > Extensions). It is installed, enabled, and configured entirely through the Claude Desktop UI — not via the config JSON file. Claude Desktop manages its configuration for first-party extensions through a separate internal store. See the resolution of Open Question #6 for details.

### 7.3 Filesystem Extension Configuration

The Filesystem extension is enabled and configured via Claude Desktop's Extensions UI (Settings > Extensions > Filesystem > Configure). The allowed directories (e.g., `C:\franl`, `C:\temp`, `C:\apps`) are set there, not in `claude_desktop_config.json`.

The memory directory (`C:\franl\.claude-agent-memory`) is covered because it is a subdirectory of `C:\franl`, which is already an allowed directory. No additional configuration is needed.

### 7.4 Memory Directory Setup

Create the directory structure:

```bash
mkdir -p C:/franl/.claude-agent-memory/blocks
```

Create the bridge configuration file (`bridge-config.yaml`) with the schema defined in [Section 3.2](stateful-agent-design-chapter3.md#32-configuration).

### 7.5 Initial Memory Seeding

The first time the memory system is used, Claude will find an empty memory store: `memory_start_conversation` returns empty `core` content and an empty derived index. The skill instructions handle this: "If the core content is empty, this is a first-run scenario."

However, it's better to pre-seed the memory with initial content derived from existing knowledge. This avoids a cold-start problem where Claude's first session has no Layer 2 context.

**Seeding approach:**

1. Manually create `core.md` with basic identity and project information (copy from Layer 1 memory or from conversation history). Note that `core.md` has no YAML frontmatter — it is not an indexed block.
2. Optionally create initial project blocks in `blocks\`. If creating blocks by hand, include the bridge's YAML frontmatter (`summary` and `updated_at` fields) so they appear correctly in the derived index — or simpler, let Claude create them via `memory_write_block`, which generates the frontmatter automatically.
3. The episodic log will be created automatically on the first `memory_append_episodic` call.

There is no index file to create: the index is derived on demand from block frontmatter (see [Chapter 4, Section 4.4](stateful-agent-design-chapter4.md#44-the-derived-index)).

Alternatively, ask Claude in an initial conversation to seed the memory from its Layer 1 knowledge: "Please seed the memory system's core and initial blocks using what you know about me from your built-in memory." Claude will use `memory_write_core` and `memory_write_block`, and the index follows automatically.

### 7.6 Skill Installation

1. Create the `SKILL.md` file with the content from [Section 5.2](stateful-agent-design-chapter5.md#52-skillmd-content), including its YAML frontmatter.
2. Place it inside a folder whose name matches the skill's `name`, then zip the folder so the archive contains `stateful-memory/SKILL.md` (not a bare `SKILL.md` at the root):
   ```bash
   mkdir stateful-memory
   cp SKILL.md stateful-memory/
   zip -r stateful-memory.zip stateful-memory
   ```
3. Upload via Claude Desktop > Customize > Skills > "+" > "Upload a skill", then toggle the skill on. (Skills require **Code execution and file creation** to be enabled under Settings > Capabilities; if it is off, the Skills section is hidden.)

### 7.7 CLAUDE.md Update

Replace the current `C:\Users\flitt\.claude\CLAUDE.md` with the lean sub-agent-optimized version described in [Section 6.5](stateful-agent-design-chapter6.md#65-claudemd-recommendations) and the proposal. Move credentials to environment variables. Move service-specific instructions to `spawn_agent` system_prompt parameters.

### 7.8 Claude Code Deployment

Claude Code is a supported client alongside Claude Desktop. It acts as an MCP client over the same
stdio transport, so **the bridge binary requires no changes** to run under it; what differs is
registration, skill installation, and the concurrency configuration of
[Section 7.9](#79-running-multiple-clients-concurrently).

**Register the bridge.** Claude Code stores MCP server configuration at three scopes: `local`
(private to you, tied to one project), `project` (`.mcp.json` at the repository root, intended to
be committed and shared), and `user` (global across all your projects). Memory is a personal,
cross-project facility, so `user` scope is the correct choice — a project-scoped registration would
make memory available only inside one repository, and a committed `.mcp.json` would publish a
machine-specific absolute path:

```bash
claude mcp add --transport stdio --scope user mcp-bridge \
  -- C:\franl\.claude-agent-memory\bin\mcp-bridge\mcp-bridge.exe \
     --config C:\franl\.claude-agent-memory\bridge-config.yaml \
     --client-id claude-code
```

The `--` separates Claude Code's own flags from the command line handed to the server. User-scope
registration is written to `~/.claude.json`; note that this file is per-machine and is not
synchronized across machines, so the command must be run once on each machine where the bridge is
deployed.

Verify with `claude mcp list`, or `/mcp` inside a session, which also reports connection status.

**Install the skill.** Claude Code reads skills from the filesystem rather than from an uploaded
archive, so there is no zip step and no upload step:

```bash
mkdir -p ~/.claude/skills/stateful-memory
cp SKILL.md ~/.claude/skills/stateful-memory/
```

The directory name must match the skill's `name` frontmatter field (`stateful-memory`). The same
`SKILL.md` authored per [Chapter 5, Section 5.2](stateful-agent-design-chapter5.md#52-skillmd-content)
is used verbatim for both clients — this is the practical payoff of holding the `description` to
the tightest documented limit ([Section 5.7](stateful-agent-design-chapter5.md#57-frontmatter-constraints-and-portability)):
one artifact, no per-client variants to keep in sync.

**Two behavioral differences worth knowing.**

- **Tool definitions may be deferred.** Claude Code enables tool search by default, which defers
  MCP tool definitions so that registering additional servers costs little context. A deferred tool
  is not directly callable until it has been searched for, which weakens the affordance to invoke a
  memory tool spontaneously. This interacts with the initialization-reliability question recorded
  as OQ#18 ([Chapter 11](stateful-agent-design-chapter11.md#111-remaining-open-questions)).
- **Sub-agents cannot reach the bridge.** Claude Code sub-agents do not inherit the parent session's
  MCP server connections, so a sub-agent spawned by Claude Code has no memory access. This is
  consistent with — and independently enforces — the design's existing rule that sub-agents never
  write to memory ([Chapter 6, Section 6.6](stateful-agent-design-chapter6.md#66-sub-agent-memory-access-rules)),
  but it also means sub-agents cannot *read* memory under Claude Code, so any context a sub-agent
  needs must be passed explicitly in its prompt.

### 7.9 Running Multiple Clients Concurrently

Each MCP client spawns its own instance of the bridge binary. Deploying both Claude Desktop and
Claude Code therefore means two bridge processes sharing one memory root, which requires the
multi-bridge provisions of
[Chapter 3, Section 3.25](stateful-agent-design-chapter3.md#325-multi-bridge-concurrency).

Deployment requirements:

1. **Every client must pass a distinct, stable `--client-id`.** Two clients sharing an id will
   overwrite each other's state file; a client whose id changes between launches will orphan its
   own handles, branch map, and read baselines on every restart. Use `desktop` and `claude-code`.
2. **All clients must point at the same memory root**, via the same `bridge-config.yaml` or
   equivalent configuration. Two bridges with different memory roots are simply two independent
   memory systems, which is a supported configuration but not a shared one.
3. **All clients should run the same bridge build.** The cross-process lock, the state-file naming
   convention, the temp-file naming convention, and the signature format are all shared on-disk
   contracts. A mixed-version deployment where one bridge predates
   [Section 3.25](stateful-agent-design-chapter3.md#325-multi-bridge-concurrency) provides *no*
   safety at all, because the older binary takes no lock — the newer one would be serializing
   against a peer that ignores serialization entirely.

**Migration from a single-client deployment.** No manual step is required. On first startup the
bridge renames an existing `.bridge-state.json` to `.bridge-state-<client-id>.json`
([Chapter 3, Section 3.25.4](stateful-agent-design-chapter3.md#3254-per-client-state-files)).
Perform this first startup with the Desktop client (or whichever client owns the existing state)
before registering the second client, so the legacy state is attributed to the right one.

**Expect branches.** With one client, simultaneous conversations were the exception and branching
was effectively never triggered. With two clients — especially given that Claude Code sessions can
run for a long time while a Desktop conversation is also active — concurrent modification becomes
ordinary. `memory_run_maintenance` moves from a rarely-needed housekeeping call to a routine part
of the workflow, and should be run correspondingly more often.
