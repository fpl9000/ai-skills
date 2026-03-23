# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>
**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Chapter 9: Future Enhancements](stateful-agent-design-chapter9.md) — parent chapter; Section 9.5 references this appendix.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## Appendix: GitHub Relay Detailed Specification

> **Status:** This appendix preserves the original detailed specification for the GitHub Relay
> protocol (formerly Section 9.5 of Chapter 9). As of March 2026, the relay design is
> designated as a **fallback approach** for mobile-to-local communication, pending evaluation
> of Anthropic's Dispatch feature for Cowork. See [Section 9.5 of Chapter 9](stateful-agent-design-chapter9.md#95-remote-access-mobile-to-local-communication)
> for the current assessment and decision framework.
>
> The specification below remains technically valid and can be implemented if the conditions
> described in Section 9.5.2 of Chapter 9 are met (i.e., Dispatch does not cover the
> required use cases).

---

### 9.5 GitHub Relay: Claude.ai to Local Bridge Communication

**Trigger:** When mobile or web access to the local stateful agent is desired — e.g., using the Claude app on a phone to invoke tools on the home machine.

**Problem:** Claude.ai runs code in an ephemeral Linux VM with strict egress restrictions (whitelisted domains only: `github.com`, `api.github.com`, `pypi.org`, etc.). It cannot reach arbitrary IPs or custom domains. This rules out direct connections via port forwarding, Tailscale, or any custom tunnel endpoint. However, both Claude.ai (via the GitHub skill) and the local MCP bridge can read and write to GitHub's REST API — making a private GitHub repo a viable asynchronous message relay.

**Architecture overview:**

```
┌──────────────────┐       ┌──────────────┐       ┌────────────────────────────┐
│  Claude.ai       │       │   GitHub     │       │  Local Machine             │
│  (phone/web)     │       │   Private    │       │  (Windows 11)              │
│                  │  PUT  │   Repo       │  GET  │                            │
│  GitHub skill ───────────▶ requests/   ─────────▶  MCP Bridge               │
│                  │       │              │       │    │                       │
│                  │  GET  │              │  PUT  │    ├─ memory_query:        │
│  GitHub skill ◀─────────── responses/ ◀──────────   │   handled directly    │
│                  │       │              │       │    ├─ shell_command:       │
│                  │       │              │       │    │   handled directly    │
│                  │       │              │       │    └─ claude_prompt:       │
│                  │       │              │       │        inject into Claude  │
│                  │       │              │       │        Desktop via AHK     │
│                  │       │              │       │        ▼                   │
│                  │       │              │       │      Claude Desktop        │
│                  │       │              │       │        │                   │
│                  │       │              │       │        ▼ relay_respond()   │
│                  │       │              │       │      MCP Bridge            │
└──────────────────┘       └──────────────┘       └────────────────────────────┘
```

**Key design principle:** The relay logic is integrated directly into the MCP bridge — there is no separate daemon process. The bridge polls the relay repo, handles `memory_query` and `shell_command` operations locally (no inference), and delegates `claude_prompt` operations to Claude Desktop via an AutoHotkey-based prompt injection mechanism.

**Relay repository:** A dedicated private repo (e.g., `fpl9000/claude-relay`) with the following structure:

```
claude-relay/
├── README.md
├── requests/          # Claude.ai writes here
│   └── <id>.json
├── responses/         # MCP bridge writes here
│   └── <id>.json
└── .gitignore
```

#### 9.5.1 Message Protocol

Each request/response pair shares a unique message ID (a timestamp-based UUID or similar). The protocol uses a simple state machine:

**Request message** (`requests/<id>.json`):

```json
{
  "id": "20260307T143022Z-a1b2c3",
  "created_at": "2026-03-07T14:30:22Z",
  "status": "pending",
  "hmac": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "operation": "memory_query",
  "arguments": {
    "path": "core.md"
  },
  "context": "User asked from mobile: what's in my core memory?"
}
```

**Response message** (`responses/<id>.json`):

```json
{
  "id": "20260307T143022Z-a1b2c3",
  "completed_at": "2026-03-07T14:30:38Z",
  "status": "completed",
  "hmac": "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
  "result": {
    "success": true,
    "content": "... file contents or response text ..."
  }
}
```

**Status values:**

| Status | Location | Meaning |
|--------|----------|---------|
| `pending` | `requests/` | Awaiting pickup by MCP bridge |
| `claimed` | `requests/` | Bridge has acknowledged, processing |
| `completed` | `responses/` | Result ready for Claude.ai to read |
| `failed` | `responses/` | Operation failed; `result.error` contains details |
| `expired` | `requests/` | TTL exceeded without pickup (set by cleanup) |

#### 9.5.2 Supported Operations

The relay supports exactly three operations, with a clear split: two are handled entirely by the MCP bridge (no inference), and one delegates to Claude Desktop for full agent-loop processing.

**Bridge-local operations (no inference):**

