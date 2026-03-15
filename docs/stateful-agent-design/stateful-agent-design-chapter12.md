# Stateful Agent System: Detailed Design

**Version:** 1.0 (Draft)<br/>
**Date:** February - March 2026<br/>
**Author:** Claude Opus (with guidance from Fran Litterio, @fpl9000.bsky.social)<br/>

**Companion documents:**
- [Stateful Agent System: Detailed Design](stateful-agent-design.md) — main design document, of which this is a part.
- [Stateful Agent Proposal](stateful-agent-proposal.md) — pre-design architecture proposals.

## 12. Appendix: mark3labs/mcp-go SDK Reference

This appendix documents the subset of the `mark3labs/mcp-go` SDK used by the MCP Bridge Server. All content is drawn directly from the library source and README. It is included here so that the implementer (Claude Sonnet running in Claude Code CLI) has an accurate, targeted reference and does not need to rely on training data, which may reflect an earlier API version.

**Repository:** https://github.com/mark3labs/mcp-go<br/>
**Import paths:** `github.com/mark3labs/mcp-go/mcp` and `github.com/mark3labs/mcp-go/server`

### 12.1 Installation

```bash
go get github.com/mark3labs/mcp-go
```

The `go.mod` file will gain a `require` line like:

```
require github.com/mark3labs/mcp-go v0.x.x
```

No CGO is required. The library is pure Go.

### 12.2 Minimal Complete Example

The following is a complete, working MCP server with one tool, demonstrating the full pattern the bridge uses. Read this first — the subsequent sections break it down piece by piece.

```go
package main

import (
    "context"
    "fmt"
    "os"

    "github.com/mark3labs/mcp-go/mcp"
    "github.com/mark3labs/mcp-go/server"
)

func main() {
    // Create the MCP server.
    //   - "mcp-bridge" is the server name reported during MCP initialization.
    //   - "1.0.0" is the version string.
    //   - WithToolCapabilities(false): advertises tool support; false means the
    //     tool list does NOT change at runtime (no dynamic tool registration
    //     after startup). The bridge registers all tools once at startup.
    //   - WithRecovery(): adds middleware that catches panics in tool handlers
    //     and returns them as MCP tool errors instead of crashing the server.
    s := server.NewMCPServer(
        "mcp-bridge",
        "1.0.0",
        server.WithToolCapabilities(false),
        server.WithRecovery(),
    )

    // Define a tool with one required string parameter.
    tool := mcp.NewTool("hello_world",
        mcp.WithDescription("Say hello to someone"),
        mcp.WithString("name",
            mcp.Required(),
            mcp.Description("Name of the person to greet"),
        ),
    )

    // Register the tool with its handler function.
    s.AddTool(tool, helloHandler)

    // Start the stdio server. This function:
    //   - Reads JSON-RPC messages from os.Stdin (one per line).
    //   - Writes JSON-RPC responses to os.Stdout.
    //   - Blocks until stdin is closed (EOF) or SIGTERM/SIGINT is received.
    //     On Windows, SIGTERM/SIGINT are not reliably deliverable from external
    //     processes (see Section 3.14), but stdin EOF works correctly.
    //   - Returns nil on clean EOF shutdown, non-nil error on I/O failure.
    //
    // CRITICAL: Do NOT write anything to os.Stdout before or during ServeStdio.
    // The MCP protocol uses stdout exclusively for JSON-RPC messages. Any stray
    // write (e.g., fmt.Println, log.Println with the default logger) will corrupt
    // the protocol stream. Use a log file (see Section 3.12) for all output.
    if err := server.ServeStdio(s); err != nil {
        fmt.Fprintf(os.Stderr, "ServeStdio error: %v\n", err)
    }

    // ServeStdio has returned (stdin EOF). Perform graceful shutdown here:
    // kill active subprocesses, flush logs, etc. (see Section 3.14).
}

// helloHandler is a tool handler. Its signature is fixed by the SDK.
//
// Return convention (critical — read this carefully):
//   - Tool execution errors (bad input, operation failed, etc.) MUST be returned
//     as *mcp.CallToolResult with IsError=true, using mcp.NewToolResultError or
//     similar. Return nil Go error in this case.
//   - Return a non-nil Go error ONLY for unexpected infrastructure failures where
//     the handler cannot produce any meaningful result at all. The SDK converts
//     a non-nil Go error into an MCP protocol-level error response, which Claude
//     cannot see or self-correct from.
func helloHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    // RequireString extracts a required string argument. Returns an error if
    // the argument is absent or not a string.
    name, err := request.RequireString("name")
    if err != nil {
        // Tool-level error: return as CallToolResult, not as Go error.
        return mcp.NewToolResultError(err.Error()), nil
    }

    return mcp.NewToolResultText(fmt.Sprintf("Hello, %s!", name)), nil
}
```

### 12.3 Tool Definition

Tools are created with `mcp.NewTool` using a variadic list of `ToolOption` functions:

