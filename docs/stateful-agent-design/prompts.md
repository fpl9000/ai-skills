# Design Issues

1. Memory file `core.md` is treated specially: it has dedicated tools to access its contents: `memory_get_core` and `memory_write_core`. Is there a compelling reason to treat `core.md` specially, when the existing tools, `memory_get_block` and `memory_write_block`, could also read/write `core.md`?
2. ...

# 2026-06-12

Please clone my GitHub repo named `ai-skills`, implement the changes to `docs/stateful-agent-design/stateful-agent-design.md` (and to its associated chapter files) specified by `docs/stateful-agent-design/design-update-plan.md` in that repo, and create a PR with the updated design changes. Note that the update plan requires reading other files in the repo to understand the full scope of the project, as specified under **Source Materials** at the top of the plan.

The goal is to update the *Stateful Agent Design* files according to the update plan, resulting in an updated design that is coherent, internally consistent, and ready for a critical review. If there are inconsistencies between the plan and the older documents it references, do what the plan specifies. If you have any major questions that I can help clarify, please ask them in advance of changing the original design document, but I trust you to decide any minor issues you encounter.

# 2026-06-05

Thanks. I've merged that PR.

§3.5 (*`summary` parameter contract*), looks good as is — I have no changes to propose.

§3.6 (*Schema for `memory_get_index()`*) also looks good. The only minor change I would request is to use an 8-character handle (e.g., `abc1def2`) instead of `abc1`.

§3.8 (*Where do branches store on disk?*) says the proposed naming convention is `<basename>.branch-<handle>-<ISO8601compact>.<ext>` with this example: `core.branch-h7k3xy90-20260520T1423.md`. Before I sign off on this, can you remind me of the meaning of the `<ISO8601compact>` date/time?
# 2026-06-04

Thanks. I merged that PR. I changed `design-update-plan.md` so the 30-day retention window for handles is now 60 days. I also made a minor formatting change to `docs/stateful-agent-design/stateful-agent-design-chapter9.md`​. You should do a pull to get those changes.

You said the handle retention window is exposed by a configuration parameter, but I don't see it in §3.2, *Configuration*, in `stateful-agent-design-chapter3.md`. In fact, the example YAML config file in that section continues to use the old "session" instead of "handle" terminology. Can you update that section with the new terminology and that new config parameter?
# 2026-05-26

Thanks for creating that PR. I've deleted branch `docs/plan-resolve-section3` from the GitHub repo. I made a small edit to `docs/stateful-agent-design/design-update-plan.md` that is not in your clone of the repo, so you might want to do a pull to get the change (or delete your clone and make a whole new one). My change is that the following lines at the top of the file now have 2 trailing spaces, which is widely accepted markdown syntax that means to insert a newline after that line:

```
**Author:** Claude Opus 4.7 (with guidance from Fran)  
**Date:** May 2026  
```

Please remember to use 2 trailing spaces in markdown to indicate a newline, otherwise the adjacent lines will be wrapped into a single paragraph by many markdown readers, like Obsidian.

Regarding changing the design to have the bridge persist state data between invocations, I think this is necessary to avoid the loss of state when I close the Claude Desktop app. As you say, it's just a matter of writing some JSON (likely periodically) and reading it back at startup. I think this direction change impacts §3.7 and §3.11 in `docs/stateful-agent-design/design-update-plan.md`, but you might see other places that need to be updated.
# 2026-05-25

Thanks. I agree with your changes to §3.3 and §2.7. We need simplicity in the design, as we "decelerate" towards implementation.

And those are great suggestions regarding how best to use rich error values. Please codify them in §3.10 now, and then we can discuss §3.4, *Handle generation policy*.

Also, I realize I gave you two different sets of instructions in my last prompt. Thanks for handling that gracefully.

---

For §3.2, I agree with your recommendation to defer this until we have some experience with the original RMW branching. I also agree with having `memory_get_*` return a flag `{ changed_since_last_read: true }` on a re-read that shows different content than the last read by this handle. Please update the plan to say that and that we'll see how it performs before re-visiting this.
# 2026-05-24

Thanks. I agree with using Option 2. The value of `index.md`​ is not that it is human-readable but that it gives the LLM a broad overview of its memory blocks. So it's fine that it is derived and only available via a tool call (`memory_get_index()`).

Unless you disagree, we can move on to the questions in §3, *Open Questions Still to Resolve*. Let's tackle them one by one. As we resolve each open question, please collect the changes to `design-update-plan.md` in a branch in your clone of the repo. Once you have all the changes for §3, then create a PR for me.

