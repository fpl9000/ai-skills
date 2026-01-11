---
name: load-skill
description: Load, activate, and optionally install an AI skill from a .skill file. Use this skill when the user wants to load, activate, or use a skill file. Invoke as `/load-skill PATH` where PATH is the path to a .skill file.
---

# Load Skill

This skill loads and activates another skill from a `.skill` file.

## Usage

```
/load-skill PATH
```

Where `PATH` is the path to a `.skill` file (a ZIP archive containing skill content).

## How to Process This Skill

When this skill is invoked, you (the AI agent) should:

1. **Parse the argument**: Extract the skill file path from the arguments provided.  If no path
   is provided, ask the user for the path to the skill file.

2. **Validate the file**: Verify the file exists and has a `.skill` extension.

3. **Extract the skill**: Use `unzip` to extract the skill to a temporary directory.  Use a
   command like:
   ```bash
   unzip -o "SKILLFILE" -d "TEMPDIR"
   ```

4. **Locate SKILL.md**: Find the `SKILL.md` file in the extracted contents.  It may be at the
   root level or inside a subdirectory (depending on how the skill was packaged).

5. **Read the skill**: Read the entire `SKILL.md` file to understand the skill's capabilities
   and instructions.

6. **Install the skill** (optional but recommended): If your AI system has a designated skills
   folder where skills can be permanently installed, copy the extracted skill folder there.
   This makes the skill available in future sessions without needing to reload it.  Ask the
   user if they want the skill installed permanently.

7. **Activate the skill**: Follow the instructions in the loaded skill's `SKILL.md` as if it
   had been invoked directly.  The loaded skill is now active for the remainder of the
   conversation.

8. **Clean up**: After activating the skill, you may delete the temporary extraction directory.

## Example

```
User: /load-skill ./my-custom.skill
Agent: [Extracts skill, reads SKILL.md, follows instructions]
```

## Notes

- The `.skill` file format is a ZIP archive as defined by the Agent Skills specification at
  https://agentskills.io.

- If the skill file contains scripts in a `scripts/` directory, those scripts become available
  for use per the loaded skill's instructions.

- If the skill file contains references in a `references/` directory, read those files as
  needed for additional context.

- If the skill requires environment variables or prerequisites, inform the user before
  proceeding.