| Operation | Arguments | Behavior |
|-----------|-----------|----------|
| `memory_query` | `path` (string) | Reads the specified file from the memory directory and returns its content as UTF-8 text. Equivalent to the bridge's `safe_read_file` tool scoped to the memory directory. |
| `shell_command` | `command` (string), `timeout_seconds` (int, optional) | Executes the command locally and returns stdout/stderr as UTF-8 text. Equivalent to the bridge's `run_command` tool with the same security constraints (no interactive commands, enforced timeout). |

**Claude Desktop-delegated operation:**

| Operation | Arguments | Behavior |
|-----------|-----------|----------|
| `claude_prompt` | `prompt` (string) | Forwards the prompt to Claude Desktop for processing. Claude Desktop performs whatever tool calls it deems appropriate based on the prompt content, then returns its final response as UTF-8 text via the `relay_respond` MCP tool. |

The `claude_prompt` operation is the "full agent loop" path — it gives Claude Desktop complete autonomy to read memory, run commands, spawn sub-agents, or do anything else its tools allow. The other two operations are fast, deterministic shortcuts that bypass inference entirely.

#### 9.5.3 The `claude_prompt` Flow and `relay_respond` Tool

The `claude_prompt` operation requires a round-trip through Claude Desktop:

1. The MCP bridge picks up a `claude_prompt` request from the relay repo.
2. The bridge injects the prompt into Claude Desktop via an AutoHotkey script (mechanism TBD — see Section 9.5.7).
3. The injected prompt includes a preamble instructing Claude Desktop to call the `relay_respond` tool when it has completed the task:

   ```
   [RELAY REQUEST id=20260307T143022Z-a1b2c3]
   The following prompt was forwarded from Claude.ai via the GitHub relay.
   Process it using whatever tools you need, then call the relay_respond
   tool with your final answer.

   <relay_prompt>
   {original prompt text from Claude.ai}
   </relay_prompt>
   ```

4. Claude Desktop processes the prompt — reading memory, running commands, spawning agents, etc. as it sees fit.
5. When finished, Claude Desktop calls the `relay_respond` MCP tool provided by the bridge.
6. The bridge writes the response to `responses/<id>.json` in the relay repo.

**New MCP tool — `relay_respond`:**

```go
// Tool definition
mcp.NewTool(
    "relay_respond",
    mcp.WithDescription(
        "Submit a response for a relay request forwarded from Claude.ai. "+
        "Call this tool when you have completed processing a [RELAY REQUEST] prompt. "+
        "The response content will be delivered back to the Claude.ai session that "+
        "originated the request.",
    ),
    mcp.WithString("relay_id",
        mcp.Required(),
        mcp.Description("The relay request ID from the [RELAY REQUEST] header."),
    ),
    mcp.WithString("content",
        mcp.Required(),
        mcp.Description(
            "Your complete response to the relay request, as UTF-8 text. "+
            "Include all relevant results, summaries, and context — the "+
            "recipient cannot ask follow-up questions.",
        ),
    ),
)
```

**Handler behavior:**

1. Validate that `relay_id` matches a `claimed` request that used the `claude_prompt` operation.
2. Write `responses/<relay_id>.json` to the relay repo via the GitHub API.
3. Return success to Claude Desktop.

If Claude Desktop calls `relay_respond` with an unknown or already-completed `relay_id`, the handler returns a tool error.

#### 9.5.4 Security

The relay repo is private, but defense-in-depth applies:

