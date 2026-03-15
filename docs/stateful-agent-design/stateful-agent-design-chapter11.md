# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>

**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## 11. Open Questions

1. **Race condition with memory writes** — MCP bridge tools `safe_write_file` and `safe_append_file` serialize file writes using a Go mutex, however this only prevents torn writes. It doesn't solve the problem where concurrent conversations race via read-modify-write.  For instance, if conversation A reads `core.md` and conversation B reads `core.md`, then after each is modified in-context, whichever conversation writes `core.md` last overwrites the other's changes.  Would it help to add a `safe_edit_file` tool that uses the same mutex?

   - *Resolution:* We discussed this and decided that last-writer-wins is the accepted concurrency model for v1. A `safe_edit_file` tool would not solve this because the race is about stale reads, not unprotected writes. The mutex prevents data corruption not semantic divergence from concurrent read-modify-write. The latter is accepted as rare and tolerable. Optimistic locking via version counters is the identified upgrade path if this proves insufficient. See updated [Section 3.9](#39-write-mutex).

2. **Need a tool to run commands** — Section 2.3, "What the Bridge Does NOT Do", says the bridge will not have a `run_command` tool, but using a sub-agent to run a simple `curl` command or Bash script is a waste of valuable tokens (that cost money).  Let's change the design to include implmenting the `run_command` tool.

   - *Resolution:* The `run_command` tool has been added to the bridge as a first-class tool (see [Section 3.6](#36-tool-run_command)). It executes shell commands via Cygwin bash (`C:\apps\cygwin\bin\bash.exe -c "<command>"`) with no LLM inference involved, making it dramatically cheaper than `spawn_agent` for simple operations. Key design decisions: (a) uses the same hybrid sync/async model as `spawn_agent` via the shared async executor ([Section 3.10](#310-async-executor)), so long-running commands like recursive `grep` are handled correctly; (b) default output limit is 50 KB (~12,500 tokens) to avoid context window bloat; (c) middle-truncation preserves both head and tail of output; (d) no command restrictions for v1 (primary agent already has equivalent access via `spawn_agent`); (e) all commands are logged for auditability. Section 2.3 has been updated to remove `run_command` from the "does NOT do" list. The bridge now provides five tools total.

3. **Bridge configuration question** — What exactly are the semantics of bridge configuration parameter `job_expiry_seconds`?

   - *Resolution:* `job_expiry_seconds` (default: 600) defines how long the bridge's job lifecycle manager will retain a completed-but-uncollected async job before discarding it. The expiry clock starts from `job.StartedAt` (not from when the process finished). When the cleanup goroutine's 30-second sweep detects that `now > job.StartedAt + job_expiry_seconds`, it kills the process if it is still running, logs a warning, and removes the job from the map.

     The parameter exists to prevent memory leaks from orphaned jobs — async jobs whose `job_id` was returned to the primary agent but never retrieved via `check_agent`. This can happen if the user closes Claude Desktop mid-conversation, the agent forgets to poll, or the agent hits a context limit and loses track of the job_id. Without expiry, those jobs would accumulate indefinitely in the job manager, holding process handles and output buffers (up to 50 KB each for `run_command`, up to the token limit for `spawn_agent`).

     The default of 600 seconds (10 minutes) is intentionally generous. In normal operation, the primary agent polls `check_agent` within seconds or minutes of receiving a `job_id`. The 10-minute window provides ample time for the agent to return to polling even after a distraction or brief interruption, while still ensuring the bridge doesn't accumulate stale jobs across a long Claude Desktop session. No change to the design or default value is needed.

4. **UNIX Signals on Windows** — Section 3.14, "Graceful Shutdown", mentions SIGINT and SIGTERM, but do those signals exist on Windows?  How does the Go runtime deal with UNIX signals on Windows?

   - *Resolution:* SIGTERM does not exist as a native inter-process signal on Windows — it is only a software-level constant defined within the Windows CRT and cannot be sent from one external process to another. SIGINT exists in a limited form (Ctrl+C in a console window triggers a `CTRL_C_EVENT` that Go maps to `syscall.SIGINT`), but since the bridge runs as a background stdio subprocess with no attached console, it is not reliably deliverable either. Go's `os/signal` package maps these console events to signal constants, but that is of no help for a headless subprocess.

     The correct shutdown mechanism for an MCP stdio server on Windows is **stdin EOF detection**. When Claude Desktop exits or kills the bridge, it closes the stdin pipe. The `mcp-go` SDK's stdio read loop detects this EOF and exits naturally, giving the bridge an opportunity to clean up. Section 3.14 has been updated accordingly: UNIX signal handling has been removed, the shutdown trigger is now stdin EOF, and subprocess termination uses `Process.Kill()` (which calls Windows `TerminateProcess` directly) rather than a SIGTERM-then-SIGKILL escalation sequence.

5. **Read-only mounts** — In section 6.4, "Directory Sandbox Behavior", the design states "For additional hardening, the bridge could launch the subprocess with the memory directory mounted read-only at the OS level (platform-specific)."  Is this possible on Windows 11?

   - *Resolution:* OS-level read-only mounting of a directory into a specific subprocess's namespace is not supported on Windows 11 without disproportionate complexity. The options considered were: (a) **ACL manipulation** — temporarily removing write permissions on the memory directory before launching the subprocess and restoring them after; this is globally visible (affects all processes, not just the sub-agent), introduces a TOCTOU race window, and is fragile if the bridge crashes before restoring permissions; (b) **Job Objects with restricted tokens** — Windows Job Objects can constrain CPU and memory but offer no directory-level read/write access control; (c) **App Containers / Win32 app isolation** — available since Windows 10 1903, but require setting up security capabilities and are far too complex to invoke from a Go binary for this use case. The design already provides the correct level of protection via Claude Code's own directory sandbox: when `allow_memory_read` is `false`, the sandbox blocks all access to the memory directory entirely; when `allow_memory_read` is `true`, the preamble-based write prohibition is the appropriate mechanism. No OS-level read-only hardening will be added in v1.

6. **Filesystem extension question** — In section 7.2, "Claude Desktop Configuration", the design says the existing Filesystem extension entry should already be present in `%APPDATA%\Claude\claude_desktop_config.json`, but on my Windows 11 machine that file contains only the below contents. Could the Filesystem extension be configured some other way? This is not really a problem, given that I know the Filesystem extension works in Claude Desktop, but I'm curious why it doesn't appear in that JSON file.

   ```
   {
     "globalShortcut": "Alt+Ctrl+Enter",
     "preferences": {
       "coworkScheduledTasksEnabled": false,
       "sidebarMode": "chat"
     }
   }
   ```

   - *Resolution:* The Filesystem extension does not appear in `claude_desktop_config.json` because it is not an MCP server configured by the user — it is a **first-party Claude Desktop extension** developed and distributed by Anthropic through Claude Desktop's built-in extensions gallery (Settings > Extensions). First-party extensions are installed, enabled, and configured entirely through the Claude Desktop UI. Claude Desktop manages their configuration through a separate internal store, not through `claude_desktop_config.json`.

     The `claude_desktop_config.json` file is only for **third-party MCP servers** that the user manually registers — i.e., servers that Claude Desktop does not know about natively and must be told how to launch. The `mcp-bridge` server we are building belongs in that file. The Filesystem extension does not.

     The screenshot of the Filesystem extension's detail screen in Claude Desktop confirms this: it shows an "Enabled" toggle and a "Configure" button (for setting allowed directories), consistent with a UI-managed extension. It also shows "Developed by Anthropic" and notes that it uses `@modelcontextprotocol/server-filesystem` under the hood — Anthropic has bundled the npm package but manages its lifecycle internally.

     **Impact on the design:** Section 7.2 has been corrected to remove the incorrect note and the example JSON that showed a `"filesystem"` entry in `claude_desktop_config.json`. Section 7.3 has been updated to describe configuring allowed directories via the UI instead of via command-line arguments. No `"filesystem"` entry should be added to `claude_desktop_config.json`.

7. **Claude Code CLI for implemenation** — Once this design stabilizes, do you see any issues with using Claude Code CLI with Sonnet 4.6 to implement it?

   - *Resolution:* Claude Code CLI with Claude Sonnet 4.6 is an appropriate choice for implementing the MCP bridge. Sonnet is Anthropic's recommended model for Claude Code and is well-suited to this kind of work: translating a detailed design document into Go code within a well-defined module structure. Note that `spawn_agent` and other bridge tools are unavailable during the bridge's own implementation — Claude Code CLI must be used directly for that phase. Once the bridge is built and deployed, it becomes available for all subsequent work.

8. **Slash commands** — Claude Code CLI has a slash command corresponding to each loaded skill.  Does the Claude Desktop also have these?  If so, can we use them to trigger memory writes?

   - *Resolution:* Slash commands are a Claude Code CLI terminal interface feature — the user types `/skill-name` in the interactive CLI session to explicitly invoke a skill. Claude Desktop has no equivalent mechanism; there is no input field where a user would type a slash command. Skills uploaded to Claude Desktop are invoked exclusively through the description-driven auto-invocation mechanism: Claude decides when to load a skill based on whether its description matches the current conversation context.

     In any case, slash commands would not be useful for triggering memory writes. A memory write requires Claude to call a tool (`Bridge:safe_write_file` or `Bridge:safe_append_file`), which happens in response to conversational context — not in response to a user-typed command. The memory skill's compliance-based instructions already cover when to write: on significant new information, on project status changes, at session end, etc. There is no gap here that slash commands would fill.

9. **Terms of Service question** — Given the news reported by PC World at https://www.pcworld.com/article/3068842/whats-behind-the-openclaw-ban-wave.html about Anthropic banning some automated use of Claude Code CLI, do Anthropic's consumer terms of service at https://www.anthropic.com/legal/consumer-terms or their Acceptable Use Policy at https://www.anthropic.com/legal/aup prevent using Claude Code CLI as a sub-agent?

   - *Resolution:* The design is compliant with Anthropic's Terms of Service. The `spawn_agent` tool invokes the official `claude -p` CLI binary as a subprocess — it does not extract, transfer, or reuse OAuth tokens, and it does not make direct Anthropic API calls. The bridge never touches authentication at all; the Claude Code CLI manages its own auth lifecycle internally. The Consumer ToS prohibition on automated access contains an explicit exception for use cases "where we otherwise explicitly permit it," and Anthropic explicitly permits scripted and automated use of the `claude` CLI — their official documentation demonstrates piping, scripting, and CI/CD pipelines as intended patterns.

     The account bans reported in January–February 2026 targeted a specific and narrow behavior: third-party harnesses (OpenCode, OpenClaw, Cline, Roo Code, etc.) that intercepted Claude's OAuth authentication flow, extracted the subscriber's OAuth token, and used it to make direct Anthropic API calls while forging the HTTP headers that the real Claude Code CLI sends — effectively spoofing the official client to gain flat-rate subscription access at API-level volume. Anthropic's formal prohibition, published February 17–19, 2026, reads: *"Using OAuth tokens obtained through Claude Free, Pro, or Max accounts in any other product, tool, or service — including the Agent SDK — is not permitted."* This design does none of that. The critical distinction is: **calling `claude -p` (the real CLI binary) = allowed; extracting OAuth tokens to use in a third-party API client = banned.**

     The "ordinary, individual usage" language added to Anthropic's February 2026 documentation refers to preventing subscription arbitrage at scale (e.g., multi-tenant bots running overnight autonomous swarms on a flat-rate plan, which would cost $1,000+/month at API prices). It does not apply to a single developer running personal project work from their own machine — which is the intended use case for a Max subscription and the exact scenario this design targets.

10. **Shell invocation to minimize quoting issues** — Section 3.6, "Tool: run_command", says that commands will be executed by Bash as follows: `C:\apps\cygwin\bin\bash.exe -c "<command>"`, but that can cause problems when `<command>` contains complex combinations of single and double quotes. Can the MCP server spawn Bash using `bash -s` so it reads the `<command>` from stdin, which simplifies the quoting issues in the command?

    - *Resolution:* Keep the `-c` approach. The question was based on a mistaken assumption: that the `bash -c <command>` invocation is itself parsed by a shell, which would require the command string to be shell-escaped. In fact, Go's `exec.Command` bypasses any intermediate shell entirely — it calls `CreateProcess` (on Windows) directly, passing the command string as a single, literal argument to Bash's `-c` flag. No shell metacharacter expansion occurs at the Go level; the raw string is delivered to Bash as-is.

      The genuine quoting challenge — complex single/double quote combinations in the command string — is a property of Bash parsing the command, not of how the string is delivered to Bash. Whether Bash receives the string via `-c` or via stdin (`-s`), it parses the same shell syntax identically. Switching to `bash -s` would not eliminate this challenge.

      The `-s` approach would have one narrow, genuine advantage: avoiding the Windows `CreateProcess` command-line length limit (~32 KB). For the command types `run_command` is intended for (`grep`, `curl`, `git`, `find`, short pipelines, etc.), this limit will never be approached in practice.

      Accordingly, the implementation uses `exec.Command(shellPath, append(shellArgs, params.Command)...)` as specified in [Section 3.6](#36-tool-run_command), where `shellArgs` defaults to `["-c"]`. This is correct, sufficient, and requires no change.

11. **Multiple home directories** — Sections 3.4, "Tool: spawn_agent", and 3.6, "Tool: run_command", say that the default value of the working directory parameter is my home directory, but there's an ambiguity: my Windows home directory is `C:\Users\flitt\` and my Cygwin home directory is `C:\franl\`.  Is there any issue with changing those sections to explicity specify `C:\franl\` as the default working directory for commands `spawn_agent` and `run_command`?

    - *Resolution:* No issue. `C:\franl\` is the correct default and `os.UserHomeDir()` would be wrong here for two reasons: (a) on Windows it returns `C:\Users\flitt\` (from `USERPROFILE`), not the Cygwin home; and (b) both `run_command` (which runs via Cygwin bash) and `spawn_agent` (which spawns a sub-agent doing real work) expect to start in the Cygwin-rooted environment where all projects and tools live. Using `C:\Users\flitt\` as the default would be consistently wrong.

      Rather than hardcoding `C:\franl\` as a compile-time constant, the design has been updated to add a `default_working_directory` field to the bridge config (see [Section 3.2](#32-configuration)), defaulting to `C:\franl\`. This keeps it configurable without a recompile if the filesystem layout ever changes, and is consistent with how the rest of the config handles machine-specific paths. Sections 3.4 and 3.6 have been updated to reference `config.DefaultWorkingDirectory` instead of `os.UserHomeDir()`.

12. **Claude.ai SKILL.md contents needed** — [Chapter 9, Future Enhancements, Section 9.5](stateful-agent-design-chapter9.md#95-github-relay-claudeai-to-local-bridge-communication), "GitHub Relay: Claude.ai to Local Bridge Communication", needs to include the contents of the skill, including the `SKILL.md` file and the names of any scripts.

    - *Resolution:* The relay functionality is split across two skills to maintain a clean separation between the transport protocol and the operational semantics:

      **(a) GitHub skill** (`ai-skills/github/`) — Gains three new scripts (`relay_common.py`, `relay_send.py`, `relay_receive.py`) and a new SKILL.md section covering the relay *transport protocol*: message format, HMAC signing and verification, polling strategy, and error handling. The transport layer is operation-agnostic — it treats the `operation` and `arguments` fields as opaque payloads.

      **(b) AI Messaging skill** (`ai-skills/ai-messaging/`) — A new skill containing only a `SKILL.md` file (no scripts). Covers the *semantic layer*: the three relay operations (`memory_query`, `shell_command`, `claude_prompt`), when to choose each one, what arguments they expect, and how to interpret results. This skill depends on the github skill's relay scripts for actual message transport. The dependency is explicit and one-directional (ai-messaging → github, never the reverse).

      This separation avoids mixing two distinct concerns in a single skill: the mechanical details of how messages are signed, delivered, and verified (transport) vs. the domain-specific knowledge of what operations are available and when to use each one (semantics). It also prevents the github skill's description from needing to serve two very different trigger patterns ("create a PR" vs. "read my local memory"), which could degrade auto-invocation accuracy.

      The `RELAY_HMAC_SECRET` environment variable value is stored in the user's Claude.ai personal instructions (the `<userPreferences>` block), alongside the existing `GITHUB_TOKEN` and Bluesky credentials. These instructions are shared by both Claude Desktop and Claude.ai, so both environments have access to the secret.

      See [Chapter 9, Future Enhancements, Section 9.5.10](stateful-agent-design-chapter9.md#9510-relay-script-inventory) for the script specifications, [Section 9.5.11](stateful-agent-design-chapter9.md#1511-github-skill-relay-transport-additions) for the github skill SKILL.md additions, and [Section 9.5.12](stateful-agent-design-chapter9.md#9512-ai-messaging-skill) for the ai-messaging skill's complete SKILL.md.
