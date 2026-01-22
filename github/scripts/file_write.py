#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub File Writer
==================
Create or update files in a GitHub repository.

This script uses the GitHub Contents API to:
- Create new files with a commit
- Update existing files (requires the file's current SHA)
- Create files on specific branches

Usage:
    uv run scripts/file_write.py owner/repo --path docs/README.md --content "..." --message "Add docs"
    uv run scripts/file_write.py owner/repo --path config.json --from-file local.json --message "Update config"
    uv run scripts/file_write.py owner/repo --path README.md --content "..." --sha abc123 --message "Update"

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import base64
import json
import os
import sys

import requests


# GitHub API base URL
API_BASE = "https://api.github.com"


def get_token():
    """
    Retrieve GitHub token from environment variable.
    
    Returns the token if set, exits with error if missing.
    """
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        print("Create a token at: https://github.com/settings/tokens", file=sys.stderr)
        sys.exit(1)
    
    return token


def get_headers(token: str) -> dict:
    """
    Build HTTP headers for GitHub API requests.
    
    Args:
        token: GitHub Personal Access Token
        
    Returns:
        Dictionary of headers including authorization
    """
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "github-skill-script",
    }


def parse_repo(repo_string: str) -> tuple:
    """
    Parse owner/repo string into components.
    
    Args:
        repo_string: Repository in "owner/repo" format
        
    Returns:
        Tuple of (owner, repo)
    """
    parts = repo_string.split("/")
    if len(parts) != 2:
        print(f"Error: Invalid repository format '{repo_string}'", file=sys.stderr)
        print("Expected format: owner/repo (e.g., octocat/hello-world)", file=sys.stderr)
        sys.exit(1)
    
    return parts[0], parts[1]


def create_or_update_file(token: str, owner: str, repo: str,
                          path: str, content: str, message: str,
                          sha: str = None, branch: str = None) -> dict:
    """
    Create or update a file in a GitHub repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        path: Path for the file in the repository
        content: File content as a string
        message: Commit message
        sha: SHA of file being replaced (required for updates)
        branch: Branch to commit to (default: repo's default branch)
        
    Returns:
        Dictionary with commit and content info from API response
    """
    headers = get_headers(token)
    
    # Build URL - path should not have leading slash
    path = path.lstrip("/")
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    
    # Encode content as base64
    content_bytes = content.encode("utf-8")
    content_b64 = base64.b64encode(content_bytes).decode("utf-8")
    
    # Build request body
    body = {
        "message": message,
        "content": content_b64,
    }
    
    # Add optional parameters
    if sha:
        body["sha"] = sha
    if branch:
        body["branch"] = branch
    
    # Make the API request
    response = requests.put(url, headers=headers, json=body)
    
    # Handle errors
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        if branch:
            print(f"(or branch '{branch}' does not exist)", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 409:
        # SHA mismatch - file was modified
        print("Error: File has been modified since you read it (SHA mismatch)", file=sys.stderr)
        print("Get the current SHA with: uv run scripts/repo_contents.py --json --path <path>", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 422:
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        errors = error_data.get("errors", [])
        print(f"Error: {error_msg}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        if "sha" in str(errors).lower() or "sha" in error_msg.lower():
            print("\nHint: You may need to provide --sha for an existing file", file=sys.stderr)
        sys.exit(1)
    elif response.status_code not in (200, 201):
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_result_for_display(result: dict, path: str) -> str:
    """
    Format the API result for human-readable display.
    
    Args:
        result: API response dictionary
        path: File path that was created/updated
        
    Returns:
        Formatted string with commit info
    """
    lines = []
    
    commit = result.get("commit", {})
    content = result.get("content", {})
    
    # Determine if this was a create or update
    # (201 status = create, 200 = update, but we only have the response data here)
    action = "Created" if commit else "Updated"
    
    lines.append(f"✅ {action}: {path}")
    lines.append("")
    
    # Commit info
    if commit:
        sha = commit.get("sha", "")[:8]
        message = commit.get("message", "")
        author = commit.get("author", {}).get("name", "Unknown")
        date = commit.get("author", {}).get("date", "")
        
        lines.append(f"📝 Commit: {sha}")
        lines.append(f"   Message: {message}")
        lines.append(f"   Author: {author}")
        if date:
            lines.append(f"   Date: {date}")
    
    # Content info
    if content:
        new_sha = content.get("sha", "")[:8]
        size = content.get("size", 0)
        html_url = content.get("html_url", "")
        
        lines.append("")
        lines.append(f"📄 File SHA: {new_sha}")
        lines.append(f"   Size: {size:,} bytes")
        if html_url:
            lines.append(f"   View: {html_url}")
    
    return "\n".join(lines)


def main():
    """
    Main entry point for the file writer.
    """
    parser = argparse.ArgumentParser(
        description="Create or update a file in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new file
  uv run scripts/file_write.py owner/repo \\
      --path docs/new-file.md \\
      --content "# New Document\\n\\nContent here." \\
      --message "Add new document"

  # Update an existing file (SHA required)
  uv run scripts/file_write.py owner/repo \\
      --path README.md \\
      --content "# Updated README" \\
      --message "Update README" \\
      --sha abc123def456...

  # Create file from local file
  uv run scripts/file_write.py owner/repo \\
      --path remote/path.py \\
      --from-file local/path.py \\
      --message "Upload script"

  # Create on specific branch
  uv run scripts/file_write.py owner/repo \\
      --path config.json \\
      --content '{"key": "value"}' \\
      --message "Add config" \\
      --branch develop
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Required: path
    parser.add_argument(
        "--path", "-p",
        required=True,
        help="Path for the file in the repository"
    )
    
    # Content (one of these required)
    content_group = parser.add_mutually_exclusive_group(required=True)
    content_group.add_argument(
        "--content", "-c",
        help="File content as a string"
    )
    content_group.add_argument(
        "--from-file", "-f",
        help="Read content from this local file"
    )
    
    # Required: commit message
    parser.add_argument(
        "--message", "-m",
        required=True,
        help="Commit message"
    )
    
    # Optional: SHA (required for updates)
    parser.add_argument(
        "--sha",
        help="SHA of file being replaced (required when updating existing file)"
    )
    
    # Optional: branch
    parser.add_argument(
        "--branch", "-b",
        help="Branch to commit to (default: repo's default branch)"
    )
    
    # Output format
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output commit details as JSON"
    )
    
    args = parser.parse_args()
    
    # Get content from file if specified
    if args.from_file:
        try:
            with open(args.from_file, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"Error: Local file not found: {args.from_file}", file=sys.stderr)
            sys.exit(1)
        except IOError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        content = args.content
    
    # Parse repository
    owner, repo = parse_repo(args.repo)
    
    # Get token and create/update file
    token = get_token()
    result = create_or_update_file(
        token, owner, repo,
        path=args.path,
        content=content,
        message=args.message,
        sha=args.sha,
        branch=args.branch,
    )
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result_for_display(result, args.path))


if __name__ == "__main__":
    main()
