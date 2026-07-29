---
name: github
description: Manage GitHub pull requests, issues, and repository listings via the GitHub REST API. Use this skill for operations that plain `git` cannot perform — opening, inspecting, and merging pull requests, and creating, listing, and updating issues — and for enumerating a user's or organization's repositories. For anything involving repository *content* (reading files, writing files, branches, commit history), use `git` directly instead. All scripts use PEP 723 inline metadata for dependencies and run via `uv run`. Requires GITHUB_TOKEN environment variable (a Personal Access Token with appropriate scopes).
---

# Skill Overview

This skill provides access to GitHub's collaboration layer — pull requests and issues — via a set of Python scripts that wrap the GitHub REST API. It also provides repository enumeration, which has no `git` equivalent.

## Scope: Use `git` for Content, This Skill for Everything Else

Git is a transport for the objects inside a repository. It knows nothing about GitHub's collaboration layer, which is proprietary metadata layered on top of the object store. That distinction determines which tool to reach for.

**Use `git` directly** for reading files, writing files, creating and deleting branches, and inspecting commit history. Clone over HTTPS, make changes locally, commit, and push. This is strictly better than driving the REST API for the same purposes: `git` produces atomic multi-file commits, preserves real history and correct merge semantics, requires no per-file blob-SHA round trips, and does not need content base64-encoded into JSON payloads.

**Use this skill** for the operations `git` structurally cannot perform, because they do not exist in the git object model at all:

- Pull requests — opening, listing, inspecting, and merging them
- Issues — creating, listing, and updating them
- Repository enumeration — listing the repositories belonging to a user or organization

Earlier versions of this skill also included scripts for file, branch, and commit operations. Those were removed because they duplicated `git` less capably. If an agent using this skill has no working `git` — for example, in a sandbox whose network egress permits `api.github.com` but not `github.com` — that agent must fall back to the REST API directly rather than to scripts that no longer exist.

## Prerequisites

**Tool Dependency**:
- `uv` - The scripts in this skill require the [uv](https://docs.astral.sh/uv/) package manager/runner. Most cloud-based AI agents have `uv` pre-installed (or they can install it). Local agents should install it via `curl -LsSf https://astral.sh/uv/install.sh | sh` or see the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/).

**Environment Variables** (must be set before running any script):
- `GITHUB_TOKEN` - A GitHub Personal Access Token (classic or fine-grained) with appropriate scopes

**Recommended Token Scopes** (for classic PAT):
- `repo` - Full control of private repositories (or `public_repo` for public only)
- `read:org` - Read organization membership (optional, for org repos)

**Important**: Use a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) when possible for better security. Configure only the repositories and permissions you need.

## Network Access

**Important**: The scripts in this skill require network access to the following domain:

- `api.github.com`

If the AI agent has network restrictions, the user may need to whitelist this domain in the agent's settings for this skill to function. Note that `api.github.com` is a separate hostname from `github.com`, which is the host `git` clones and pushes to; an allowlist that permits one does not necessarily permit the other.

## Common Code Used by All Scripts

This skill uses a shared common module (`github_common.py`) to centralize authentication, token management, HTTP header construction, repository string parsing, error handling, and retry logic with exponential backoff.

All scripts import from `github_common.py`, which makes maintenance easier and ensures consistent behavior across all operations.

## API Versioning

This skill uses explicit GitHub API versioning for long-term stability:
- API Version: `2022-11-28`
- Header: `X-GitHub-Api-Version: 2022-11-28`

This ensures consistent behavior even if GitHub releases new API versions with breaking changes.

## Available Scripts

All scripts include PEP 723 inline metadata declaring their dependencies. Just run with `uv run` — no manual dependency installation needed.

---

## Repository Operations

### List Repositories (`scripts/repo_list.py`)

Enumerates repositories belonging to a user or organization. There is no `git` equivalent: `git` can clone a repository whose URL is already known, but it cannot ask GitHub what repositories exist.