```go
// NewTool creates a tool with an object-type JSON Schema input schema.
// The name must match exactly the name used in s.AddTool.
func NewTool(name string, opts ...ToolOption) Tool
```

Example:

```go
tool := mcp.NewTool("safe_write_file",
    mcp.WithDescription("Atomically write content to a memory file."),
    mcp.WithString("path",
        mcp.Required(),
        mcp.Description("Absolute path to the file (must be within memory directory)"),
    ),
    mcp.WithString("content",
        mcp.Required(),
        mcp.Description("Complete file content to write"),
    ),
)
```

### 12.4 Parameter Declarations

Each parameter is declared with a typed `With*` `ToolOption` function. The parameter name (first argument) must match the key string used in handler extraction calls (Section 12.6).

**String parameters:**

```go
mcp.WithString("param_name",
    mcp.Required(),                    // Marks the parameter required in the JSON Schema
    mcp.Description("What it does"),   // Human-readable parameter description
    mcp.DefaultString("default_val"),  // Default value when parameter is omitted
    mcp.Enum("val1", "val2"),          // Restrict to enumerated string values
    mcp.MinLength(1),                  // Minimum string length
    mcp.MaxLength(255),                // Maximum string length
    mcp.Pattern("^[a-z]+$"),           // Regex the value must match
)
```

**Numeric parameters:**

```go
// mcp-go has no WithInteger — all numeric parameters use WithNumber (JSON type "number").
// Use GetInt / RequireInt in the handler to receive an int; the SDK handles
// the float64 → int conversion automatically.
mcp.WithNumber("timeout_seconds",
    mcp.Description("Timeout in seconds"),
    mcp.Min(1),    // Minimum value (float64)
    mcp.Max(300),  // Maximum value (float64)
)
```

**Boolean parameters:**

```go
mcp.WithBoolean("allow_memory_read",
    mcp.Description("Grant read access to the memory directory"),
    mcp.DefaultBool(false),
)
```

**Array-of-strings parameters:**

```go
mcp.WithArray("additional_dirs",
    mcp.Description("Extra directories to grant access via --add-dir"),
    mcp.WithStringItems(),  // Declares array elements as strings
)
```

**`PropertyOption` functions** (used inside `With*` parameter declarations):

| Function | Purpose |
|----------|---------|
| `mcp.Required()` | Adds the parameter name to the tool's `required` list |
| `mcp.Description(s)` | Sets the parameter's description |
| `mcp.DefaultString(s)` | Default value for string parameters |
| `mcp.DefaultBool(b)` | Default value for boolean parameters |
| `mcp.Enum(vals...)` | Restricts a string parameter to enumerated values |
| `mcp.MinLength(n)` | Minimum length for string parameters |
| `mcp.MaxLength(n)` | Maximum length for string parameters |
| `mcp.Pattern(re)` | Regex constraint for string parameters |
| `mcp.Min(f)` | Minimum value for numeric parameters |
| `mcp.Max(f)` | Maximum value for numeric parameters |
| `mcp.WithStringItems()` | Constrains array items to type string |

### 12.5 Tool Registration

```go
// AddTool registers a tool and its handler. Must be called before ServeStdio.
// Registering two tools with the same name silently overwrites the first.
s.AddTool(tool, handlerFunc)

// Handler signature — must match exactly:
func handlerName(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error)

// Anonymous function form (equally valid):
s.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    // ...
    return mcp.NewToolResultText("result"), nil
})
```

### 12.6 Argument Extraction

`mcp.CallToolRequest` provides typed accessor methods. There are two patterns:

- **`Require*`** — returns `(T, error)`; the error is non-nil if the argument is absent or has the wrong type. Use for parameters declared `mcp.Required()`.
- **`Get*`** — returns `T`; returns a caller-supplied default if the argument is absent. Use for optional parameters.

```go
// String
str, err := request.RequireString("key")        // (string, error)
str      := request.GetString("key", "default") // string

// Integer  (JSON numbers are float64; SDK auto-converts)
n,   err := request.RequireInt("key")            // (int, error)
n        := request.GetInt("key", 0)             // int

// Float64
f,   err := request.RequireFloat("key")          // (float64, error)
f        := request.GetFloat("key", 0.0)         // float64

// Boolean
b,   err := request.RequireBool("key")           // (bool, error)
b        := request.GetBool("key", false)        // bool

// String slice  (for WithArray + WithStringItems parameters)
ss,  err := request.RequireStringSlice("key")    // ([]string, error)
ss       := request.GetStringSlice("key", nil)   // []string

// Escape hatch: raw map access (avoid if typed accessors suffice)
args := request.GetArguments() // map[string]any
```

### 12.7 Result Constructors

All tool handlers return `*mcp.CallToolResult`. The bridge uses these constructors:

