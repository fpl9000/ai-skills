# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>

**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Contents

- [6. Sub-Agent System](#6-sub-agent-system)
  - [6.1 Command Construction](#61-command-construction)
  - [6.2 Default System Preamble](#62-default-system-preamble)
  - [6.3 System Prompt Assembly](#63-system-prompt-assembly)
  - [6.4 Directory Sandbox Behavior](#64-directory-sandbox-behavior)
  - [6.5 CLAUDE.md Recommendations](#65-claudemd-recommendations)
  - [6.6 Sub-Agent Memory Access Rules](#66-sub-agent-memory-access-rules)

## 6. Sub-Agent System

### 6.1 Command Construction

The bridge constructs a `claude -p` command from `spawn_agent` parameters. Here is the exact mapping:

```
claude
  --print                                    # Always: non-interactive pipe mode
  --output-format text                       # Always: plain text output (not JSON)
  --system-prompt "<preamble + system_prompt>" # Always: full system prompt replacement
  [--model <model>]                          # If model parameter provided
  [--add-dir <memory_dir>]                   # If allow_memory_read is true
  [--add-dir <dir1>] [--add-dir <dir2>] ... # For each additional_dirs entry
```

The `task` string is piped to the subprocess's stdin.

**Working directory:** Set via `proc.Dir` in Go's `exec.Cmd`. This also activates Claude Code's directory sandbox — the sub-agent cannot access files outside this directory (or explicitly granted `--add-dir` directories).

### 6.2 Default System Preamble

This preamble is injected into every sub-agent invocation. Because `--system-prompt` replaces Claude Code's entire default behavioral prompt (empirically confirmed), this is the sole set of behavioral instructions the sub-agent receives.

```
You are a sub-agent performing a focused task on behalf of a primary Claude conversation.

Rules:
- Complete the assigned task and return your findings as text output.
- Be concise and structured. Prefer markdown formatting for readability.
- Keep your response under 2,000 words unless the task requires more detail. Your output
  will be truncated if it exceeds a token budget, so prioritize the most important findings.
- Do NOT modify files under C:\franl\.claude-agent-memory\. This directory is read-only for you.
- Do NOT commit to Git or push to any remote repository unless the task explicitly asks for it.
- If you cannot complete the task with the information provided, return a clear explanation
  of what additional information or context you need.
- Do NOT engage in open-ended exploration. Stay focused on the assigned task.
```

### 6.3 System Prompt Assembly

The final system prompt passed to `--system-prompt` is assembled as:

```
[DEFAULT_PREAMBLE]

[caller's system_prompt, if provided]
```

Example: If the primary agent calls `spawn_agent` with `system_prompt: "Return your analysis as a markdown list. Each finding should have a severity (high/medium/low)."`, the sub-agent receives:

```
You are a sub-agent performing a focused task on behalf of a primary Claude conversation.

Rules:
- Complete the assigned task and return your findings as text output.
- Be concise and structured. Prefer markdown formatting for readability.
- [... rest of default preamble ...]

Return your analysis as a markdown list. Each finding should have a severity (high/medium/low).
```

### 6.4 Directory Sandbox Behavior

Claude Code's directory sandbox is enforcement-level security provided by Claude Code's own infrastructure:

| Scenario | `working_directory` | `allow_memory_read` | `additional_dirs` | Sub-agent can access |
|----------|--------------------|--------------------|-------------------|---------------------|
| Minimal | `C:\franl\projects\foo` | false | none | Only `C:\franl\projects\foo\**` |
| With memory | `C:\franl\projects\foo` | true | none | `C:\franl\projects\foo\**` + `C:\franl\.claude-agent-memory\**` (read) |
| Multi-repo | `C:\franl\projects\foo` | false | `[C:\franl\projects\bar]` | `C:\franl\projects\foo\**` + `C:\franl\projects\bar7**` |
| Memory + multi-repo | `C:\franl\projects\foo` | true | `[C:\franl\projects\bar]` | All three directories |

**Important:** The sandbox blocks reads, not just writes. If `allow_memory_read` is `false`, the sub-agent cannot even `cat` a memory file — Claude Code will refuse the operation.

**Write protection for memory files** is preamble-based (compliance), not enforced by the sandbox. If `allow_memory_read` is `true`, the sub-agent could technically write to the memory directory. The preamble instructs against this. For additional hardening, the bridge could launch the subprocess with the memory directory mounted read-only at the OS level (platform-specific).

### 6.5 CLAUDE.md Recommendations

The file `C:\Users\flitt\.claude\CLAUDE.md` is loaded into every Claude Code invocation automatically (including sub-agents), independent of `--system-prompt`. It should be optimized for the sub-agent use case:

**Target size:** Under 500 tokens (~400 words).

**Should include:**
- OS environment (Windows 11 + Cygwin, shell behavior, pathname conventions)
- Available tools (compilers, package managers, utilities)
- Source code conventions (line width, comments, encoding, newlines)

**Should NOT include:**
- Credentials (API tokens, passwords — use environment variables instead)
- Interactive instructions ("confirm with the user")
- Service-specific instructions (Bluesky conventions, GitHub profile)
- Niche build instructions (GUI flags, specific project configs)

Recommended `CLAUDE.md` content:

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

### 6.6 Sub-Agent Memory Access Rules

| Layer | Access | Enforcement | Notes |
|-------|--------|-------------|-------|
| Layer 1 (Anthropic built-in) | None | Platform | `claude -p` does not receive built-in memory. Platform limitation. |
| Layer 2 (supplementary) | Read-only (optional) | Sandbox (read) + preamble (write) | Controlled by `allow_memory_read`. Default: false. |
| CLAUDE.md | Auto-loaded | None (automatic) | Loaded by Claude Code startup, cannot be suppressed. Keep credentials out. |

**Why no write access?** Allowing sub-agents to write to Layer 2 would break the single-writer model and reintroduce concurrent write problems. The primary agent is the sole writer. Sub-agents return findings in their text response; the primary agent decides what to persist.
