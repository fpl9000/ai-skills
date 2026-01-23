#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Pull Request Merger
==========================
Merge a pull request in a GitHub repository.

Supports three merge methods:
- merge: Create a merge commit
- squash: Squash all commits into one
- rebase: Rebase commits onto base branch

Usage:
    uv run scripts/pr_merge.py owner/repo 123
    uv run scripts/pr_merge.py owner/repo 123 --method squash
    uv run scripts/pr_merge.py owner/repo 123 --method squash --message "Feature complete"

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import json
import sys

from github_common import (
    API_BASE, get_token, get_headers, parse_repo,
    make_request_with_retry,
)


def merge_pull_request(
    token: str, owner: str, repo: str, pr_number: int,
    merge_method: str = "merge",
    commit_title: str = None,
    commit_message: str = None,
    sha: str = None
) -> dict:
    """
    Merge a pull request.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        pr_number: PR number to merge
        merge_method: 'merge', 'squash', or 'rebase'
        commit_title: Custom commit title (for merge/squash)
        commit_message: Custom commit message (for merge/squash)
        sha: Expected head SHA (optional, for safety)
        
    Returns:
        Merge result dictionary
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/merge"
    
    payload = {
        "merge_method": merge_method,
    }
    if commit_title:
        payload["commit_title"] = commit_title
    if commit_message:
        payload["commit_message"] = commit_message
    if sha:
        payload["sha"] = sha
    
    response = make_request_with_retry('put', url, headers, json=payload)
    
    if response.status_code == 404:
        print(f"Error: Pull request #{pr_number} not found in {owner}/{repo}",
              file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 405:
        error_data = response.json()
        error_msg = error_data.get("message", "Merge not allowed")
        print(f"Error: {error_msg}", file=sys.stderr)
        print("The PR may not be mergeable. Check for:", file=sys.stderr)
        print("  - Unresolved conflicts", file=sys.stderr)
        print("  - Required reviews not completed", file=sys.stderr)
        print("  - Required status checks not passed", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 409:
        error_data = response.json()
        error_msg = error_data.get("message", "Conflict")
        print(f"Error: {error_msg}", file=sys.stderr)
        if "sha" in error_msg.lower():
            print("The PR head has changed. Refresh and try again.", file=sys.stderr)
        sys.exit(1)
    elif response.status_code not in (200, 201):
        try:
            error_msg = response.json().get("message", "Unknown error")
        except ValueError:
            error_msg = response.text or "Unknown error"
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_merge_for_display(result: dict, pr_number: int, method: str) -> str:
    """Format the merge result for display."""
    lines = []
    
    merged = result.get("merged", False)
    sha = result.get("sha", "")[:8]
    message = result.get("message", "")
    
    if merged:
        method_text = {
            "merge": "merged",
            "squash": "squash merged",
            "rebase": "rebased and merged",
        }.get(method, "merged")
        
        lines.append(f"✅ Pull request #{pr_number} {method_text}")
        lines.append("")
        lines.append(f"Merge commit: {sha}")
        if message:
            lines.append(f"Message: {message}")
    else:
        lines.append(f"❌ Failed to merge pull request #{pr_number}")
        if message:
            lines.append(f"Reason: {message}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Merge a pull request",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Merge with default method (merge commit)
  uv run scripts/pr_merge.py owner/repo 123

  # Squash merge
  uv run scripts/pr_merge.py owner/repo 123 --method squash

  # Rebase merge
  uv run scripts/pr_merge.py owner/repo 123 --method rebase

  # Custom commit message (for merge/squash)
  uv run scripts/pr_merge.py owner/repo 123 --method squash \\
      --title "Add new feature (#123)" \\
      --message "This adds the new feature as discussed in #100"

Merge Methods:
  merge   - Create a merge commit (preserves all commits)
  squash  - Combine all commits into one
  rebase  - Rebase commits onto base branch (linear history)
        """
    )
    
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("pr_number", type=int, help="Pull request number")
    parser.add_argument("--method", "-m", default="merge",
                        choices=["merge", "squash", "rebase"],
                        help="Merge method (default: merge)")
    parser.add_argument("--title", "-t", help="Custom commit title")
    parser.add_argument("--message", help="Custom commit message/body")
    parser.add_argument("--sha", help="Expected head SHA (for safety)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    result = merge_pull_request(
        token, owner, repo, args.pr_number,
        merge_method=args.method,
        commit_title=args.title,
        commit_message=args.message,
        sha=args.sha,
    )
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_merge_for_display(result, args.pr_number, args.method))


if __name__ == "__main__":
    main()