```go
// Successful result containing a plain text string.
// Use this for all successful tool outputs. The bridge returns JSON-encoded
// strings (e.g., marshaled structs) as the text argument.
mcp.NewToolResultText(text string) *mcp.CallToolResult

// Error result — sets IsError: true in the MCP response.
// Claude sees this as a tool error and can self-correct.
// Use for all tool-level failures (invalid input, operation failed, etc.).
mcp.NewToolResultError(text string) *mcp.CallToolResult

// Error result, appending ": <err.Error()>" to the message text.
// Equivalent to NewToolResultError(fmt.Sprintf("%s: %v", text, err)).
mcp.NewToolResultErrorFromErr(text string, err error) *mcp.CallToolResult

// Error result with printf-style formatting.
mcp.NewToolResultErrorf(format string, a ...any) *mcp.CallToolResult
```

**Return convention summary:**

| Situation | What to return |
|-----------|---------------|
| Success | `mcp.NewToolResultText(...)`, `nil` |
| Tool-level error (bad input, op failed) | `mcp.NewToolResultError(...)`, `nil` |
| Infrastructure failure (handler cannot run at all) | `nil`, `fmt.Errorf(...)` |

The third case causes the SDK to send an MCP protocol-level error — Claude cannot see the message and cannot self-correct. Reserve it for truly unexpected failures (e.g., the job manager is in an invalid state).

### 12.8 Server Creation Options

```go
s := server.NewMCPServer(
    name    string,           // Server name (reported during MCP handshake)
    version string,           // Server version string
    opts    ...ServerOption,  // Zero or more option functions (see below)
)
```

**Options used by the bridge:**

```go
// Advertise tool support in the server's capability declaration.
// listChanged=false: the tool list is static after startup.
// listChanged=true:  the server may send tool-list-changed notifications.
// The bridge uses false — all tools are registered before ServeStdio.
server.WithToolCapabilities(listChanged bool) ServerOption

// Add panic-recovery middleware to all tool handlers.
// A panic in any handler is caught and returned as a NewToolResultError
// instead of crashing the bridge process.
server.WithRecovery() ServerOption
```

### 12.9 Starting the Stdio Server

```go
// ServeStdio wraps the MCPServer in a StdioServer and calls Listen(ctx, os.Stdin, os.Stdout).
// Signature:
func ServeStdio(server *MCPServer, opts ...StdioOption) error

// Useful StdioOptions:
//   server.WithErrorLogger(logger *log.Logger)  — redirect SDK internal error output
//   server.WithWorkerPoolSize(n int)             — concurrent tool call workers (default: 5)
//   server.WithQueueSize(n int)                  — tool call queue depth (default: 100)

// Bridge usage (no options needed — defaults are fine):
if err := server.ServeStdio(s); err != nil {
    // Log to file — NEVER to stdout.
    bridgeLog.Printf("ServeStdio returned: %v", err)
}
// Reaches here when stdin is closed (EOF) → begin graceful shutdown.
```

**Shutdown behavior of `ServeStdio`:**
- Returns `nil` when `os.Stdin` reaches EOF (the expected case when Claude Desktop exits).
- Also sets up `signal.Notify` for `syscall.SIGTERM` and `syscall.SIGINT` internally. On Windows these signals are not reliably deliverable from external processes (see Section 3.14), but the `signal.Notify` call compiles and runs without error; stdin EOF remains the authoritative shutdown trigger.
- After `ServeStdio` returns, `main()` should call `jobManager.KillAll()` and exit (see Section 3.14).

### 12.10 Key Implementation Notes

1. **stdout is reserved for MCP protocol traffic.** Any write to `os.Stdout` outside the SDK (including `fmt.Print*`, `log.Print*` with the default logger, or any library that writes to stdout) will corrupt the JSON-RPC stream. Configure the bridge logger to write to a file before calling `ServeStdio`, and never use the default `log` package (which writes to stderr by default — stderr is safe, but a dedicated log file is preferred per Section 3.12).

2. **Tool names must be globally unique.** `s.AddTool` stores tools by name. A second `AddTool` call with an existing name silently replaces the first handler.

3. **Handlers run concurrently.** The `StdioServer` uses a worker pool (default 5 workers) for tool calls. Two tool calls can arrive and execute simultaneously. This is exactly why `safe_write_file` and `safe_append_file` share a `sync.Mutex` — without it, two concurrent write calls would race on the same file.

4. **JSON numbers are `float64`.** The JSON protocol encodes all numbers as `float64`. The `GetInt` / `RequireInt` accessors perform the `float64 → int` conversion (via truncation) automatically. The correct pattern for integer tool parameters is `mcp.WithNumber(...)` in the tool definition and `request.GetInt(...)` / `request.RequireInt(...)` in the handler. There is no `mcp.WithInteger` function in this SDK.

5. **`Required()` in the schema is advisory, not enforced by the SDK.** The `mcp.Required()` property option adds the parameter name to the JSON Schema `required` array, which is conveyed to Claude. However, the SDK does not validate incoming requests against this schema before calling the handler. The handler is responsible for validating its own inputs — which is why `RequireString`, `RequireInt`, etc. exist and should be used for required parameters.
