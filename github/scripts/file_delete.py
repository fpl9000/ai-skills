#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub File Deleter
===================
Delete a file from a GitHub repository.

This script uses the GitHub Contents API to delete files with a commit.
The file's SHA is required to prevent accidental deletions of modified files.

Usage:
    uv run scripts/file_delete.py owner/repo --path old-file.md --sha abc123 --message "Remove old file"

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
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


def delete_file(token: str, owner: str, repo: str,
                path: str, sha: str, message: str,
                branch: str = None) -> dict:
    """
    Delete a file from a GitHub repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        path: Path to the file to delete
        sha: SHA of the file to delete
        message: Commit message
        branch: Branch to delete from (default: repo's default branch)
        
    Returns:
        Dictionary with commit info from API response
    """
    headers = get_headers(token)
    
    # Build URL - path should not have leading slash
    path = path.lstrip("/")
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    
    # Build request body
    body = {
        "message": message,
        "sha": sha,
    }
    
    # Add optional branch parameter
    if branch:
        body["branch"] = branch
    
    # Make the API request (DELETE with JSON body)
    response = requests.delete(url, headers=headers, json=body)
    
    # Handle errors
    if response.status_code == 404:
        print(f"Error: File '{path}' not found in {owner}/{repo}", file=sys.stderr)
        if branch:
            print(f"(or branch '{branch}' does not exist)", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 409:
        # SHA mismatch
        print("Error: File SHA does not match (file was modified)", file=sys.stderr)
        print("Get the current SHA with: uv run scripts/repo_contents.py --json --path <path>", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 422:
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        print(f"Error: {error_msg}", file=sys.stderr)
        sys.exit(1)
    elif response.status_code != 200:
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
        path: File path that was deleted
        
    Returns:
        Formatted string with commit info
    """
    lines = []
    
    commit = result.get("commit", {})
    
    lines.append(f"🗑️  Deleted: {path}")
    lines.append("")
    
    # Commit info
    if commit:
        sha = commit.get("sha", "")[:8]
        message = commit.get("message", "")
        author = commit.get("author", {}).get("name", "Unknown")
        date = commit.get("author", {}).get("date", "")
        html_url = commit.get("html_url", "")
        
        lines.append(f"📝 Commit: {sha}")
        lines.append(f"   Message: {message}")
        lines.append(f"   Author: {author}")
        if date:
            lines.append(f"   Date: {date}")
        if html_url:
            lines.append(f"   View: {html_url}")
    
    return "\n".join(lines)


def main():
    """
    Main entry point for the file deleter.
    """
    parser = argparse.ArgumentParser(
        description="Delete a file from a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete a file (SHA required)
  uv run scripts/file_delete.py owner/repo \\
      --path docs/old-file.md \\
      --sha abc123def456... \\
      --message "Remove old document"

  # Delete from specific branch
  uv run scripts/file_delete.py owner/repo \\
      --path temp.txt \\
      --sha abc123def456... \\
      --message "Clean up temp file" \\
      --branch develop

To get a file's SHA:
  uv run scripts/repo_contents.py owner/repo --path <file> --json | jq -r '.sha'
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
        help="Path to the file to delete"
    )
    
    # Required: SHA
    parser.add_argument(
        "--sha",
        required=True,
        help="SHA of the file to delete (get from repo_contents.py --json)"
    )
    
    # Required: commit message
    parser.add_argument(
        "--message", "-m",
        required=True,
        help="Commit message"
    )
    
    # Optional: branch
    parser.add_argument(
        "--branch", "-b",
        help="Branch to delete from (default: repo's default branch)"
    )
    
    # Output format
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output commit details as JSON"
    )
    
    args = parser.parse_args()
    
    # Parse repository
    owner, repo = parse_repo(args.repo)
    
    # Get token and delete file
    token = get_token()
    result = delete_file(
        token, owner, repo,
        path=args.path,
        sha=args.sha,
        message=args.message,
        branch=args.branch,
    )
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result_for_display(result, args.path))


if __name__ == "__main__":
    main()
