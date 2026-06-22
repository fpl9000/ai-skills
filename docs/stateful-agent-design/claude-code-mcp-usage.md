# Claude Code MCP Support

I asked Claude Code CLI this question:

>Are you able to load and use a user-supplied local MCP server that communicates over stdin/stdout? I know that Claude Desktop can do this, but you are Claude Code CLI (running in a terminal).

Below was its answer.

---

Yes — this is a first-class feature of Claude Code CLI, not just Claude Desktop. Claude Code speaks the same MCP protocol and supports local stdio servers (JSON-RPC over a child process's stdin/stdout), exactly like Desktop, plus SSE and HTTP transports.

The difference from Desktop is just how you register them. Desktop uses a mcpServers block in claude_desktop_config.json; Claude Code uses its own CLI/config.

## How a user adds a stdio server

The simplest way is the claude mcp add command. Everything after -- is the literal command line the harness will spawn and talk to over stdio:
```bash
# A Node-based server
claude mcp add my-server -- node /c/path/to/server.js

# A Python server (your CLAUDE.md's preferred language)
claude mcp add my-server -- python /c/path/to/server.py

# With environment variables
claude mcp add my-server -e API_KEY=abc123 -- python /c/path/to/server.py
```
Or you can edit config directly — a project-scoped `.mcp.json` at the repo root:
```json
{
  "mcpServers": {
    "my-server": { "command": "python", "args": ["./server.py"], "env": {} }
  }
}
```
Scopes control visibility: local (just you, this project — the default), project (committed in `.mcp.json`, shared with the team), or user (global across all your projects). Manage them with claude mcp list, `claude mcp get <name>`, `claude mcp remove <name>`, and the in-session `/mcp` command shows connection status / handles auth.

## The important nuance about me

The MCP connection lifecycle is owned by the Claude Code harness, not by me mid-conversation. I don't dial out to a new MCP server on my own the way I run a Bash command. The flow is: you register the server → the client spawns it and performs the MCP handshake → its tools surface to me as callable tools named `mcp__<server>__<toolname>`. New stdio servers generally become available after the client (re)connects — often a session restart — rather than instantly appearing in an ongoing turn.

You can actually see this already working in this session: there are live MCP integrations connected right now (Gmail, Google Calendar, Google Drive, PubMed — they show up as `mcp__claude_ai_*` tools). So MCP is demonstrably active here; a local stdio server you write would surface the same way.

## One Windows/Cygwin caveat

On this machine, watch the path and launcher conventions:

- Node/npx-based servers sometimes need a `cmd /c npx ...` wrapper on Windows, since the bare `npx` shim can misbehave when spawned directly.
- The harness spawns the command as a native process, so prefer Windows-style absolute paths (`C:\...` or `/c/...` drive-letter form) rather than Cygwin symlink paths, which native apps can't follow (per your own `CLAUDE.md` notes).
- A python/uv-based server avoids most of the npx shim issues.