1. **Bidirectional HMAC authentication via relay skill scripts:** The bridge and Claude.ai share a secret key (stored in the `RELAY_HMAC_SECRET` environment variable on both sides). Both requests and responses are authenticated using HMAC-SHA256, implemented in two Python scripts that are part of the GitHub skill:

   - **`relay_send.py`** — Constructs a relay message, computes the HMAC, and pushes the signed message to the relay repo via the GitHub API.
   - **`relay_receive.py`** — Fetches a relay message from the repo, recomputes the HMAC from the message fields, performs constant-time comparison, and returns the verified payload (or rejects the message).

   Because both scripts live in the GitHub skill, and the GitHub skill is available to both Claude.ai (in its ephemeral VM) and the MCP bridge (on the local machine via `uv run`), both sides get signing *and* verification from the same codebase. The bridge does not need to implement HMAC in Go — its relay goroutine shells out to `uv run scripts/relay_send.py` and `uv run scripts/relay_receive.py` for all crypto operations, keeping the bridge code focused on orchestration.

   **HMAC protocol:**

   Both scripts share a common `compute_hmac()` function. The HMAC input is constructed by concatenating message fields in a canonical order that differs by message direction:

   - **Request HMAC input:** `id || operation || canonical_arguments`, where `canonical_arguments` is the JSON-serialized `arguments` object with keys sorted alphabetically.
   - **Response HMAC input:** `id || status || canonical_result`, where `canonical_result` is the JSON-serialized `result` object with keys sorted alphabetically.

   The HMAC is computed using HMAC-SHA256 and hex-encoded. Verification uses `hmac.compare_digest()` for constant-time comparison.

   **Replay prevention:** `relay_receive.py` checks the timestamp field (`created_at` for requests, `completed_at` for responses) against a ±5-minute window. Messages outside this window are rejected. Within the window, replay is prevented by the combination of: (a) the relay repo's Git history making message tampering auditable, (b) the bridge deleting request files after processing, and (c) the short TTL on response files.

   **Example HMAC computations:**

   ```
   Request:
     Input:  "20260307T143022Z-a1b2c3" + "memory_query" + '{"path":"core.md"}'
     Key:    <shared secret from RELAY_HMAC_SECRET>
     Output: HMAC-SHA256 → hex-encoded → "e3b0c44298fc1c..."

   Response:
     Input:  "20260307T143022Z-a1b2c3" + "completed" + '{"content":"...","success":true}'
     Key:    <shared secret from RELAY_HMAC_SECRET>
     Output: HMAC-SHA256 → hex-encoded → "7f83b1657ff1fc..."
   ```

   Messages with invalid or missing HMACs are rejected and logged. On the Claude.ai side, a response that fails HMAC verification is reported to the user as a potential tampering event rather than silently accepted.

   **Script invocation patterns:**

   Sending a signed request (Claude.ai side):
   ```bash
   GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
       fpl9000/claude-relay \
       --direction request \
       --id "20260307T143022Z-a1b2c3" \
       --operation memory_query \
       --arguments '{"path":"core.md"}' \
       --context "User asked from mobile: what is in my core memory?"
   ```

   Receiving and validating a response (Claude.ai side):
   ```bash
   GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_receive.py \
       fpl9000/claude-relay \
       --direction response \
       --id "20260307T143022Z-a1b2c3"
   ```

   The bridge uses the same scripts with `--direction` reversed: `relay_receive.py --direction request` to validate incoming requests, and `relay_send.py --direction response` to sign outgoing responses.

   **Pseudo-code for `relay_send.py`:**

   ```
   # /// script
   # requires-python = ">=3.11"
   # dependencies = ["requests"]
   # ///

   import argparse, hashlib, hmac, json, os, secrets, sys
   from datetime import datetime, timezone

   def compute_hmac(key_hex, *fields):
       """Compute HMAC-SHA256 over concatenated fields.
       The key is hex-decoded from the environment variable.
       Fields are concatenated as UTF-8 strings with no separator
       (each field is self-delimiting by protocol design)."""
       key = bytes.fromhex(key_hex)
       msg = "".join(fields).encode("utf-8")
       return hmac.new(key, msg, hashlib.sha256).hexdigest()

   def canonical_json(obj):
       """Serialize a dict to JSON with keys sorted alphabetically.
       This ensures both sides produce identical HMAC inputs
       regardless of the dict's internal key ordering."""
       return json.dumps(obj, sort_keys=True, separators=(",", ":"))

   def generate_message_id():
       """Create a timestamp-based ID with a random suffix.
       Format: 20260307T143022Z-a1b2c3 (ISO 8601 compact + 6 hex chars)."""
       ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
       suffix = secrets.token_hex(3)
       return f"{ts}-{suffix}"

   def main():
       # Parse args: repo, --direction, --id (optional, auto-generated if omitted),
       #             --operation (for requests), --status (for responses),
       #             --arguments/--result (JSON string), --context (optional)

       # Load shared secret from RELAY_HMAC_SECRET env var
       secret = os.environ["RELAY_HMAC_SECRET"]

       # Build the message body (varies by direction)
       if direction == "request":
           timestamp = datetime.now(timezone.utc).isoformat()
           canonical_args = canonical_json(arguments)
           mac = compute_hmac(secret, msg_id, operation, canonical_args)
           message = {
               "id": msg_id,
               "created_at": timestamp,
               "status": "pending",
               "hmac": mac,
               "operation": operation,
               "arguments": arguments,
               "context": context   # optional, not included in HMAC
           }
           path = f"requests/{msg_id}.json"

       elif direction == "response":
           timestamp = datetime.now(timezone.utc).isoformat()
           canonical_res = canonical_json(result)
           mac = compute_hmac(secret, msg_id, status, canonical_res)
           message = {
               "id": msg_id,
               "completed_at": timestamp,
               "status": status,
               "hmac": mac,
               "result": result
           }
           path = f"responses/{msg_id}.json"

       # Push to GitHub via REST API (PUT /repos/:owner/:repo/contents/:path)
       # Uses GITHUB_TOKEN for authentication
       # Prints the message ID to stdout on success for the caller to capture
   ```

   **Pseudo-code for `relay_receive.py`:**

   ```
   # /// script
   # requires-python = ">=3.11"
   # dependencies = ["requests"]
   # ///

   import argparse, hashlib, hmac, json, os, sys
   from datetime import datetime, timezone, timedelta

   # compute_hmac() and canonical_json() — same as in relay_send.py
   # (in implementation, these would be in a shared module like relay_common.py,
   # or duplicated with a comment pointing to the canonical copy)

   REPLAY_WINDOW_MINUTES = 5

   def validate_timestamp(ts_str):
       """Reject messages whose timestamp is outside the ±5-minute window.
       This bounds the replay prevention surface without requiring
       persistent state."""
       ts = datetime.fromisoformat(ts_str)
       now = datetime.now(timezone.utc)
       delta = abs((now - ts).total_seconds())
       if delta > REPLAY_WINDOW_MINUTES * 60:
           return False, f"Timestamp {ts_str} is {delta:.0f}s from now (limit: {REPLAY_WINDOW_MINUTES * 60}s)"
       return True, None

   def main():
       # Parse args: repo, --direction, --id, --json (output as JSON, default: true)

       # Load shared secret from RELAY_HMAC_SECRET env var
       secret = os.environ["RELAY_HMAC_SECRET"]

       # Determine the file path based on direction
       if direction == "request":
           path = f"requests/{msg_id}.json"
       elif direction == "response":
           path = f"responses/{msg_id}.json"

       # Fetch the message from GitHub via REST API
       # (GET /repos/:owner/:repo/contents/:path)
       # If 404: print error and exit 1 (message not yet available or expired)
       message = fetch_and_parse(repo, path)

       # Extract fields for HMAC verification
       received_hmac = message["hmac"]

       if direction == "request":
           timestamp_field = message["created_at"]
           canonical_payload = canonical_json(message["arguments"])
           expected_hmac = compute_hmac(
               secret, message["id"], message["operation"], canonical_payload
           )
       elif direction == "response":
           timestamp_field = message["completed_at"]
           canonical_payload = canonical_json(message["result"])
           expected_hmac = compute_hmac(
               secret, message["id"], message["status"], canonical_payload
           )

       # Constant-time HMAC comparison — prevents timing side-channel attacks
       if not hmac.compare_digest(received_hmac, expected_hmac):
           print(json.dumps({"error": "HMAC verification failed", "id": msg_id}))
           sys.exit(2)

       # Timestamp validation — reject messages outside the replay window
       valid, reason = validate_timestamp(timestamp_field)
       if not valid:
           print(json.dumps({"error": f"Timestamp rejected: {reason}", "id": msg_id}))
           sys.exit(3)

       # Verification passed — output the validated message payload
       print(json.dumps({"verified": True, "message": message}))
       sys.exit(0)
   ```

   **Testing the HMAC round-trip without the bridge:** Because both scripts are standalone, the full signing and verification flow can be tested from the command line:

   ```bash
   # 1. Send a signed request
   export RELAY_HMAC_SECRET="your_hex_secret_here"
   export GITHUB_TOKEN="ghp_..."
   ID=$(uv run scripts/relay_send.py fpl9000/claude-relay \
       --direction request --operation memory_query \
       --arguments '{"path":"core.md"}')

   # 2. Verify it (simulating the bridge side)
   uv run scripts/relay_receive.py fpl9000/claude-relay \
       --direction request --id "$ID"
   # Expected: {"verified": true, "message": {...}}

   # 3. Tamper test: manually edit the request in the repo, re-verify
   # Expected: exit code 2, "HMAC verification failed"
   ```

   **No HMAC in Go:** Because the bridge delegates all HMAC operations to these Python scripts (invoked via `uv run` using `exec.Command`, the same mechanism used by `run_command`), the bridge's Go code contains no cryptographic logic. This keeps the bridge focused on its core responsibilities (MCP tool handling, subprocess management, relay orchestration) and ensures that the signing and verification logic is identical on both sides — there is exactly one implementation, shared via the GitHub skill.