```bash
uv run scripts/repo_list.py                          # List the token owner's repos
uv run scripts/repo_list.py --user octocat           # List a user's repos
uv run scripts/repo_list.py --org github             # List an organization's repos
uv run scripts/repo_list.py --type public --sort updated --json
```

| Argument | Description |
|----------|-------------|
| `--user` | List repos for this user |
| `--org` | List repos for this organization |
| `--type` | Filter: all, public, private, forks, sources, member |
| `--sort` | Sort by: created, updated, pushed, full_name |
| `--per-page` | Results per page (max 100, default: 30) |
| `--page` | Page number (default: 1) |
| `--json`, `-j` | Output as JSON |

---

## Issue Operations

### List Issues (`scripts/issue_list.py`)

```bash
uv run scripts/issue_list.py owner/repo
uv run scripts/issue_list.py owner/repo --state all
uv run scripts/issue_list.py owner/repo --labels "bug,urgent"
uv run scripts/issue_list.py owner/repo --assignee octocat --json
```

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--state` | Filter: open, closed, all (default: open) |
| `--labels` | Comma-separated list of label names |
| `--assignee` | Filter by assignee username |
| `--sort` | Sort by: created, updated, comments |
| `--direction` | Sort direction: asc, desc |
| `--per-page` | Results per page (max 100) |
| `--page` | Page number |
| `--json`, `-j` | Output as JSON |

---

### Create Issue (`scripts/issue_create.py`)

```bash
uv run scripts/issue_create.py owner/repo --title "Bug report" --body "Description..."
uv run scripts/issue_create.py owner/repo --title "Feature" --labels "enhancement"
uv run scripts/issue_create.py owner/repo --title "Task" --assignees "user1,user2"
```

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--title`, `-t` | Issue title (required) |
| `--body`, `-b` | Issue body/description |
| `--labels` | Comma-separated list of label names |
| `--assignees` | Comma-separated list of usernames |
| `--milestone` | Milestone number |
| `--json`, `-j` | Output as JSON |

---

### Update Issue (`scripts/issue_update.py`)

```bash
uv run scripts/issue_update.py owner/repo 123 --title "New title"
uv run scripts/issue_update.py owner/repo 123 --state closed
uv run scripts/issue_update.py owner/repo 123 --state closed --reason not_planned
uv run scripts/issue_update.py owner/repo 123 --labels "bug,urgent"
uv run scripts/issue_update.py owner/repo 123 --assignees "user1,user2"
```

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `issue_number` | Issue number to update (required) |
| `--title`, `-t` | New title |
| `--body`, `-b` | New body/description |
| `--state`, `-s` | New state: open, closed |
| `--reason` | Close reason: completed, not_planned |
| `--labels` | Comma-separated labels (replaces existing) |
| `--assignees` | Comma-separated usernames (replaces existing) |
| `--milestone` | Milestone number (0 to clear) |
| `--json`, `-j` | Output as JSON |

---

## Pull Request Operations

### List Pull Requests (`scripts/pr_list.py`)

```bash
uv run scripts/pr_list.py owner/repo
uv run scripts/pr_list.py owner/repo --state all
uv run scripts/pr_list.py owner/repo --base main
uv run scripts/pr_list.py owner/repo --sort updated --json
```

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--state` | Filter: open, closed, all (default: open) |
| `--base` | Filter by base branch |
| `--head` | Filter by head branch |
| `--sort` | Sort by: created, updated, popularity, long-running |
| `--direction` | Sort direction: asc, desc |
| `--per-page` | Results per page (max 100) |
| `--page` | Page number |
| `--json`, `-j` | Output as JSON |

---

### Create Pull Request (`scripts/pr_create.py`)

The head branch must already exist on the remote before a pull request can reference it. Push it with `git push -u origin <branch>` first.

```bash
uv run scripts/pr_create.py owner/repo --title "Add feature" --head feature-branch
uv run scripts/pr_create.py owner/repo --title "Fix bug" --head fix-123 --base develop
uv run scripts/pr_create.py owner/repo --title "WIP" --head wip-branch --draft
```

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--title`, `-t` | PR title (required) |
| `--head`, `-h` | Branch containing changes (required) |
| `--base`, `-b` | Branch to merge into (default: default branch) |
| `--body` | PR description |
| `--draft`, `-d` | Create as draft PR |
| `--json`, `-j` | Output as JSON |

