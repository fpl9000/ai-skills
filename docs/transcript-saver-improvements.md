# Transcript Saver Script - Windows Compatibility Improvements

This document proposes changes to `transcript-saver/scripts/save_transcript.py` to improve
compatibility with Windows systems running Git Bash.

## Issues Identified

### Issue 1: Interactive Picker Fails in Non-TTY Environments (Critical)

**Location:** Lines 181-184

```python
else:
    # Default to 'local' which shows an interactive picker
    # of recent sessions from ~/.claude/projects/
    cmd.append('local')
```

**Problem:** When no `session_path` is provided, the script uses the `local` subcommand which
launches an interactive terminal picker via the `questionary` library.  On Windows in Git Bash
or non-console environments (such as Claude Code's subprocess execution), this fails with:

```
prompt_toolkit.output.win32.NoConsoleScreenBufferError: No Windows console found. Are you running cmd.exe?
```

**Root Cause:** The `prompt_toolkit` library used by `questionary` requires a native Windows
console (cmd.exe or PowerShell).  Git Bash uses a pseudo-terminal (PTY) that doesn't provide
the Win32 console APIs.

**Proposed Fix:** Detect non-interactive environments and auto-select the most recent session
for the current project directory instead of relying on the interactive picker.

```python
import sys

def is_interactive():
    """
    Check if the script is running in an interactive terminal.

    Returns False if running in a non-interactive environment where
    the interactive picker would fail.
    """
    # Check if stdin is connected to a terminal.
    if not sys.stdin.isatty():
        return False

    # On Windows, also check for console buffer availability.
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Try to get the console screen buffer info.
            # This will fail in Git Bash / non-console environments.
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            csbi = ctypes.create_string_buffer(22)
            result = kernel32.GetConsoleScreenBufferInfo(handle, csbi)
            return result != 0
        except Exception:
            return False

    return True
```

Then modify `run_transcript_tool()` to use this check:

```python
if session_path:
    cmd.append('json')
    cmd.append(str(session_path))
elif is_interactive():
    cmd.append('local')
else:
    # Non-interactive environment: auto-select most recent session for current project.
    auto_session = find_current_project_session()
    if auto_session:
        print(f"Auto-selected session: {auto_session.name}")
        cmd.append('json')
        cmd.append(str(auto_session))
    else:
        print("Error: Cannot use interactive picker in this environment.")
        print("Use --session-id to specify a session, or --list to see available sessions.")
        return 1
```

---

### Issue 2: Unicode Encoding Error (Critical)

**Location:** Line 225

```python
result = subprocess.run(cmd)
```

**Problem:** Windows defaults to the cp1252 (Windows-1252) encoding.  The `claude-code-transcripts`
tool writes HTML files containing Unicode characters (such as the gear emoji U+2699), causing:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2699' in position 14007
```

**Root Cause:** Python on Windows uses the system's default encoding for file I/O unless
explicitly configured otherwise.  The `claude-code-transcripts` tool doesn't force UTF-8
encoding when writing files.

**Proposed Fix:** Set the `PYTHONUTF8=1` environment variable when running the subprocess
on Windows to force UTF-8 encoding for all file operations.

```python
def run_transcript_tool(session_path=None, output_dir=None, gist=False,
                        auto_name=False, include_json=False, open_browser=True):
    # ... existing code ...

    # Prepare environment for subprocess.
    # On Windows, force UTF-8 encoding to handle Unicode in HTML output.
    env = os.environ.copy()
    if sys.platform == 'win32':
        env['PYTHONUTF8'] = '1'

    # ... build cmd list ...

    # Execute the command with the modified environment.
    print(f"Running: {' '.join(cmd)}")
    print()
    result = subprocess.run(cmd, env=env)

    return result.returncode
```

---

### Issue 3: No Current-Project Auto-Detection (Enhancement)

**Location:** Throughout `main()` and `run_transcript_tool()`

**Problem:** When run from within a Claude Code session, the script should auto-detect the
current session based on the working directory.  Currently it either:

- Uses the interactive picker (which fails on Windows in Git Bash)
- Requires the user to manually specify `--session-id`

**Proposed Fix:** Add a function to match the current working directory to a project in
`~/.claude/projects/` and auto-select the most recent session for that project.

```python
def find_current_project_session():
    """
    Find the most recent session file for the current working directory.

    Claude Code stores sessions in directories named after the project path,
    with path separators replaced by dashes.  For example:
        /home/user/myproject -> ~/.claude/projects/-home-user-myproject/
        C:\\Users\\user\\myproject -> ~/.claude/projects/C--Users-user-myproject/

    Returns:
        Path or None: Path to the most recent session file, or None if not found.
    """
    cwd = Path.cwd()
    claude_projects_dir = Path.home() / '.claude' / 'projects'

    if not claude_projects_dir.exists():
        return None

    # Convert current path to Claude's project directory naming convention.
    # Replace path separators and colons with dashes.
    cwd_str = str(cwd)
    if sys.platform == 'win32':
        # Windows: C:\Users\foo -> C--Users-foo
        project_name = cwd_str.replace(':\\', '--').replace('\\', '-')
    else:
        # Unix: /home/foo -> -home-foo
        project_name = cwd_str.replace('/', '-')

    project_dir = claude_projects_dir / project_name

    if not project_dir.exists():
        return None

    # Find most recent JSONL file in this project directory.
    session_files = list(project_dir.glob('*.jsonl'))
    if not session_files:
        return None

    # Sort by modification time, return most recent.
    session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return session_files[0]
```

---

### Issue 4: Documentation Comment (Minor)

**Location:** Lines 97-98

```python
# Define the base directory where Claude Code stores project sessions
# This is the standard location on macOS/Linux
```

**Problem:** The comment says "macOS/Linux" but the path `~/.claude/projects/` works
identically on Windows (where `~` expands to `C:\Users\<username>`).

**Proposed Fix:** Update the comment to be platform-inclusive:

```python
# Define the base directory where Claude Code stores project sessions.
# This path works on all platforms (macOS, Linux, and Windows).
```

---

## Summary of Changes

| Priority | Issue | Location | Fix |
|----------|-------|----------|-----|
| Critical | Interactive picker fails | Lines 181-184 | Add `is_interactive()` check; auto-detect session |
| Critical | Unicode encoding error | Line 225 | Set `PYTHONUTF8=1` env var on Windows |
| Enhancement | No current-project detection | New function | Add `find_current_project_session()` |
| Minor | Documentation | Lines 97-98 | Update comment to mention Windows |

## Testing Recommendations

After implementing these changes, test the following scenarios on Windows with Git Bash:

1. **Basic usage with auto-detection:**
   ```bash
   python save_transcript.py --output ./test-output
   ```

2. **Explicit session selection:**
   ```bash
   python save_transcript.py --list
   python save_transcript.py --session-id <id-from-list> --output ./test-output
   ```

3. **Gist publishing (if gh CLI is configured):**
   ```bash
   python save_transcript.py --gist
   ```

4. **Verify UTF-8 handling:**
   - Ensure output HTML files contain Unicode characters correctly.
   - Open generated HTML in a browser to verify rendering.