2. **Operation allowlist:** The bridge configuration specifies which operations are permitted via the relay. For example, `shell_command` can be disabled or restricted to specific command patterns.

3. **Rate limiting:** The bridge enforces a maximum number of requests per time window (e.g., 10 requests per minute) to limit abuse.

4. **Audit log:** All relay activity is logged to the bridge's log file, including rejected requests and responses with the rejection reason (bad HMAC, disallowed operation, rate-limited).

#### 9.5.5 Bridge Relay Integration

The relay polling loop runs as a goroutine within the MCP bridge process. Its responsibilities:

1. **Poll** the `requests/` directory in the relay repo at a configurable interval (default: 15 seconds) using the GitHub Contents API.
2. **Validate** incoming requests by invoking `uv run scripts/relay_receive.py --direction request --id <id>`. Requests that fail HMAC verification or timestamp validation are rejected and logged.
3. **Claim** validated `pending` requests by updating their status to `claimed`.
4. **Dispatch** the operation:
   - `memory_query` → read the file directly from the memory directory and write the response.
   - `shell_command` → execute the command (reusing `run_command` logic) and write the response.
   - `claude_prompt` → inject the prompt into Claude Desktop via AutoHotkey; the response arrives asynchronously when Claude Desktop calls `relay_respond`.
5. **Sign and send** responses by invoking `uv run scripts/relay_send.py --direction response --id <id> --status completed --result '<json>'`.
6. **Clean up** expired requests and old response files beyond the configured TTL (default: 1 hour).

