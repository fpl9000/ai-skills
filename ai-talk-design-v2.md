# AI Talk Skill Design v2

## Overview

The `ai-talk` skill enables AI agents to communicate with each other over local TCP connections using ZeroMQ. This allows multiple AI instances (potentially running in different processes or terminals) to exchange textual messages in real-time using a hub-and-spoke topology.

## Changes from v1

This design replaces the custom TCP framing protocol from v1 with ZeroMQ, which provides:

- **Built-in message framing** — No need for manual `length:message` protocol
- **Hub-and-spoke topology** — Native support via ROUTER/DEALER sockets
- **Late binding** — Connections succeed even if hub starts after spokes
- **Multi-part messages** — Built-in support for structured messages
- **Transport flexibility** — TCP, IPC (Unix sockets), or in-process

### Why ZeroMQ over alternatives?

| Option | Verdict | Reason |
|--------|---------|--------|
| Custom TCP (v1) | ❌ Replaced | Requires manual framing, point-to-point only |
| AT Protocol | ❌ Overkill | Designed for internet federation, requires PDS server |
| Redis Pub/Sub | ❌ External dependency | Requires running Redis server |
| NATS | ❌ External dependency | Requires running NATS server |
| ZeroMQ | ✅ Selected | Library-only, no server process, hub-and-spoke built-in |

ZeroMQ is a library, not a server. The messaging patterns are embedded in your Python process—no external daemon required. The `pyzmq` package works seamlessly with `uv run` using PEP 723 inline metadata.

## Design Goals

1. **Non-blocking operation** — Listening for messages should not block the AI's tool call indefinitely.
2. **Hub-and-spoke topology** — Multiple AIs can communicate through a central hub.
3. **Simplicity** — Scripts should be straightforward to use.
4. **Reliability** — Messages should be delivered reliably with clear error reporting.
5. **Zero configuration** — Should work without external services (no Redis, no NATS, no PDS).
6. **Same-machine only** — Designed for local inter-process communication, not cross-network.

## Architecture

### Topology

```
                    ┌─────────────┐
         ┌─────────►│    HUB      │◄─────────┐
         │          │   :9000     │          │
         │          └──────┬──────┘          │
         │                 │                 │
         ▼                 ▼                 ▼
    ┌─────────┐       ┌─────────┐       ┌─────────┐
    │  AI-A   │       │  AI-B   │       │  AI-C   │
    │ "alpha" │       │ "beta"  │       │ "gamma" │
    └─────────┘       └─────────┘       └─────────┘
```

All AIs connect to a central hub. The hub routes messages between registered AIs.

### Socket Pattern: ROUTER/DEALER

ZeroMQ's ROUTER/DEALER pattern provides bidirectional hub-and-spoke messaging:

- **Hub**: Uses a `ROUTER` socket that binds and can address messages to specific connected peers
- **Spokes**: Use `DEALER` sockets that connect to the hub

The ROUTER socket automatically tracks connected peers and can route messages to specific destinations.

### Message Format

Messages are multi-part ZeroMQ frames:

```
Frame 0: Destination identity (e.g., "beta")
Frame 1: Source identity (e.g., "alpha")
Frame 2: Message type (e.g., "message", "register", "ack")
Frame 3: Payload (UTF-8 text or JSON)
```

### Identity System

AIs register with human-readable identities (not just ports):

- `"alpha"`, `"beta"`, `"gamma"` — Simple names
- `"research-assistant"`, `"code-reviewer"` — Descriptive names

The hub maintains an identity-to-connection mapping and routes messages accordingly.

## Scripts

The skill provides five scripts:

### 1. `scripts/hub.py` — Start the Message Hub

Starts the central message router as a background daemon process.

**Usage:**
```bash
uv run scripts/hub.py start [--port <port>]
uv run scripts/hub.py stop [--port <port>]
uv run scripts/hub.py status [--port <port>]
```

**Default port:** 9000

