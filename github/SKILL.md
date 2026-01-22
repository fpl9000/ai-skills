---
name: github
description: Access GitHub repositories via the GitHub REST API. Use this skill when the user wants to interact with GitHub including reading files, creating/updating files, listing repos, managing branches, viewing commits, or working with issues and pull requests. All scripts use PEP 723 inline metadata for dependencies and run via `uv run`. Requires GITHUB_TOKEN environment variable (a Personal Access Token with appropriate scopes).
---

# Skill Overview

This skill provides access to GitHub repositories via a set of Python scripts that wrap the GitHub REST API.

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

If you (the AI agent) have network restrictions, the user may need to whitelist this domain in the agent's settings for this skill to function.

## Available Scripts

All scripts include PEP 723 inline metadata declaring their dependencies. Just run with `uv run` — no manual dependency installation needed.

---

### List Repositories (`scripts/repo_list.py`)

List repositories for a user or organization.

```bash
# List your own repos (authenticated user)
uv run scripts/repo_list.py

# List repos for a specific user
uv run scripts/repo_list.py --user octocat

# List repos for an organization
uv run scripts/repo_list.py --org github

# Filter by type and sort
uv run scripts/repo_list.py --type public --sort updated

# JSON output
uv run scripts/repo_list.py --json

# Pagination
uv run scripts/repo_list.py --per-page 50 --page 2
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `--user` | List repos for this user |
| `--org` | List repos for this organization |
| `--type` | Filter by type: all, public, private, forks, sources, member (default: all) |
| `--sort` | Sort by: created, updated, pushed, full_name (default: updated) |
| `--per-page` | Results per page (max 100, default: 30) |
| `--page` | Page number (default: 1) |
| `--json`, `-j` | Output as JSON |

---

### Get Repository Contents (`scripts/repo_contents.py`)

Get file or directory contents from a repository.

```bash
# Get root directory listing
uv run scripts/repo_contents.py owner/repo

# Get a specific file
uv run scripts/repo_contents.py owner/repo --path README.md

# Get a directory listing
uv run scripts/repo_contents.py owner/repo --path src/

# Get contents from a specific branch
uv run scripts/repo_contents.py owner/repo --path config.json --ref develop

# JSON output (includes metadata like SHA, size, etc.)
uv run scripts/repo_contents.py owner/repo --path README.md --json
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--path`, `-p` | Path to file or directory (default: root) |
| `--ref`, `-r` | Git ref (branch, tag, or commit SHA) |
| `--json`, `-j` | Output as JSON with full metadata |

---

### Get Repository Tree (`scripts/repo_tree.py`)

Get the full file tree of a repository (recursive listing).

```bash
# Get full tree of default branch
uv run scripts/repo_tree.py owner/repo

# Get tree from specific branch
uv run scripts/repo_tree.py owner/repo --ref develop

# Filter to specific directory
uv run scripts/repo_tree.py owner/repo --path src/

# JSON output
uv run scripts/repo_tree.py owner/repo --json
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--ref`, `-r` | Git ref (branch, tag, or commit SHA) |
| `--path`, `-p` | Filter to paths starting with this prefix |
| `--json`, `-j` | Output as JSON |

---

### Create or Update File (`scripts/file_write.py`)

Create a new file or update an existing file in a repository.

```bash
# Create a new file
uv run scripts/file_write.py owner/repo \
    --path docs/new-file.md \
    --content "# New Document\n\nContent here." \
    --message "Add new document"

# Update an existing file (SHA required - get it from repo_contents.py --json)
uv run scripts/file_write.py owner/repo \
    --path README.md \
    --content "# Updated README\n\nNew content." \
    --message "Update README" \
    --sha abc123...

# Create file on a specific branch
uv run scripts/file_write.py owner/repo \
    --path config.json \
    --content '{"key": "value"}' \
    --message "Add config" \
    --branch develop

# Read content from a local file
uv run scripts/file_write.py owner/repo \
    --path remote/path.py \
    --from-file local/path.py \
    --message "Upload script"
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--path`, `-p` | Path for the file in the repo (required) |
| `--content`, `-c` | File content as string |
| `--from-file`, `-f` | Read content from this local file |
| `--message`, `-m` | Commit message (required) |
| `--sha` | SHA of file being replaced (required for updates) |
| `--branch`, `-b` | Branch to commit to (default: repo's default branch) |
| `--json`, `-j` | Output commit details as JSON |

**Note**: Either `--content` or `--from-file` must be provided.

---

### Delete File (`scripts/file_delete.py`)

Delete a file from a repository.

```bash
# Delete a file (SHA required - get it from repo_contents.py --json)
uv run scripts/file_delete.py owner/repo \
    --path docs/old-file.md \
    --sha abc123... \
    --message "Remove old document"

# Delete from specific branch
uv run scripts/file_delete.py owner/repo \
    --path temp.txt \
    --sha abc123... \
    --message "Clean up temp file" \
    --branch develop
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--path`, `-p` | Path to the file to delete (required) |
| `--sha` | SHA of the file to delete (required) |
| `--message`, `-m` | Commit message (required) |
| `--branch`, `-b` | Branch to delete from (default: repo's default branch) |
| `--json`, `-j` | Output commit details as JSON |

---

### List Branches (`scripts/branch_list.py`)

List branches in a repository.

```bash
# List all branches
uv run scripts/branch_list.py owner/repo