---

### Get Pull Request Details (`scripts/pr_get.py`)

```bash
uv run scripts/pr_get.py owner/repo 123
uv run scripts/pr_get.py owner/repo 123 --json
```

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `pr_number` | Pull request number (required) |
| `--json`, `-j` | Output as JSON |

---

### Merge Pull Request (`scripts/pr_merge.py`)

```bash
uv run scripts/pr_merge.py owner/repo 123
uv run scripts/pr_merge.py owner/repo 123 --method squash
uv run scripts/pr_merge.py owner/repo 123 --method rebase
uv run scripts/pr_merge.py owner/repo 123 --method squash --title "Feature (#123)"
```

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `pr_number` | Pull request number (required) |
| `--method`, `-m` | Merge method: merge, squash, rebase |
| `--title`, `-t` | Custom commit title |
| `--message` | Custom commit message body |
| `--sha` | Expected head SHA (for safety) |
| `--json`, `-j` | Output as JSON |

---

## Common Patterns

### Setting Credentials

```bash
# Set for current session
export GITHUB_TOKEN="ghp_xxxxxxxxxxxx"

# Or inline with command
GITHUB_TOKEN="ghp_xxx" uv run scripts/repo_list.py
```

### Branch, Commit, and PR (Full Workflow)

The content half of this workflow is plain `git`; only the final two steps need the API. Note that the token is embedded in the clone URL because HTTPS-with-PAT is the transport GitHub supports for scripted access.

```bash
# 1. Clone and branch — git, not the API
git clone "https://USERNAME:${GITHUB_TOKEN}@github.com/owner/repo.git"
cd repo
git checkout -b feature/my-feature

# 2. Make changes with ordinary file edits, then commit them atomically
#    (one commit can touch any number of files; the REST API cannot do this)
git add -A
git commit -m "Add my feature"

# 3. Push the branch so the PR has a head to reference
git push -u origin feature/my-feature

# 4. Open the PR — this is the part git cannot do
uv run scripts/pr_create.py owner/repo \
    --title "Add my feature" \
    --head feature/my-feature \
    --body "This PR adds..."

# 5. Merge it once approved
uv run scripts/pr_merge.py owner/repo 123 --method squash

# 6. Clean up the branch — git again
git push origin --delete feature/my-feature
```

### JSON Output for Processing

All scripts support `--json` for machine-readable output:

```bash
# List repos and filter with jq
uv run scripts/repo_list.py --json | jq '.[] | select(.language == "Python")'

# Get all open PR numbers
uv run scripts/pr_list.py owner/repo --json | jq '.[].number'

# Count open issues
uv run scripts/issue_list.py owner/repo --json | jq 'length'
```

## Error Handling

Scripts exit with non-zero status on errors. Common issues:

- **401 Unauthorized**: Check that `GITHUB_TOKEN` is set and valid
- **403 Forbidden**: Token lacks required scopes, or rate limit exceeded
- **404 Not Found**: Repository, issue, or pull request doesn't exist (or the token lacks access)
- **405 Method Not Allowed**: The pull request is not in a mergeable state
- **409 Conflict**: Head SHA mismatch on merge (the branch moved since it was read), or a merge conflict
- **422 Validation Failed**: Invalid input — for `pr_create.py`, the most common cause is a head branch that was never pushed to the remote

## Rate Limits

The GitHub API has rate limits:
- Authenticated requests: 5,000 per hour
- Search API: 30 per minute

The skill includes automatic retry logic with exponential backoff for rate limit errors.

Current limits can be checked as follows:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
```
