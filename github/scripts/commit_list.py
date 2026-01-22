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
import os
import sys
from datetime import datetime

import requests


# GitHub API base URL
API_BASE = "https://api.github.com"


def get_token():
    """
    Retrieve GitHub token from environment variable.
    """
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        print("Create a token at: https://github.com/settings/tokens", file=sys.stderr)
        sys.exit(1)
    
    return token


def get_headers(token: str) -> dict:
    """Build HTTP headers for GitHub API requests."""
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "github-skill-script",
    }


def parse_repo(repo_string: str) -> tuple:
    """Parse owner/repo string into components."""
    parts = repo_string.split("/")
    if len(parts) != 2:
        print(f"Error: Invalid repository format '{repo_string}'", file=sys.stderr)
        print("Expected format: owner/repo (e.g., octocat/hello-world)", file=sys.stderr)
        sys.exit(1)
    
    return parts[0], parts[1]


def list_commits(token: str, owner: str, repo: str,
                 branch: str = None, path: str = None,
                 author: str = None, since: str = None, until: str = None,
                 per_page: int = 30, page: int = 1) -> list:
    """
    List commits from a GitHub repository.
    
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
        List of commit dictionaries
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/commits"
    
    # Build query parameters
    params = {
        "per_page": min(per_page, 100),
        "page": page,
    }
    
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
    
    # Make the API request
    response = requests.get(url, headers=headers, params=params)
    
    # Handle errors
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        sys.exit(1)
    elif response.status_code != 200:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_commit_for_display(commit: dict) -> str:
    """Format a single commit for human-readable display."""
    lines = []
    
    sha = commit.get("sha", "")[:8]
    commit_data = commit.get("commit", {})
    
    # Message (first line only for summary)
    message = commit_data.get("message", "")
    first_line = message.split("\n")[0]
    if len(first_line) > 60:
        first_line = first_line[:57] + "..."
    
    # Author info
    author = commit_data.get("author", {})
    author_name = author.get("name", "Unknown")
    author_date = author.get("date", "")
    
    # Format date
    date_str = ""
    if author_date:
        try:
            dt = datetime.fromisoformat(author_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            date_str = author_date
    
    lines.append(f"📝 {sha}  {first_line}")
    lines.append(f"   {author_name} • {date_str}")
    
    return "\n".join(lines)


def format_commits_for_display(commits: list) -> str:
    """Format a list of commits for display."""
    if not commits:
        return "No commits found."
    
    output = [f"Found {len(commits)} commits:\n"]
    
    for commit in commits:
        output.append(format_commit_for_display(commit))
        output.append("")
    
    return "\n".join(output)


def main():
    """Main entry point for the commit lister."""
    parser = argparse.ArgumentParser(
        description="List commits in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List recent commits on default branch
  uv run scripts/commit_list.py owner/repo

  # List commits on specific branch
  uv run scripts/commit_list.py owner/repo --branch develop

  # List commits for a specific file
  uv run scripts/commit_list.py owner/repo --path src/main.py

  # List commits by author
  uv run scripts/commit_list.py owner/repo --author octocat

  # List commits in date range
  uv run scripts/commit_list.py owner/repo --since 2024-01-01 --until 2024-12-31

  # Output as JSON
  uv run scripts/commit_list.py owner/repo --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Optional filters
    parser.add_argument(
        "--branch", "-b",
        help="Branch name (default: repo's default branch)"
    )
    parser.add_argument(
        "--path", "-p",
        help="Only commits affecting this file path"
    )
    parser.add_argument(
        "--author", "-a",
        help="Filter by author username or email"
    )
    parser.add_argument(
        "--since",
        help="Only commits after this date (ISO 8601 format, e.g., 2024-01-01)"
    )
    parser.add_argument(
        "--until",
        help="Only commits before this date (ISO 8601 format)"
    )
    
    # Pagination
    parser.add_argument(
        "--per-page",
        type=int,
        default=30,
        help="Results per page, max 100 (default: 30)"
    )
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Page number (default: 1)"
    )
    
    # Output format
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    # Parse repository
    owner, repo = parse_repo(args.repo)
    
    # Get token and fetch commits
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
    
    # Output results
    if args.json:
        print(json.dumps(commits, indent=2))
    else:
        print(format_commits_for_display(commits))


if __name__ == "__main__":
    main()
