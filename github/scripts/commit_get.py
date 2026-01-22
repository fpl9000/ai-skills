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

This script retrieves detailed commit information including:
- Full commit message
- Author and committer info
- Parent commits
- File changes with stats (additions, deletions)
- Verification status (GPG signature)

Usage:
    uv run scripts/commit_get.py owner/repo abc123def456
    uv run scripts/commit_get.py owner/repo abc123def456 --json

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
    """Retrieve GitHub token from environment variable."""
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


def get_commit(token: str, owner: str, repo: str, sha: str) -> dict:
    """
    Get details for a specific commit.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        sha: Commit SHA
        
    Returns:
        Commit dictionary with full details
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/commits/{sha}"
    
    response = requests.get(url, headers=headers)
    
    # Handle errors
    if response.status_code == 404:
        print(f"Error: Commit {sha} not found in {owner}/{repo}", file=sys.stderr)
        sys.exit(1)
    elif response.status_code != 200:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_commit_for_display(commit: dict) -> str:
    """Format commit details for human-readable display."""
    lines = []
    
    sha = commit.get("sha", "")
    commit_data = commit.get("commit", {})
    stats = commit.get("stats", {})
    files = commit.get("files", [])
    
    # Header
    lines.append(f"📝 Commit: {sha[:8]}")
    lines.append(f"   Full SHA: {sha}")
    lines.append("")
    
    # Message
    message = commit_data.get("message", "")
    lines.append("Message:")
    for line in message.split("\n"):
        lines.append(f"   {line}")
    lines.append("")
    
    # Author
    author = commit_data.get("author", {})
    author_name = author.get("name", "Unknown")
    author_email = author.get("email", "")
    author_date = author.get("date", "")
    
    if author_date:
        try:
            dt = datetime.fromisoformat(author_date.replace("Z", "+00:00"))
            author_date = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            pass
    
    lines.append(f"Author: {author_name} <{author_email}>")
    lines.append(f"Date:   {author_date}")
    
    # Committer (if different from author)
    committer = commit_data.get("committer", {})
    committer_name = committer.get("name", "")
    if committer_name and committer_name != author_name:
        committer_email = committer.get("email", "")
        lines.append(f"Committer: {committer_name} <{committer_email}>")
    
    lines.append("")
    
    # Verification
    verification = commit_data.get("verification", {})
    if verification:
        verified = verification.get("verified", False)
        reason = verification.get("reason", "")
        if verified:
            lines.append("✅ Signature: Verified")
        else:
            lines.append(f"❌ Signature: {reason}")
        lines.append("")
    
    # Stats
    additions = stats.get("additions", 0)
    deletions = stats.get("deletions", 0)
    total = stats.get("total", 0)
    
    lines.append(f"Stats: +{additions} -{deletions} ({total} total changes)")
    lines.append("")
    
    # Files changed
    if files:
        lines.append(f"Files changed ({len(files)}):")
        for f in files[:20]:  # Limit display to first 20 files
            filename = f.get("filename", "")
            status = f.get("status", "")
            additions = f.get("additions", 0)
            deletions = f.get("deletions", 0)
            
            # Status indicator
            status_icon = {
                "added": "➕",
                "removed": "➖",
                "modified": "📝",
                "renamed": "📛",
                "copied": "📋",
            }.get(status, "❓")
            
            lines.append(f"   {status_icon} {filename} (+{additions} -{deletions})")
        
        if len(files) > 20:
            lines.append(f"   ... and {len(files) - 20} more files")
    
    # Parents
    parents = commit.get("parents", [])
    if parents:
        lines.append("")
        lines.append(f"Parents ({len(parents)}):")
        for parent in parents:
            parent_sha = parent.get("sha", "")[:8]
            lines.append(f"   {parent_sha}")
    
    # Web URL
    html_url = commit.get("html_url", "")
    if html_url:
        lines.append("")
        lines.append(f"🔗 View: {html_url}")
    
    return "\n".join(lines)


def main():
    """Main entry point for the commit viewer."""
    parser = argparse.ArgumentParser(
        description="Get details for a specific commit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get commit details
  uv run scripts/commit_get.py owner/repo abc123def456

  # Output as JSON (includes full diff stats)
  uv run scripts/commit_get.py owner/repo abc123def456 --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Required: commit SHA
    parser.add_argument(
        "sha",
        help="Commit SHA"
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
    
    # Get token and fetch commit
    token = get_token()
    commit = get_commit(token, owner, repo, args.sha)
    
    # Output results
    if args.json:
        print(json.dumps(commit, indent=2))
    else:
        print(format_commit_for_display(commit))


if __name__ == "__main__":
    main()