# JSON output
uv run scripts/branch_list.py owner/repo --json

# Pagination
uv run scripts/branch_list.py owner/repo --per-page 100
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--per-page` | Results per page (max 100, default: 30) |
| `--page` | Page number (default: 1) |
| `--json`, `-j` | Output as JSON |

---

### Create Branch (`scripts/branch_create.py`)

Create a new branch in a repository.

```bash
# Create branch from default branch
uv run scripts/branch_create.py owner/repo --name feature/new-feature

# Create branch from specific source branch
uv run scripts/branch_create.py owner/repo \
    --name hotfix/bug-123 \
    --from develop

# Create branch from specific commit SHA
uv run scripts/branch_create.py owner/repo \
    --name release/v1.0 \
    --from abc123def456...
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--name`, `-n` | Name for the new branch (required) |
| `--from`, `-f` | Source branch or commit SHA (default: repo's default branch) |
| `--json`, `-j` | Output as JSON |

---

### List Commits (`scripts/commit_list.py`)

List commits in a repository.

```bash
# List recent commits on default branch
uv run scripts/commit_list.py owner/repo

# List commits on specific branch
uv run scripts/commit_list.py owner/repo --branch develop

# List commits for a specific path
uv run scripts/commit_list.py owner/repo --path src/main.py

# List commits by author
uv run scripts/commit_list.py owner/repo --author octocat

# JSON output
uv run scripts/commit_list.py owner/repo --json
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--branch`, `-b` | Branch name (default: repo's default branch) |
| `--path`, `-p` | Only commits containing this file path |
| `--author`, `-a` | Filter by author username or email |
| `--since` | Only commits after this date (ISO 8601 format) |
| `--until` | Only commits before this date (ISO 8601 format) |
| `--per-page` | Results per page (max 100, default: 30) |
| `--page` | Page number (default: 1) |
| `--json`, `-j` | Output as JSON |

---

### Get Commit Details (`scripts/commit_get.py`)

Get details for a specific commit.

```bash
# Get commit by SHA
uv run scripts/commit_get.py owner/repo abc123def456

# JSON output (includes full diff stats)
uv run scripts/commit_get.py owner/repo abc123def456 --json
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `sha` | Commit SHA (required) |
| `--json`, `-j` | Output as JSON |

---

### List Issues (`scripts/issue_list.py`)

List issues in a repository.

```bash
# List open issues
uv run scripts/issue_list.py owner/repo

# List all issues (including closed)
uv run scripts/issue_list.py owner/repo --state all

# Filter by labels
uv run scripts/issue_list.py owner/repo --labels "bug,high-priority"

# Filter by assignee
uv run scripts/issue_list.py owner/repo --assignee octocat

# JSON output
uv run scripts/issue_list.py owner/repo --json
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--state` | Filter by state: open, closed, all (default: open) |
| `--labels` | Comma-separated list of label names |
| `--assignee` | Filter by assignee username |
| `--sort` | Sort by: created, updated, comments (default: created) |
| `--direction` | Sort direction: asc, desc (default: desc) |
| `--per-page` | Results per page (max 100, default: 30) |
| `--page` | Page number (default: 1) |
| `--json`, `-j` | Output as JSON |

---

### Create Issue (`scripts/issue_create.py`)

Create a new issue in a repository.

```bash
# Create simple issue
uv run scripts/issue_create.py owner/repo \
    --title "Bug: Something is broken" \
    --body "Description of the bug..."

# Create issue with labels and assignee
uv run scripts/issue_create.py owner/repo \
    --title "Feature request" \
    --body "Please add this feature" \
    --labels "enhancement,help-wanted" \
    --assignees "octocat,contributor"
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `repo` | Repository in owner/repo format (required) |
| `--title`, `-t` | Issue title (required) |
| `--body`, `-b` | Issue body/description |
| `--labels` | Comma-separated list of label names |
| `--assignees` | Comma-separated list of usernames to assign |
| `--milestone` | Milestone number |
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

### Updating a File (Full Workflow)

To update a file, you need its current SHA. Here's the workflow:

```bash
# 1. Get the current file with its SHA
uv run scripts/repo_contents.py owner/repo --path README.md --json > file_info.json

# 2. Extract the SHA
SHA=$(jq -r '.sha' file_info.json)

# 3. Update the file with the SHA
uv run scripts/file_write.py owner/repo \
    --path README.md \
    --content "New content here" \
    --message "Update README" \
    --sha "$SHA"
```

### JSON Output for Processing

All scripts support `--json` for machine-readable output:

```bash
# List repos and filter with jq
uv run scripts/repo_list.py --json | jq '.[] | select(.language == "Python")'

# Get commit count
uv run scripts/commit_list.py owner/repo --json | jq 'length'
```

## Error Handling

Scripts exit with non-zero status on errors. Common issues:

- **401 Unauthorized**: Check that `GITHUB_TOKEN` is set and valid
- **403 Forbidden**: Token lacks required scopes, or rate limit exceeded
- **404 Not Found**: Repository, file, or branch doesn't exist (or token lacks access)
- **409 Conflict**: SHA mismatch when updating (file was modified since you read it)
- **422 Validation Failed**: Invalid input (check branch name format, file path, etc.)

## Rate Limits

The GitHub API has rate limits:
- Authenticated requests: 5,000 per hour
- Search API: 30 per minute

Check your current limits:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
```
