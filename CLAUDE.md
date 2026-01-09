# AI Skills Project

A collection of freely-distributed AI skills. Skills in this repo must conform to the skills specification at https://agentskills.io/specification — read that page for full details.

## Project Structure

- Each skill has a corresponding directory (e.g., `bluesky/`) containing source files
- Each skill is packaged as a `.skill` file (ZIP archive) with matching name (e.g., `bluesky.skill`)
  - Packaging is as simple as executing command`zip -r SKILLDIR.skill SKILLDIR` from the root of this repo, where SKILLDIR is the name of the skill's source directory
- A skill directory contains the following required file:
  - `SKILL.md` - Metadata and documentation in frontmatter + markdown
- A skill directory can contain the following optional directories:
  - `scripts/` - Contains executable scripts (typically Python with PEP 723 inline metadata)
  - `references/` - Contains additional documentation (in markdown format) that agents can read when needed
  - `assets/` - Contains static resources, such as templates (document templates, configuration templates), images (diagrams, examples), data files (lookup tables, schemas)
  - No other directories should appear
  - The `assets/` directory is a good place to put files that don't have a better location

## Skill Design Guidelines

When creating new skills for this repository, follow these principles:

### 1. Zero-Configuration Philosophy

**Avoid requiring user authentication or API credentials whenever possible.**

- Freely-distributed skills should work out-of-the-box without friction
- Don't require users to create accounts, obtain API keys, or configure credentials
- Prefer web scraping, public APIs without auth, or other zero-config approaches
- Only require authentication when absolutely necessary for the functionality

**Rationale**: Creating barriers to entry (account registration, API keys) reduces accessibility and adoption. Users should be able to download a skill and use it immediately.

### 2. Technical Standards

**Python Scripts**:
- Use PEP 723 inline metadata for dependency declarations
- Make scripts executable (`chmod +x`)
- Use `uv run` as the execution method (no manual pip installs)
- Include comprehensive docstrings and help text

**Documentation**:
- Write detailed `SKILL.md` files with:
  - Frontmatter with `name` and `description` fields
  - Clear prerequisites and requirements
  - Usage examples for common scenarios
  - Troubleshooting section
- Use clear, concise language
- Refer to "the user" rather than "you" in documentation

**Packaging**:
- Create `.skill` files as ZIP archives: `cd skillname && zip -r ../skillname.skill .`
- Verify contents with `unzip -l skillname.skill`
- Include both the directory and `.skill` file in the repository

### 3. Error Handling and User Experience

- Implement robust error handling with clear, actionable error messages
- Use retry logic with exponential backoff for network requests
- Provide both human-readable and JSON output formats when appropriate
- Include progress indicators for long-running operations
- Validate input and provide helpful format examples

### 4. Network Access

- Document required network domains clearly in `SKILL.md`
- Note that some AI agents (like Claude) may require domain whitelisting
- Implement reasonable timeouts (e.g., 30 seconds)
- Handle network failures gracefully

### 5. Demonstration Data

When creating skills that require external APIs or network access:
- Include demonstration/fallback data to show expected formats
- Clearly label demo data with notes explaining it's for demonstration
- Allow the skill to function (at least partially) for testing purposes

## Common Patterns

### Python Script Template with PEP 723

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.31.0",
# ]
# ///
"""
Script Description
==================
Brief description of what this script does.

Usage:
    uv run scripts/script.py [arguments]
"""

import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description='...')
    # Add arguments
    args = parser.parse_args()

    # Implementation

if __name__ == '__main__':
    main()
```

### SKILL.md Template

```markdown
---
name: skill-name
description: Brief description triggering when the user wants to... (Use this skill when...)
---

# Skill Name

Overview paragraph.

## Prerequisites

**Tool Dependencies**:
- `uv` - Required for running scripts

**Network Access** (if applicable):
- List required domains

## Available Scripts

### Script Name (`scripts/script.py`)

Description and usage examples.

## Common Use Cases

Examples of when to use this skill.

## Troubleshooting

Common issues and solutions.
```

## Repository Conventions

- Commit messages should be descriptive and explain the "why"
- Reference agentskills.io for the official specification
- Update README.md when adding new skills
- Test skills before committing to ensure they work as documented
- Use clear, professional language in all documentation

## For AI Assistants

When working on this repository:

1. **Creating New Skills**: Follow the design guidelines above, especially the zero-configuration principle
2. **Packaging**: Always create both the directory and `.skill` file
3. **Documentation**: Write comprehensive SKILL.md files that explain usage clearly
4. **Testing**: Verify scripts run correctly with `uv run`
5. **Consistency**: Follow patterns established by existing skills (bluesky, drawio, transcript-saver)

## Resources

- Official specification: [agentskills.io](https://agentskills.io)
- uv documentation: [docs.astral.sh/uv](https://docs.astral.sh/uv/)
- PEP 723 (inline script metadata): [peps.python.org/pep-0723](https://peps.python.org/pep-0723/)