The bridge invokes the relay skill scripts via `exec.Command` and `uv run`, consistent with how all other GitHub skill scripts are used. The `GITHUB_TOKEN` and `RELAY_HMAC_SECRET` environment variables are inherited from the bridge's process environment (configured in the bridge's YAML config via `github_token_env` and `hmac_secret_env`).

**Bridge configuration** (added to `relay-config.yaml` or a `[relay]` section in the bridge config):

```yaml
relay:
  enabled: false               # Off by default
  repo: fpl9000/claude-relay
  github_token_env: GITHUB_TOKEN
  poll_interval_seconds: 15
  request_ttl_minutes: 60
  claude_prompt_timeout_minutes: 5
  max_requests_per_minute: 10
  hmac_secret_env: RELAY_HMAC_SECRET   # Environment variable holding the shared key
  replay_window_minutes: 5             # Replay prevention window
  skill_scripts_dir: C:\franl\git\ai-skills\skills\github\scripts  # Path to relay_send.py / relay_receive.py
  allowed_operations:
    - memory_query
    - shell_command
    - claude_prompt
  ahk_script_path: C:\franl\scripts\relay-inject.ahk
  log_file: C:\franl\.claude-agent-memory\relay.log
```

#### 9.5.6 Claude.ai Workflow

From Claude.ai (web or mobile), the interaction pattern is:

1. **User** asks Claude.ai to do something that requires the local machine (e.g., "read my core memory," "ask my local Claude to summarize today's episodic log").
2. **Claude.ai** invokes `relay_send.py` (via `uv run` from the GitHub skill) to construct a signed request and push it to the relay repo. The script returns the message ID.
3. **Claude.ai** polls by invoking `relay_receive.py --direction response --id <id>` at intervals (e.g., every 10 seconds, up to a timeout). The script returns the validated response payload or a 404/timeout indication.
4. **Claude.ai** presents the verified result to the user. If HMAC verification fails, Claude.ai reports a potential tampering event rather than silently accepting the response.

The round-trip latency depends on the operation:

| Operation | Typical latency | Bottleneck |
|-----------|----------------|------------|
| `memory_query` | 15–40 sec | Bridge poll interval + GitHub API round-trips |
| `shell_command` | 15–60 sec | Bridge poll interval + command execution time |
| `claude_prompt` | 30 sec–5 min | Bridge poll interval + Claude Desktop inference + tool calls |

**Timeout behavior:** If no response appears within a configurable timeout (default: 2 minutes for bridge-local ops, 5 minutes for `claude_prompt`), Claude.ai reports that the local machine may be offline or the operation is still in progress.

#### 9.5.7 AutoHotkey Prompt Injection (TBD)

The mechanism for injecting a prompt into Claude Desktop's UI is deferred to a future design iteration. The approach will use an AutoHotkey script that:

1. Activates the Claude Desktop window.
2. Pastes the relay-formatted prompt into the input field.
3. Sends Enter to submit.

Design considerations include: handling the case where Claude Desktop is mid-conversation, ensuring the prompt is injected cleanly (no partial sends), and dealing with Claude Desktop's window state (minimized, behind other windows, etc.).

#### 9.5.8 Cleanup and Hygiene

- The bridge deletes request files after writing the corresponding response.
- Response files are deleted after the configured TTL.
- Cleanup runs on each poll cycle as part of the relay goroutine.
- The relay repo should stay lean — it is a message queue, not a data store. The `.gitignore` should exclude any local state files.
- GitHub API rate limits (5,000 authenticated requests/hour) are more than sufficient for relay traffic at expected volumes.

#### 9.5.9 Relationship to Section 1.3 (Architecture B2 Upgrade)

If the bridge gains Streamable HTTP transport and a Cloudflare Tunnel (Section 1.3), Claude.ai could potentially connect directly — bypassing the GitHub relay entirely. The relay is the pragmatic v1 solution that works within Claude.ai's current egress restrictions. The two approaches are complementary: the relay can remain as a fallback for environments where tunnel setup is impractical.

#### 9.5.10 Relay Script Inventory

Three new scripts are added to the github skill's `scripts/` directory. All use PEP 723 inline metadata and run via `uv run`.

**`relay_common.py`** — Shared module providing `compute_hmac()`, `canonical_json()`, `generate_message_id()`, and `validate_timestamp()`. Imported by both `relay_send.py` and `relay_receive.py`. Not invoked directly.

**`relay_send.py`** — Constructs a signed relay message and pushes it to the relay repo via the GitHub API.

```
Usage:
  uv run scripts/relay_send.py <repo> --direction request|response [options]

  For requests (Claude.ai → bridge):
    --id <id>                   Message ID (auto-generated if omitted)
    --operation <op>            Operation name (required)
    --arguments <json>          JSON object of operation arguments (required)
    --context <text>            Optional human-readable context (not included in HMAC)

  For responses (bridge → Claude.ai):
    --id <id>                   Message ID (required, must match the request)
    --status completed|failed   Response status (required)
    --result <json>             JSON object of response payload (required)

Environment variables:
    GITHUB_TOKEN                GitHub PAT with repo access
    RELAY_HMAC_SECRET           Hex-encoded shared HMAC key

Output:
    On success, prints the message ID to stdout.
    On failure, prints an error message to stderr and exits with code 1.
```

