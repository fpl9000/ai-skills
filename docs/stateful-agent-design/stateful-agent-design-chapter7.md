# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Contents

- [7. Build and Deployment](#7-build-and-deployment)
  - [7.1 Build the Bridge](#71-build-the-bridge)
  - [7.2 Claude Desktop Configuration](#72-claude-desktop-configuration)
  - [7.3 Filesystem Extension Configuration](#73-filesystem-extension-configuration)
  - [7.4 Memory Directory Setup](#74-memory-directory-setup)
  - [7.5 Initial Memory Seeding](#75-initial-memory-seeding)
  - [7.6 Skill Installation](#76-skill-installation)
  - [7.7 CLAUDE.md Update](#77-claudemd-update)

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

**Note:** The Filesystem extension does **not** appear in `claude_desktop_config.json` and should **not** be added there. It is a first-party Claude Desktop extension developed by Anthropic and distributed through Claude Desktop's built-in extensions gallery (Settings > Extensions). It is installed, enabled, and configured entirely through the Claude Desktop UI — not via the config JSON file. Claude Desktop manages its configuration for first-party extensions through a separate internal store. See the resolution of Open Question #6 for details.

### 7.3 Filesystem Extension Configuration

The Filesystem extension is enabled and configured via Claude Desktop's Extensions UI (Settings > Extensions > Filesystem > Configure). The allowed directories (e.g., `C:\franl`, `C:\temp`, `C:\apps`) are set there, not in `claude_desktop_config.json`.

The memory directory (`C:\franl\.claude-agent-memory`) is covered because it is a subdirectory of `C:\franl`, which is already an allowed directory. No additional configuration is needed.

### 7.4 Memory Directory Setup

Create the directory structure:

```bash
mkdir -p C:/franl/.claude-agent-memory/blocks
```

Create the bridge configuration file (`bridge-config.yaml`) with the schema defined in [Section 3.2](#32-configuration).

### 7.5 Initial Memory Seeding

The first time the memory system is used, Claude will find an empty memory directory (no `core.md`, no `index.md`). The skill instructions handle this: "If core.md does not exist, this is a first-run scenario."

However, it's better to pre-seed the files with initial content derived from existing knowledge. This avoids a cold-start problem where Claude's first session has no Layer 2 context.

**Seeding approach:**

1. Manually create `core.md` with basic identity and project information (copy from Layer 1 memory or from conversation history).
2. Create `index.md` with an empty table header:
   ```markdown
   # Index

   | Block | Summary | Updated |
   |-------|---------|---------|
   ```
3. Optionally create initial project blocks for active projects.
4. The episodic log will be created automatically on the first session.

Alternatively, ask Claude in an initial conversation to seed the memory from its Layer 1 knowledge: "Please create the initial core.md and index.md for the memory system, using what you know about me from your built-in memory."

### 7.6 Skill Installation

1. Create the `SKILL.md` file with the content from [Section 5.2](#52-skillmd-content).
2. Create a .zip file containing only `SKILL.md`:
   ```bash
   zip stateful-memory.zip SKILL.md
   ```
3. Upload via Claude Desktop > Settings > Capabilities > Add Skill.

### 7.7 CLAUDE.md Update

Replace the current `C:\Users\flitt\.claude\CLAUDE.md` with the lean sub-agent-optimized version described in [Section 6.5](#65-claudemd-recommendations) and the proposal. Move credentials to environment variables. Move service-specific instructions to `spawn_agent` system_prompt parameters.
