#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Commit Viewer
====================
Get details for a specific commit in a GitHub repository.

Usage:
    uv run scripts/commit_get.py owner/repo abc123def456
    uv run scripts/commit_get.py owner/repo abc123def456 --json

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import json
import sys
from datetime import datetime

from github_common import (
    API_BASE, get_token, get_headers, parse_repo,
    make_request_with_retry, handle_api_error,
)


def get_commit(token: str, owner: str, repo: str, sha: str) -> dict:
    """Get details for a specific commit."""
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/commits/{sha}"
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 404:
        print(f"Error: Commit {sha} not found in {owner}/{repo}", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Commit {sha[:8]}")
    return response.json()


def format_commit_for_display(commit: dict) -> str:
    """Format a commit for detailed display."""
    lines = []
    sha = commit.get("sha", "")
    commit_data = commit.get("commit", {})
    message = commit_data.get("message", "")
    
    lines.append(f"📝 Commit: {sha}")
    lines.append("")
    
    author = commit_data.get("author", {})
    lines.append(f"Author: {author.get('name', 'Unknown')} <{author.get('email', '')}>")
    
    date_str = author.get("date", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    lines.append(f"Date:   {date_str}")
    lines.append("")
    
    lines.append("Message:")
    for line in message.split("\n"):
        lines.append(f"    {line}")
    lines.append("")
    
    stats = commit.get("stats", {})
    if stats:
        lines.append(f"Stats: {stats.get('total', 0)} changes (+{stats.get('additions', 0)}, -{stats.get('deletions', 0)})")
        lines.append("")
    
    files = commit.get("files", [])
    if files:
        lines.append(f"Files changed ({len(files)}):")
        for f in files[:20]:
            status_icon = {"added": "➕", "removed": "➖", "modified": "📝", "renamed": "📛"}.get(f.get("status", "modified"), "📄")
            lines.append(f"  {status_icon} {f.get('filename', '')} (+{f.get('additions', 0)}, -{f.get('deletions', 0)})")
        if len(files) > 20:
            lines.append(f"  ... and {len(files) - 20} more files")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Get details for a specific commit")
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("sha", help="Commit SHA")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    commit = get_commit(token, owner, repo, args.sha)
    
    if args.json:
        print(json.dumps(commit, indent=2))
    else:
        print(format_commit_for_display(commit))


if __name__ == "__main__":
    main()
