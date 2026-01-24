# AI Talk Skill Design

## Overview

The `ai-talk` skill enables AI agents to communicate with each other over local TCP connections.  This allows multiple AI instances (potentially running in different processes or terminals) to exchange textual messages in real-time.

## Design Goals

1. **Non-blocking operation** - Listening for messages should not block the AI's tool call indefinitely.
2. **Simplicity** - The protocol and scripts should be straightforward to use.
3. **Reliability** - Messages should be delivered reliably with clear error reporting.
4. **Zero configuration** - Should work without external dependencies beyond Python and `uv`.

## Architecture

### Message Format

Messages are exchanged as UTF-8 encoded text using a simple framing protocol:

```
<length>:<message>
```

Where:
- `<length>` is the byte length of the message as a decimal integer
- `:` is a literal colon separator
- `<message>` is the UTF-8 encoded message content

Example: `13:Hello, World!`

This framing allows reliable message boundary detection over TCP streams.

### Scripts

The skill provides four scripts:

#### 1. `scripts/listen.py` - Start Background Listener

Starts a TCP listener as a background daemon process.

**Usage:**
```
uv run scripts/listen.py start --port <port> [--message-file <path>]
uv run scripts/listen.py stop --port <port>
uv run scripts/listen.py status --port <port>
```

**Behavior:**
- The `start` subcommand spawns a background process that listens on the specified port.
- Incoming messages are appended to a message file (default: `~/.ai-talk/<port>/inbox.jsonl`).
- Each message is stored as a JSON object with fields: `timestamp`, `sender_port`, `message`.
- A PID file is written to `~/.ai-talk/<port>/listener.pid` for process management.
- The `stop` subcommand terminates the background listener.
- The `status` subcommand reports whether a listener is running on the specified port.

**Output (JSON):**
```json
{
  "status": "started",
  "port": 9001,
  "pid": 12345,
  "message_file": "/home/user/.ai-talk/9001/inbox.jsonl"
}
```

#### 2. `scripts/check.py` - Check for Messages

Reads and optionally clears pending messages from the inbox.

**Usage:**
```
uv run scripts/check.py --port <port> [--clear] [--limit <n>]
```

**Options:**
- `--port` - The port number whose inbox to check.
- `--clear` - Remove messages from the inbox after reading them.
- `--limit` - Maximum number of messages to return (default: all).

**Output (JSON):**
```json
{
  "port": 9001,
  "message_count": 2,
  "messages": [
    {
      "timestamp": "2026-01-16T10:30:45.123456",
      "sender_port": 9002,
      "message": "Hello from the other AI!"
    },
    {
      "timestamp": "2026-01-16T10:31:02.789012",
      "sender_port": 9002,
      "message": "Are you there?"
    }
  ]
}
```

#### 3. `scripts/send.py` - Send a Message

Connects to another AI's listener and sends a message.

**Usage:**
```
uv run scripts/send.py --to-port <port> --from-port <port> --message <text>
uv run scripts/send.py --to-port <port> --from-port <port> --message-file <path>
```

**Options:**
- `--to-port` - The destination port (where the other AI is listening).
- `--from-port` - The sender's port (for identification/reply purposes).
- `--message` - The message text to send.
- `--message-file` - Read message from a file instead of command line.
- `--timeout` - Connection timeout in seconds (default: 10).

**Output (JSON):**
```json
{
  "status": "sent",
  "to_port": 9002,
  "from_port": 9001,
  "message_length": 25,
  "timestamp": "2026-01-16T10:32:15.456789"
}
```

#### 4. `scripts/discover.py` - Discover Active Listeners

Lists all active AI-talk listeners on the local machine.

**Usage:**
```
uv run scripts/discover.py
```

**Output (JSON):**
```json
{
  "listeners": [
    {"port": 9001, "pid": 12345, "started": "2026-01-16T10:00:00"},
    {"port": 9002, "pid": 12346, "started": "2026-01-16T10:05:00"}
  ]
}
```

## Non-Blocking Design

The primary challenge with AI-to-AI communication is that tool calls should not block indefinitely.  This design addresses the challenge through several mechanisms:

### Background Listener Process

The listener runs as a separate daemon process, completely decoupled from the AI's tool calls.  This means:

1. Starting a listener returns immediately after spawning the background process.
2. The listener continues running independently of the AI's session.
3. Checking for messages is a fast file read operation, not a blocking network call.

### Polling Pattern

The AI uses a polling pattern to check for messages:

1. Start a listener once at the beginning of a conversation.
2. Periodically call `check.py` to see if any messages have arrived.
3. Process messages and send responses as needed.

The polling interval is up to the AI's discretion based on conversation context.  During active communication, the AI might check frequently.  During other work, it might check less often.

### Mitigations for Blocking Scenarios

If background processes are not feasible in certain environments, the following mitigations apply:

#### Mitigation 1: Short Timeout Listener

