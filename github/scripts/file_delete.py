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
import sys

# Import shared utilities from the common module
from github_common import (
    API_BASE,
    get_token,
    get_headers,
    parse_repo,
    make_request_with_retry,
)


# =============================================================================
# API Functions
# =============================================================================

def delete_file(
    token: str,
    owner: str,
    repo: str,
    path: str,
    sha: str,
    message: str,
    branch: str = None
) -> dict:
    """
    Delete a file from a GitHub repository.
    
    The SHA must match the current file's SHA to prevent accidental
    deletion of files that have been modified since they were read.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        path: Path to the file to delete
        sha: SHA of the file to delete (required)
        message: Commit message
        branch: Branch to delete from (default: repo's default branch)
        
    Returns:
        API response dictionary with commit info
    """
    headers = get_headers(token)
    
    # Build URL - path should not have leading slash
    path = path.lstrip("/")
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    
    # Build request body
    body = {
        "message": message,
        "sha": sha,  # SHA is required for deletion
    }
    
    # Add optional branch parameter
    if branch:
        body["branch"] = branch
    
    # Make the DELETE request
    response = make_request_with_retry('delete', url, headers, json=body)
    
    # Handle specific error cases
    if response.status_code == 404:
        print(f"Error: File '{path}' not found in {owner}/{repo}", file=sys.stderr)
        if branch:
            print(f"(on branch '{branch}')", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 409:
        # SHA mismatch - file was modified
        print("Error: File has been modified since you read it (SHA mismatch)",
              file=sys.stderr)
        print("Get the current SHA with: uv run scripts/repo_contents.py --json --path <path>",
              file=sys.stderr)
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


# =============================================================================
# Display Formatting Functions
# =============================================================================

def format_result_for_display(result: dict, path: str) -> str:
    """
    Format the deletion result for human-readable display.
    
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
        
        lines.append(f"📝 Commit: {sha}")
        lines.append(f"   Message: {message}")
        lines.append(f"   Author: {author}")
        if date:
            lines.append(f"   Date: {date}")
    
    return "\n".join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the file deleter.
    
    Parses command-line arguments and deletes the specified file.
    """
    parser = argparse.ArgumentParser(
        description="Delete a file from a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete a file (SHA required - get it from repo_contents.py --json)
  uv run scripts/file_delete.py owner/repo \\
      --path docs/old-file.md \\
      --sha abc123... \\
      --message "Remove old document"

  # Delete from specific branch
  uv run scripts/file_delete.py owner/repo \\
      --path temp.txt \\
      --sha abc123... \\
      --message "Clean up temp file" \\
      --branch develop

  # Get the SHA first, then delete
  SHA=$(uv run scripts/repo_contents.py owner/repo --path file.txt --json | jq -r '.sha')
  uv run scripts/file_delete.py owner/repo --path file.txt --sha $SHA --message "Remove file"
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Required: file path
    parser.add_argument(
        "--path", "-p",
        required=True,
        help="Path to the file to delete"
    )
    
    # Required: file SHA
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
    
    # Optional: target branch
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