**`relay_receive.py`** — Fetches a relay message from the relay repo, verifies its HMAC signature and timestamp, and returns the validated payload.

```
Usage:
  uv run scripts/relay_receive.py <repo> --direction request|response --id <id>

Environment variables:
    GITHUB_TOKEN                GitHub PAT with repo access
    RELAY_HMAC_SECRET           Hex-encoded shared HMAC key

Output (JSON to stdout):
    On success:  {"verified": true, "message": {...}}
    On HMAC failure: {"error": "HMAC verification failed", "id": "<id>"}  (exit code 2)
    On timestamp rejection: {"error": "Timestamp rejected: ...", "id": "<id>"}  (exit code 3)
    On not found: {"error": "Message not found", "id": "<id>"}  (exit code 1)
```

#### 9.5.11 GitHub Skill Relay Transport Additions

The following section is appended to the existing `github/SKILL.md` when the relay is implemented. It covers the transport protocol only — the semantic layer (operations, decision tree) is in the ai-messaging skill ([Section 9.5.12](#1512-ai-messaging-skill)).

````markdown
---

## Relay Transport Protocol

The GitHub skill includes scripts for a relay transport protocol that uses a private
GitHub repository as an asynchronous message bus. This protocol enables communication
between Claude.ai (which has restricted network egress) and a local MCP bridge server
(which can read/write to GitHub via the API).

The transport layer is operation-agnostic — it handles message signing, delivery,
polling, and verification without interpreting the message payload. The semantic
meaning of operations is defined by the AI Messaging skill, which depends on
these scripts.

### Prerequisites

In addition to the standard `GITHUB_TOKEN`, the relay scripts require:

- `RELAY_HMAC_SECRET` — A hex-encoded shared secret key for HMAC-SHA256 message
  authentication. Both Claude.ai and the local MCP bridge must use the same key.

### Message Format

Each relay exchange consists of a request/response pair sharing a unique message ID.

**Request** (pushed to `requests/<id>.json` in the relay repo):

```json
{
  "id": "20260307T143022Z-a1b2c3",
  "created_at": "2026-03-07T14:30:22Z",
  "status": "pending",
  "hmac": "<64 hex chars>",
  "operation": "<operation name>",
  "arguments": { ... },
  "context": "<optional human-readable context>"
}
```

**Response** (pushed to `responses/<id>.json` in the relay repo):

```json
{
  "id": "20260307T143022Z-a1b2c3",
  "completed_at": "2026-03-07T14:30:38Z",
  "status": "completed",
  "hmac": "<64 hex chars>",
  "result": {
    "success": true,
    "content": "..."
  }
}
```

### Sending a Signed Message

Use `relay_send.py` to construct, sign, and push a message:

```bash
# Send a request (Claude.ai side)
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction request \
    --operation memory_query \
    --arguments '{"path":"core.md"}' \
    --context "User asked from mobile: what's in my core memory?"

# Send a response (bridge side)
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction response \
    --id "20260307T143022Z-a1b2c3" \
    --status completed \
    --result '{"success":true,"content":"# Core\n\nFran is a retired..."}'
```

### Receiving and Verifying a Message

Use `relay_receive.py` to fetch, verify HMAC, validate timestamp, and return
the payload:

```bash
# Receive a response (Claude.ai side, polling for a result)
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_receive.py \
    fpl9000/claude-relay \
    --direction response \
    --id "20260307T143022Z-a1b2c3"
```

The script verifies the HMAC signature (constant-time comparison) and rejects
messages whose timestamp is outside a ±5-minute window. Exit codes:
- **0**: Verified successfully. Stdout contains `{"verified": true, "message": {...}}`.
- **1**: Message not found (not yet available or expired).
- **2**: HMAC verification failed (possible tampering).
- **3**: Timestamp outside replay window.

### Polling Strategy

When waiting for a response from the local MCP bridge:

- **Minimum polling interval:** 2 minutes for bridge-local operations
  (`memory_query`, `shell_command`); 5 minutes for `claude_prompt`.
- **Longer intervals are acceptable.** Use your judgment — if the bridge is
  likely busy with a complex `claude_prompt` task, waiting longer before the
  first poll is reasonable.
- **Backoff on failure:** If a poll returns "not found" (exit code 1), double
  the interval for the next attempt, up to a maximum of 5 minutes for
  bridge-local ops and 10 minutes for `claude_prompt`.
- **Maximum attempts:** Stop polling after 5 attempts for bridge-local ops
  (total wall-clock ~10–15 minutes) or 4 attempts for `claude_prompt`
  (total wall-clock ~20–30 minutes). Report to the user that the local
  machine may be offline or the operation is still in progress.

### Error Handling

| Scenario | Behavior |
|----------|----------|
| `relay_send.py` fails (exit code 1) | Report the GitHub API error to the user. Common cause: invalid token or repo not found. |
| `relay_receive.py` exit code 1 (not found) | Message not yet available. Continue polling per the strategy above. |
| `relay_receive.py` exit code 2 (HMAC failed) | **Potential tampering.** Report to the user that the response failed authentication. Do NOT use the message content. |
| `relay_receive.py` exit code 3 (timestamp rejected) | Message is too old or clock skew is excessive. Report to the user. |
| Max polling attempts reached | Inform the user that the local machine may be offline, sleeping, or the bridge is not running. |

### HMAC Details (Reference)

The HMAC is computed over canonicalized message fields using HMAC-SHA256:

- **Request HMAC input:** `id + operation + canonical_json(arguments)`
- **Response HMAC input:** `id + status + canonical_json(result)`

Where `canonical_json()` serializes the JSON object with keys sorted alphabetically
and compact separators (`","` `":"`). The `context` field in requests is NOT included
in the HMAC (it is informational only).

````

#### 9.5.12 AI Messaging Skill

The AI Messaging skill is a new skill created at `ai-skills/ai-messaging/SKILL.md`. It contains only a `SKILL.md` file (no scripts) and depends on the github skill's relay transport scripts.

**Skill description** (for Claude Desktop/Claude.ai auto-invocation):

```
name: ai-messaging
description: >
  Communicate with the local stateful agent system via the GitHub relay.
  Use this skill when the user wants to interact with their local machine
  remotely — reading memory files, running shell commands, or delegating
  tasks to the local Claude Desktop agent. Triggers include phrases like:
  "on my local machine", "check my local files", "run this on my home
  computer", "ask my local Claude", "read my memory files", "what's in
  my core memory", "what's on my home machine", "run this locally".
  Requires the github skill for relay transport scripts.
```

**Complete `SKILL.md` content:**

````markdown
---
name: ai-messaging
description: >
  Communicate with the local stateful agent system via the GitHub relay.
  Use this skill when the user wants to interact with their local machine
  remotely — reading memory files, running shell commands, or delegating
  tasks to the local Claude Desktop agent. Triggers include phrases like:
  "on my local machine", "check my local files", "run this on my home
  computer", "ask my local Claude", "read my memory files", "what's in
  my core memory", "what's on my home machine", "run this locally".
  Requires the github skill for relay transport scripts.
---

# AI Messaging Skill

This skill enables Claude.ai (web or mobile) to communicate with the local
stateful agent system running on Fran's home machine. It uses the GitHub relay
transport protocol (provided by the github skill) to send signed requests to
the local MCP bridge and receive signed responses.

## Prerequisites

- The **github skill** must be installed (provides `relay_send.py`,
  `relay_receive.py`, and `relay_common.py` in its `scripts/` directory).
- Environment variables `GITHUB_TOKEN` and `RELAY_HMAC_SECRET` must be set
  (available via personal instructions).
- The relay repository is `fpl9000/claude-relay`.

## When to Use This Skill

Use this skill when the user wants to do something that requires their local
machine — a Windows 11 system running the MCP bridge server. Common triggers:

- "Read my core memory" / "What's in my memory files?"
- "Run this on my local machine" / "Check something on my home computer"
- "Ask my local Claude to..." / "Have Claude Desktop do..."
- "What's the status of [project] locally?"
- "Run `git status` on my mcp-bridge repo"
- Any reference to the local machine, local files, or the stateful agent system

Do NOT use this skill for operations that can be performed directly from
Claude.ai (e.g., reading GitHub repos via the github skill's existing scripts,
web searches, or general knowledge questions).

## Operations

The relay supports three operations. Choose the simplest one that can
accomplish the task.

### memory_query

Read a file from the local Layer 2 memory directory
(`C:\franl\.claude-agent-memory\`). The MCP bridge handles this directly
with no LLM inference — it simply reads the file and returns its contents.

**When to use:** The user wants to see the contents of a specific memory
file (core.md, index.md, or a block).

**Arguments:**
```json
{"path": "core.md"}
```

The `path` is relative to the memory directory. Valid paths include:
- `core.md` — Identity and active project summary
- `index.md` — Block index table
- `blocks/project-mcp-bridge.md` — A specific content block
- `blocks/episodic-2026-03.md` — A specific episodic log

**Example invocation:**
```bash
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction request \
    --operation memory_query \
    --arguments '{"path":"core.md"}'
```

**Response format:** `result.content` contains the full UTF-8 text of the file.
If the file does not exist, `result.success` is `false` and `result.error`
describes the problem.

### shell_command

Execute a shell command on the local machine via Cygwin bash. The MCP bridge
handles this directly with no LLM inference — it runs the command and returns
stdout/stderr. This is equivalent to the bridge's `run_command` tool.

**When to use:** The task can be expressed as a single shell command or short
pipeline and requires no LLM reasoning. Examples: `git status`, `ls -la`,
`grep -r 'TODO' src/`, `cat some-file.txt`, `wc -l *.go`.

**Arguments:**
```json
{
  "command": "cd /c/franl/git/mcp-bridge && git log --oneline -5",
  "timeout_seconds": 60
}
```

- `command` (required) — The shell command to execute.
- `timeout_seconds` (optional, default: 120) — Maximum runtime before the
  command is killed.

**Example invocation:**
```bash
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction request \
    --operation shell_command \
    --arguments '{"command":"cd /c/franl/git/mcp-bridge && git log --oneline -5"}'
```

**Response format:** `result.content` contains the combined stdout+stderr.
`result.exit_code` contains the process exit code (0 = success).
`result.timed_out` is `true` if the command exceeded its timeout.

### claude_prompt

Forward a prompt to Claude Desktop for full agent-loop processing. Claude
Desktop receives the prompt, performs whatever tool calls it deems appropriate
(reading memory, running commands, spawning sub-agents, writing memory
updates), and returns its final response.

**When to use:** The task requires LLM reasoning, multi-step tool use, or
memory writes. Examples:
- "Summarize today's episodic log and update core.md"
- "Read the mcp-bridge project block and tell me what the open issues are"
- "Refactor the error handling in server.go"
- "Create a new memory block for the dashboard-v2 project"

**Arguments:**
```json
{
  "prompt": "Read the mcp-bridge project block and summarize the current open issues."
}
```

- `prompt` (required) — The task prompt for Claude Desktop. Write it as if
  you were typing directly into Claude Desktop's input field. Be specific
  and self-contained — Claude Desktop does not have context from the
  current Claude.ai conversation.

**Example invocation:**
```bash
GITHUB_TOKEN="..." RELAY_HMAC_SECRET="..." uv run scripts/relay_send.py \
    fpl9000/claude-relay \
    --direction request \
    --operation claude_prompt \
    --arguments '{"prompt":"Read the mcp-bridge project block and summarize the current open issues."}'
```

**Response format:** `result.content` contains Claude Desktop's final text
response. This may be lengthy if the task involved analysis or summarization.

## Decision Tree

When the user asks you to do something on their local machine, choose the
operation using this decision tree:

1. **Is the user asking to read a specific memory file?**
   → Use `memory_query`. This is instant (no inference) and costs nothing.

2. **Can the task be expressed as a single shell command?**
   → Use `shell_command`. Fast, cheap, no inference involved.

3. **Does the task require LLM reasoning, multi-step actions, or memory writes?**
   → Use `claude_prompt`. This is the most capable but slowest option.

When in doubt, prefer the simpler operation. You can always escalate — for
example, if a `memory_query` reveals that you need to read multiple files
and synthesize them, follow up with a `claude_prompt`.

## End-to-End Workflow

Here is the complete sequence for a typical relay interaction:

1. **User asks:** "What are my active projects on my local machine?"

2. **Choose operation:** This is a memory file read → `memory_query` for `core.md`.

3. **Send the request:**
   ```bash
   export GITHUB_TOKEN="..."
   export RELAY_HMAC_SECRET="..."
   ID=$(uv run scripts/relay_send.py fpl9000/claude-relay \
       --direction request \
       --operation memory_query \
       --arguments '{"path":"core.md"}')
   ```

4. **Inform the user:** "I've sent a request to your local machine to read
   your core memory file. I'll check for a response in about 2 minutes."

5. **Poll for the response** (after minimum interval):
   ```bash
   uv run scripts/relay_receive.py fpl9000/claude-relay \
       --direction response \
       --id "$ID"
   ```

6. **Handle the result:**
   - If exit code 0: Parse the verified response and present the content
     to the user naturally.
   - If exit code 1 (not found): Wait longer, then poll again (with backoff).
   - If exit code 2 (HMAC failed): Alert the user to a potential security issue.
   - If max attempts reached: Inform the user their machine may be offline.

7. **Present the answer:** Summarize the core.md contents in response to
   the user's question.

## Important Notes

- **The local machine must be running.** The MCP bridge polls the relay repo
  periodically (default: every 15 seconds). If the machine is off, sleeping,
  or the bridge is not running, requests will go unanswered.

- **Latency is inherent.** Round-trip times of 1–5 minutes are normal for
  bridge-local operations; `claude_prompt` may take 5–15 minutes depending
  on task complexity. Set expectations with the user.

- **Prompts for `claude_prompt` must be self-contained.** Claude Desktop
  does not have access to the current Claude.ai conversation. Include all
  necessary context in the prompt itself.

- **HMAC failures are serious.** If `relay_receive.py` reports an HMAC
  verification failure, do not use the response content. Report the issue
  to the user.

- **One request at a time.** Do not send multiple relay requests
  simultaneously. Wait for each response (or timeout) before sending
  the next request. This simplifies the interaction and avoids overwhelming
  the bridge's polling loop.
````

---