An alternative `listen-once.py` script that:
- Listens for a single message with a configurable timeout (default: 5 seconds).
- Returns immediately if a message arrives.
- Returns a "no message" response if the timeout expires.
- The AI calls this repeatedly when expecting a message.

```
uv run scripts/listen-once.py --port <port> --timeout <seconds>
```

#### Mitigation 2: Callback File

The listener writes a "callback" file when a message arrives.  The AI can use filesystem monitoring (or simple file existence checks) to detect incoming messages without calling any script.

```
~/.ai-talk/9001/callback  # Exists when unread messages are waiting
```

#### Mitigation 3: Structured Conversation Protocol

For structured conversations, AIs can use a request-response pattern:
1. AI-A sends a message to AI-B.
2. AI-A immediately calls `listen-once.py` with a reasonable timeout.
3. AI-B processes the message and sends a response.
4. AI-A receives the response or times out.

This pattern bounds the maximum blocking time to the timeout value.

## Typical Conversation Flow

### AI-A (Initiator)

```
1. AI-A starts a listener on port 9001
2. AI-A sends a message to AI-B on port 9002, identifying itself as port 9001
3. AI-A checks its inbox for a response
4. AI-A processes the response and continues the conversation
```

### AI-B (Responder)

```
1. AI-B starts a listener on port 9002
2. AI-B checks its inbox and finds a message from port 9001
3. AI-B sends a response to port 9001
4. AI-B checks for the next message
```

### Port Discovery

AIs can discover each other through:

1. **Explicit configuration** - The user tells each AI which port the other is using.
2. **Discovery script** - AIs run `discover.py` to see active listeners.
3. **Convention** - Use predictable ports like 9001 for the first AI, 9002 for the second, etc.

## Data Storage

All data is stored under `~/.ai-talk/`:

```
~/.ai-talk/
├── 9001/
│   ├── listener.pid      # PID of the listener process
│   ├── inbox.jsonl       # Incoming messages (JSON Lines format)
│   ├── outbox.jsonl      # Sent messages (optional, for logging)
│   └── callback          # Exists when unread messages are present
├── 9002/
│   └── ...
└── config.json           # Optional global configuration
```

## Security Considerations

1. **Localhost only** - All listeners bind to `127.0.0.1` exclusively.  Remote connections are not accepted.

2. **No authentication** - This design assumes a trusted local environment.  Any process on the local machine can send messages to any listener.

3. **Message validation** - Scripts validate message format but do not sanitize content.  AIs should treat received messages as untrusted input.

4. **Port restrictions** - Only ports above 1024 are allowed to avoid requiring elevated privileges.

5. **Resource limits** - Listeners should implement reasonable limits:
   - Maximum message size (e.g., 1 MB)
   - Maximum inbox size (e.g., 100 messages)
   - Connection rate limiting

## Error Handling

All scripts return JSON output with consistent error reporting:

```json
{
  "status": "error",
  "error_code": "CONNECTION_REFUSED",
  "error_message": "Could not connect to port 9002: Connection refused",
  "details": {
    "port": 9002,
    "timeout": 10
  }
}
```

Common error codes:
- `PORT_IN_USE` - The requested port is already in use by another process.
- `CONNECTION_REFUSED` - No listener on the target port.
- `CONNECTION_TIMEOUT` - Connection attempt timed out.
- `INVALID_PORT` - Port number out of valid range.
- `LISTENER_NOT_RUNNING` - No listener found for the specified port.
- `MESSAGE_TOO_LARGE` - Message exceeds size limit.

## Future Enhancements

1. **Encryption** - Optional TLS encryption for message privacy.
2. **Message types** - Support for different message types (text, JSON, binary).
3. **Conversation threads** - Message threading with conversation IDs.
4. **Acknowledgments** - Delivery and read receipts.
5. **Broadcast** - Send messages to multiple listeners simultaneously.
6. **Named channels** - Register listeners with human-readable names instead of ports.

## Dependencies

- Python 3.10+
- `uv` for script execution
- No external Python packages required (uses only standard library)

## Example Session

### Terminal 1 (AI-A)

```
$ uv run scripts/listen.py start --port 9001
{"status": "started", "port": 9001, "pid": 12345}

$ uv run scripts/send.py --to-port 9002 --from-port 9001 --message "Hello AI-B!"
{"status": "sent", "to_port": 9002, "from_port": 9001}

$ uv run scripts/check.py --port 9001 --clear
{"port": 9001, "message_count": 1, "messages": [
  {"sender_port": 9002, "message": "Hello AI-A! Nice to meet you."}
]}
```

### Terminal 2 (AI-B)

```
$ uv run scripts/listen.py start --port 9002
{"status": "started", "port": 9002, "pid": 12346}

$ uv run scripts/check.py --port 9002 --clear
{"port": 9002, "message_count": 1, "messages": [
  {"sender_port": 9001, "message": "Hello AI-B!"}
]}

$ uv run scripts/send.py --to-port 9001 --from-port 9002 --message "Hello AI-A! Nice to meet you."
{"status": "sent", "to_port": 9001, "from_port": 9002}
```
