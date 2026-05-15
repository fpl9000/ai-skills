# Critical Design Review Prompt — Stateful Agent System

## Instructions for Use

Paste this prompt into a new conversation with Claude Opus (extended thinking
enabled), followed immediately by the concatenated content of all chapter files
from the `docs/stateful-agent-design/` directory (in chapter order), then
Chapter 9. Do not summarize or paraphrase the design — provide the full text.

---

## Prompt

You are acting as a skeptical senior systems architect performing a critical
design review of a proposed Stateful Agent System. Your job is to find
problems — not to validate the design or encourage the author. Do not soften
criticisms. If something is underspecified, say so directly. If something seems
wrong or fragile, say so. Be thorough and precise.

### Context

This system is being built to give a Claude-based AI agent persistent memory
across conversations. The agent runs inside Claude.ai (not Claude Code), which
means:

- The agent has no persistent process — it is stateless between turns.
- All "agentic" behavior is implemented via MCP (Model Context Protocol) tool
  calls to an external bridge server.
- The bridge server runs locally on a Windows 11 machine (Cygwin environment).
- Network egress from the Claude.ai environment is restricted: `git
  clone/push/pull` are blocked. All GitHub operations must go through the
  GitHub REST API.
- The primary developer is a solo retired engineer. Token efficiency matters —
  he is on a fixed-cost Claude plan.
- The system must be robust to network failures, race conditions, and the
  inherent statelessness of the LLM between turns.

### What to Review

The full design document follows this prompt. It is divided into chapters.
**Chapter 9 covers future enhancements not targeted for near-term
implementation.** Review Chapter 9 only to the extent that its planned future
features reveal constraints or incompatibilities with the current architecture.
Do not critique Chapter 9 features as if they were immediate implementation
targets.

### Review Categories

Structure your findings under the following headings. For each finding, state:
(a) what the issue is, (b) why it matters, and (c) if possible, what a better
approach might be.

**1. Design Flaws and Logical Contradictions**
Identify anything internally inconsistent, self-contradictory, or logically
unsound in the design. This includes protocol definitions, state machine
transitions, error handling logic, and data flow descriptions.

**2. Underspecified Areas That Would Block Implementation**
Identify anything that is described at too high a level of abstraction to
implement without making significant design decisions not covered in the
document. A future implementer should not have to guess.

**3. Reliability and Failure Mode Concerns**
Identify scenarios where the system could fail silently, corrupt state, or
behave incorrectly under realistic conditions such as: network interruptions,
partial writes, concurrent access, timeout/retry loops, or agent crashes
mid-operation.

**4. Security Concerns**
Identify any authentication weaknesses, potential for unauthorized access,
replay attack vectors, credential exposure risks, or places where the trust
model is unclear or insufficiently enforced.

**5. Scalability and Performance Concerns**
Identify anything that would become a bottleneck or break down as the volume of
memory blocks, conversation history, or tool call frequency grows. Note if any
O(n) or worse operations are performed in a hot path.

**6. Extensibility and Future Compatibility**
With reference to Chapter 9 only where relevant: identify places where the
current design would make planned future enhancements difficult, expensive, or
impossible to add without significant rework.

**7. Surprises and Unusual Design Choices**
Note anything that struck you as unconventional, surprising, or that deviates
from standard practice in distributed systems or agent architectures without an
obvious justification. These are not necessarily flaws — but they warrant
explicit acknowledgment.

### Assumptions

Before or after your findings, explicitly list the key assumptions the design
makes. For each assumption, assess: (a) how likely it is to hold in practice,
and (b) what happens to the system if the assumption is violated.

### Overall Verdict

After completing your review, give a concise overall verdict:

- Is the design ready to proceed to a minimal implementation (store, index, and
  retrieve memory blocks only — deferring bash command execution and sub-agent
  orchestration)?
- If not, what are the blocking issues that must be resolved first?
- If yes, are there any issues significant enough that they should be addressed
  in parallel with or immediately after the minimal implementation, before
  further features are added?

Be direct. A verdict of "not ready" with clear reasons is more useful than a
qualified "mostly ready" that obscures real problems.

---

*End of prompt. The full design document follows immediately below.*