**Behavior:**
- The `start` subcommand spawns a background process running the ROUTER socket.
- The hub tracks registered AI identities and routes messages between them.
- A PID file is written to `~/.ai-talk/hub-<port>.pid` for process management.
- The hub logs activity to `~/.ai-talk/hub-<port>.log`.

**Output (JSON):**
```json
{
  "status": "started",
  "port": 9000,
  "pid": 12345,
  "endpoint": "tcp://127.0.0.1:9000"
}
```

### 2. `scripts/register.py` — Register an AI Identity

Registers this AI with the hub and starts a background listener for incoming messages.

**Usage:**
```bash
uv run scripts/register.py --identity <name> [--hub-port <port>]
uv run scripts/register.py --identity alpha --hub-port 9000
```

**Behavior:**
- Connects to the hub as a DEALER socket.
- Sends a registration message with the specified identity.
- Spawns a background process that listens for incoming messages.
- Incoming messages are appended to `~/.ai-talk/<identity>/inbox.jsonl`.
- A PID file is written to `~/.ai-talk/<identity>/listener.pid`.

**Output (JSON):**
```json
{
  "status": "registered",
  "identity": "alpha",
  "hub": "tcp://127.0.0.1:9000",
  "pid": 12346,
  "inbox": "/home/user/.ai-talk/alpha/inbox.jsonl"
}
```

### 3. `scripts/send.py` — Send a Message

Sends a message to another registered AI via the hub.

**Usage:**
```bash
uv run scripts/send.py --from <identity> --to <identity> --message <text>
uv run scripts/send.py --from alpha --to beta --message "Hello!"
uv run scripts/send.py --from alpha --to beta --message-file response.txt
```

**Options:**
- `--from` — Sender's registered identity (required).
- `--to` — Recipient's registered identity (required).
- `--message` — The message text to send.
- `--message-file` — Read message from a file instead of command line.
- `--hub-port` — Hub port if not default (9000).
- `--timeout` — Send timeout in seconds (default: 10).

**Output (JSON):**
```json
{
  "status": "sent",
  "from": "alpha",
  "to": "beta",
  "message_length": 6,
  "timestamp": "2026-01-24T10:32:15.456789Z"
}
```

### 4. `scripts/check.py` — Check for Messages

Reads and optionally clears pending messages from the inbox.

**Usage:**
```bash
uv run scripts/check.py --identity <name> [--clear] [--limit <n>]
```

**Options:**
- `--identity` — The identity whose inbox to check (required).
- `--clear` — Remove messages from the inbox after reading them.
- `--limit` — Maximum number of messages to return (default: all).

**Output (JSON):**
```json
{
  "identity": "alpha",
  "message_count": 2,
  "messages": [
    {
      "timestamp": "2026-01-24T10:30:45.123456Z",
      "from": "beta",
      "message": "Hello from beta!"
    },
    {
      "timestamp": "2026-01-24T10:31:02.789012Z",
      "from": "beta",
      "message": "Are you there?"
    }
  ]
}
```

### 5. `scripts/discover.py` — Discover Hub and Registered AIs

Lists the running hub and all registered AI identities.

**Usage:**
```bash
uv run scripts/discover.py [--hub-port <port>]
```

**Output (JSON):**
```json
{
  "hub": {
    "port": 9000,
    "pid": 12345,
    "started": "2026-01-24T10:00:00Z"
  },
  "registered_identities": [
    {"identity": "alpha", "connected": true, "registered_at": "2026-01-24T10:05:00Z"},
    {"identity": "beta", "connected": true, "registered_at": "2026-01-24T10:06:00Z"}
  ]
}
```

## Non-Blocking Design

### Background Processes

Both the hub and the per-identity listeners run as background daemon processes:

1. Starting the hub returns immediately after spawning the daemon.
2. Registering an identity spawns a listener daemon and returns immediately.
3. Checking for messages reads from a file—no blocking network calls.
4. Sending a message has a configurable timeout (default: 10 seconds).

### Polling Pattern

AIs use a polling pattern to check for messages:

