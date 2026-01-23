#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Commit Lister
====================
List commits in a GitHub repository.

This script retrieves commit information including:
- Commit SHA and message
- Author and committer info
- Timestamp
- Stats (additions, deletions)

Usage:
    uv run scripts/commit_list.py owner/repo
    uv run scripts/commit_list.py owner/repo --branch develop
    uv run scripts/commit_list.py owner/repo --path src/main.py
    uv run scripts/commit_list.py owner/repo --json

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import json
import sys
from datetime import datetime

# Import shared utilities from the common module
from github_common import (
    API_BASE,
    get_token,
    get_headers,
    parse_repo,
    make_request_with_retry,
    handle_api_error,
)


def list_commits(
    token: str,
    owner: str,
    repo: str,
    branch: str = None,
    path: str = None,
    author: str = None,
    since: str = None,
    until: str = None,
    per_page: int = 30,
    page: int = 1
) -> list:
    """
    List commits from a GitHub repository.
    
    Retrieves commits with optional filtering by branch, path, author,
    and date range. Results are paginated.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        branch: Branch name (default: repo's default branch)
        path: Filter to commits affecting this path
        author: Filter by author username or email
        since: Only commits after this date (ISO 8601)
        until: Only commits before this date (ISO 8601)
        per_page: Results per page (max 100)
        page: Page number
        
    Returns:
        List of commit dictionaries from the API
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/commits"
    
    # Build query parameters
    params = {
        "per_page": min(per_page, 100),
        "page": page,
    }
    
    # Add optional filters
    if branch:
        params["sha"] = branch
    if path:
        params["path"] = path
    if author:
        params["author"] = author
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    
    response = make_request_with_retry('get', url, headers, params=params)
    handle_api_error(response, f"Commits in {owner}/{repo}")
    return response.json()


def format_commit_for_display(commit: dict) -> str:
    """Format a single commit for human-readable display."""
    lines = []
    sha = commit.get("sha", "")[:8]
    commit_data = commit.get("commit", {})
    message = commit_data.get("message", "").split("\n")[0]
    author = commit_data.get("author", {})
    author_name = author.get("name", "Unknown")
    date_str = author.get("date", "")
    
    date_display = ""
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_display = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            date_display = date_str
    
    if len(message) > 60:
        message = message[:57] + "..."
    
    lines.append(f"📝 {sha}  {message}")
    lines.append(f"   Author: {author_name}  |  {date_display}")
    return "\n".join(lines)


def format_commits_for_display(commits: list) -> str:
    """Format a list of commits for human-readable display."""
    if not commits:
        return "No commits found."
    
    lines = [f"Found {len(commits)} commits:\n"]
    for commit in commits:
        lines.append(format_commit_for_display(commit))
        lines.append("")
    return "\n".join(lines)


def main():
    """Main entry point for the commit lister."""
    parser = argparse.ArgumentParser(
        description="List commits in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run scripts/commit_list.py owner/repo
  uv run scripts/commit_list.py owner/repo --branch develop
  uv run scripts/commit_list.py owner/repo --path src/main.py
  uv run scripts/commit_list.py owner/repo --author octocat
  uv run scripts/commit_list.py owner/repo --json
        """
    )
    
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("--branch", "-b", help="Branch name")
    parser.add_argument("--path", "-p", help="Only commits containing this file path")
    parser.add_argument("--author", "-a", help="Filter by author username or email")
    parser.add_argument("--since", help="Only commits after this date (ISO 8601)")
    parser.add_argument("--until", help="Only commits before this date (ISO 8601)")
    parser.add_argument("--per-page", type=int, default=30, help="Results per page")
    parser.add_argument("--page", type=int, default=1, help="Page number")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    commits = list_commits(
        token, owner, repo,
        branch=args.branch,
        path=args.path,
        author=args.author,
        since=args.since,
        until=args.until,
        per_page=args.per_page,
        page=args.page,
    )
    
    if args.json:
        print(json.dumps(commits, indent=2))
    else:
        print(format_commits_for_display(commits))


if __name__ == "__main__":
    main()