For §3.1, *Wake-up phase mechanism*, I agree with your recommendation to make it manually triggered by the user. The skill should teach the LLM to call tool `memory_run_maintenance(handle)`, which will use a sub-agent to do the semantic merge. Please modify that section in your branch.
# 2026-05-23

There's one ratified decision that I'm not sure about: "2.8 Index is always canonical, mechanically merged", which states: "The index does not branch". The rest of that section describes an algorithm where the bridge merges `index.md` mechanically, as follows:

- `updated_at` → latest wins.
- `summary` → latest wins (if the writer supplied one; otherwise unchanged).
- New rows → union.
- Deleted rows (not yet supported in v1, but for future): deletion-wins or latest-wins depending on policy.

But given that the current memory write is by definition the "latest", won't the "latest wins" rules mean the bridge *always* replace the `summary` and `updated_at` fields in the corresponding row in `index.md`? Even if I'm wrong, this design allows memory block summaries to leak between conversations. IMO, `index.md` should branch, because it contains semantic information (the `summary`) that needs to be semantically merged.
# 2026-05-21

Thanks for creating that analysis. I've read it, and I can provide some feedback right off:

1. Regarding issue "2.1 — Tool signatures omit the handle parameter", the tool signatures you gave look good to me, so they should go  into the design. But there is no tool to update `index.md`. Will the bridge update (and possibly branch) `index.md` based on the `summary` parameter passed to `memory_write_block`, obviating the need for a tool to update `index.md`?

2. Regarding issue "2.2 — Read-your-own-writes through an 'invisible branch' is not defined", when conversation X writes to block B creating branch B1, all subsequent reads of block B by conversation X see branch B1. This lets the LLM see only its own previous writes (i.e., it prevents memories leaking between conversations). As you say in your analysis, this means "the bridge must track `handle → block → branch` mapping and resolve reads against that map" and the design needs to specify that.

	- NOTE: There are no branches of branches. Once a memory file is branched by a conversation, the branch can never be branched, because in that conversation all future reads/writes to the canonical file name access the branch, avoiding all race conditions.

3. Regarding issue "2.3 — The wake-up phase mechanism is unspecified", in the desktop app, Claude Code and Claude Cowork have mechanisms to perform periodic unattended tasks, but I'm not sure if Claude Chat has the same functionality. I know that  AutoHotkey on my Windows 11 system can control Claude Chat in my absence, sending it an automated prompt to initiate unattended wake-up periods. If that's too fragile, I'm can ask the LLM to merge branches until we find a good automated solution.

4. Regarding issue "2.4 — Atomic block-plus-index update is asserted but not specified", your analysis gave this example of the correct logic: "Concretely: write a temp block file, update the index referencing the temp path, fsync, then atomic-rename the temp to the canonical name." Did you mean to say "update the index referencing the temp path"? Because that leaves the index entry pointing at a non-existent temp file.

Other notes:

1. The design probably should specify that when a merge starts, the bridge needs to hold a mutex that blocks all memory reads and writes until the merge is complete. This lets the bridge have free reign to modify memory files during merges, and it prevents new branches from being created during a merge.

2. Open question: If conversation X reads memory block B, then conversation Y writes block B (changing it from what X has read), then conversation X it needs to read block B again (because compaction removed block B's context from the context window), it will see conversation Y's memories in block B, which might be confusing. In this use case, should Y's write to block B cause a branch? This is a different branching cause than with the read-modify-write use case we have until now assumed causes all branches.
# 2026-05-20

Attached is a transcript of part of a conversation between myself and Claude Sonnet 4.6 (with adaptive thinking enabled) in which we discuss a design flaw in the latest iteration of our Stateful Agent Design, available in my `ai-skills` GitHub repo at `docs/stateful-agent-design/stateful-agent-design.md` (with some chapters in files in the same repo folder having names of the form `stateful-agent-design-chapterN.md`, though to reduce context bloat you should defer reading those external chapters until necessary).

The design review that drove that discussion is also in that repo at `docs/stateful-agent-design/design-review.md`. Please read the attached discussion, the `design-review.md`​, and just the main `stateful-agent-design.md` document.

In the attached discussion, after some missteps, Sonnet and I converged on what looks like a workable design to address the flaw. Before we modify the existing design document, I'd like you to review the attached discussion for flaws, inconsistencies, and omissions. Write your analysis to a new file in my `ai-skills` repo at `docs/stateful-agent-design/memory-aware-tools-analysis.md` and create a PR for me.