1. Ensure the hub is running (start it if needed).
2. Register an identity once at the beginning of a conversation.
3. Periodically call `check.py` to see if any messages have arrived.
4. Process messages and send responses as needed.

### ZeroMQ Non-Blocking Features

ZeroMQ provides additional non-blocking capabilities:

- **`zmq.NOBLOCK`** — Poll sockets without blocking.
- **`zmq.Poller`** — Monitor multiple sockets simultaneously.
- **High-water marks** — Configure queue limits to prevent memory exhaustion.

## Data Storage

All data is stored under `~/.ai-talk/`:

```
~/.ai-talk/
├── hub-9000.pid          # PID of the hub process (port in filename)
├── hub-9000.log          # Hub activity log
├── alpha/
│   ├── listener.pid      # PID of alpha's listener process
│   ├── inbox.jsonl       # Incoming messages (JSON Lines format)
│   └── outbox.jsonl      # Sent messages (optional, for logging)
├── beta/
│   └── ...
└── config.json           # Optional global configuration
```


## File Synchronization

The inbox file (`inbox.jsonl`) may be accessed concurrently by multiple processes:

- **Writer**: The listener daemon appends incoming messages
- **Reader**: The `check.py` script reads (and optionally clears) messages

Without synchronization, a race condition can occur:

```
Time T1: Listener begins appending message to inbox.jsonl
Time T2: check.py --clear reads inbox.jsonl
Time T3: check.py --clear truncates inbox.jsonl
Time T4: Listener finishes writing
Result: Message from T1 is lost
```

### Solution: Cross-Platform File Locking with `portalocker`

All scripts use the `portalocker` library for cross-platform advisory file locking. This library wraps:

- **Unix/Linux/macOS**: `fcntl.flock()`
- **Windows**: `win32file.LockFileEx()` (via pywin32) or `msvcrt.locking()`

```python
import json
import portalocker

def append_message(inbox_path: str, message: dict) -> None:
    """Append a message to the inbox with exclusive locking."""
    with portalocker.Lock(inbox_path, mode='a', timeout=10) as f:
        f.write(json.dumps(message) + '\n')
        f.flush()
    # Lock released automatically when context manager exits

def read_messages(inbox_path: str, clear: bool = False) -> list[dict]:
    """Read messages from inbox with exclusive locking."""
    messages = []
    mode = 'r+' if clear else 'r'
    
    try:
        with portalocker.Lock(inbox_path, mode=mode, timeout=10) as f:
            for line in f:
                if line.strip():
                    messages.append(json.loads(line))
            if clear:
                f.seek(0)
                f.truncate()
    except FileNotFoundError:
        pass  # No inbox yet, return empty list
    
    return messages
```

### Dependency Declaration

The `portalocker` dependency is declared in each script's PEP 723 metadata:

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyzmq>=26.0.0",
#     "portalocker>=2.0.0",
# ]
# ///
```

### Important Notes

1. **Advisory locking**: Like all userspace file locking, `portalocker` uses advisory locks—all processes must cooperate by acquiring locks. A process that ignores locking can still cause corruption.

2. **Timeout handling**: The `timeout=10` parameter causes `portalocker.LockException` if the lock cannot be acquired within 10 seconds. Scripts should handle this gracefully.

3. **Lock scope**: Locks are held only during the file operation (within the `with` block), minimizing contention between the listener and reader processes.

4. **Platform support**:
   - **Linux/macOS/BSD**: Uses `fcntl.flock()` 
   - **Windows**: Uses Win32 API (`LockFileEx`) or falls back to `msvcrt.locking()`
   - No platform-specific code needed in the skill scripts



## Security Considerations

1. **Localhost only** — The hub binds to `127.0.0.1` exclusively. Remote connections are not accepted.

2. **No authentication** — This design assumes a trusted local environment. Any process on the local machine can connect to the hub and send messages.

3. **Message validation** — Scripts validate message format but do not sanitize content. AIs should treat received messages as untrusted input.

4. **Port restrictions** — Only ports above 1024 are allowed to avoid requiring elevated privileges.

5. **Resource limits** — The hub implements reasonable limits:
   - Maximum message size: 1 MB
   - Maximum queued messages per identity: 100
   - Connection timeout: 30 seconds

## Scope Limitations

This skill is explicitly designed for **same-machine communication only**:

- ✅ Multiple terminals on one computer
- ✅ Multiple AI processes on one server
- ✅ Docker containers on the same host (with shared network)
- ❌ Cross-computer communication (blocked by NAT/firewalls)
- ❌ Cloud-to-cloud AI communication (would require a relay server)

ZeroMQ does not perform NAT traversal. For cross-network communication, you would need a relay server with a public IP, which is outside the scope of this skill.

## Error Handling

All scripts return JSON output with consistent error reporting:

```json
{
  "status": "error",
  "error_code": "HUB_NOT_RUNNING",
  "error_message": "No hub found on port 9000. Start one with: uv run scripts/hub.py start",
  "details": {
    "port": 9000
  }
}
```

Common error codes:
- `HUB_NOT_RUNNING` — No hub process found on the specified port.
- `IDENTITY_NOT_REGISTERED` — The specified identity is not registered with the hub.
- `RECIPIENT_NOT_FOUND` — The destination identity is not registered.
- `CONNECTION_TIMEOUT` — Connection attempt timed out.
- `SEND_TIMEOUT` — Message send timed out.
- `MESSAGE_TOO_LARGE` — Message exceeds size limit (1 MB).
- `INVALID_IDENTITY` — Identity contains invalid characters.

## Dependencies

- Python 3.10+
- `uv` for script execution
- `pyzmq` — ZeroMQ Python bindings (installed automatically via PEP 723 metadata)
- `portalocker` — Cross-platform file locking (installed automatically via PEP 723 metadata)

All scripts include inline dependency declarations:

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyzmq>=26.0.0",
#     "portalocker>=2.0.0",
# ]
# ///
```

## Example Session

### Terminal 0 (Start Hub)

```bash
$ uv run scripts/hub.py start
{"status": "started", "port": 9000, "pid": 12345}
```

### Terminal 1 (AI-A)

```bash
$ uv run scripts/register.py --identity alpha
{"status": "registered", "identity": "alpha", "hub": "tcp://127.0.0.1:9000"}

$ uv run scripts/send.py --from alpha --to beta --message "Hello AI-B!"
{"status": "sent", "from": "alpha", "to": "beta"}

$ uv run scripts/check.py --identity alpha --clear
{"identity": "alpha", "message_count": 1, "messages": [
  {"from": "beta", "message": "Hello AI-A! Nice to meet you."}
]}
```

### Terminal 2 (AI-B)

```bash
$ uv run scripts/register.py --identity beta
{"status": "registered", "identity": "beta", "hub": "tcp://127.0.0.1:9000"}

$ uv run scripts/check.py --identity beta --clear
{"identity": "beta", "message_count": 1, "messages": [
  {"from": "alpha", "message": "Hello AI-B!"}
]}

$ uv run scripts/send.py --from beta --to alpha --message "Hello AI-A! Nice to meet you."
{"status": "sent", "from": "beta", "to": "alpha"}
```

### Discovery

```bash
$ uv run scripts/discover.py
{
  "hub": {"port": 9000, "pid": 12345},
  "registered_identities": [
    {"identity": "alpha", "connected": true},
    {"identity": "beta", "connected": true}
  ]
}
```

## Future Enhancements

1. **Message acknowledgments** — Delivery and read receipts.
2. **Message types** — Support for different message types (text, JSON, binary).
3. **Conversation threads** — Message threading with conversation IDs.
4. **Broadcast** — Send messages to all registered identities.
5. **Groups/channels** — Named channels that multiple AIs can subscribe to.
6. **Encryption** — Optional message encryption for sensitive communications.
7. **IPC transport** — Option to use Unix domain sockets for faster local communication.


