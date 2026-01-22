#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Issue Lister
===================
List issues in a GitHub repository.

This script retrieves issue information including:
- Issue number and title
- State (open/closed)
- Labels and assignees
- Creation date and author

Usage:
    uv run scripts/issue_list.py owner/repo
    uv run scripts/issue_list.py owner/repo --state all
    uv run scripts/issue_list.py owner/repo --labels "bug,high-priority"
    uv run scripts/issue_list.py owner/repo --json

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


def list_issues(token: str, owner: str, repo: str,
                state: str = "open", labels: str = None,
                assignee: str = None, sort: str = "created",
                direction: str = "desc",
                per_page: int = 30, page: int = 1) -> list:
    """
    List issues from a GitHub repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        state: Filter by state (open, closed, all)
        labels: Comma-separated list of label names
        assignee: Filter by assignee username
        sort: Sort by (created, updated, comments)
        direction: Sort direction (asc, desc)
        per_page: Results per page (max 100)
        page: Page number
        
    Returns:
        List of issue dictionaries
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/issues"
    
    # Build query parameters
    params = {
        "state": state,
        "sort": sort,
        "direction": direction,
        "per_page": min(per_page, 100),
        "page": page,
    }
    
    if labels:
        params["labels"] = labels
    if assignee:
        params["assignee"] = assignee
    
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
    
    # Filter out pull requests (they also appear in the issues endpoint)
    issues = [i for i in response.json() if "pull_request" not in i]
    
    return issues


def format_issue_for_display(issue: dict) -> str:
    """Format a single issue for human-readable display."""
    lines = []
    
    number = issue.get("number", 0)
    title = issue.get("title", "")
    state = issue.get("state", "")
    
    # Truncate long titles
    if len(title) > 60:
        title = title[:57] + "..."
    
    # State indicator
    state_icon = "🟢" if state == "open" else "🔴"
    
    lines.append(f"{state_icon} #{number}: {title}")
    
    # Labels
    labels = issue.get("labels", [])
    if labels:
        label_names = [l.get("name", "") for l in labels]
        lines.append(f"   Labels: {', '.join(label_names)}")
    
    # Assignees
    assignees = issue.get("assignees", [])
    if assignees:
        assignee_names = [a.get("login", "") for a in assignees]
        lines.append(f"   Assignees: {', '.join(assignee_names)}")
    
    # Author and date
    user = issue.get("user", {})
    author = user.get("login", "Unknown")
    created = issue.get("created_at", "")
    
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    
    lines.append(f"   By: {author} on {created}")
    
    return "\n".join(lines)


def format_issues_for_display(issues: list, state: str) -> str:
    """Format a list of issues for display."""
    if not issues:
        return f"No {state} issues found."
    
    output = [f"Found {len(issues)} issues:\n"]
    
    for issue in issues:
        output.append(format_issue_for_display(issue))
        output.append("")
    
    return "\n".join(output)


def main():
    """Main entry point for the issue lister."""
    parser = argparse.ArgumentParser(
        description="List issues in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List open issues (default)
  uv run scripts/issue_list.py owner/repo

  # List all issues (including closed)
  uv run scripts/issue_list.py owner/repo --state all

  # Filter by labels
  uv run scripts/issue_list.py owner/repo --labels "bug,high-priority"

  # Filter by assignee
  uv run scripts/issue_list.py owner/repo --assignee octocat

  # Sort by comments (most commented first)
  uv run scripts/issue_list.py owner/repo --sort comments

  # Output as JSON
  uv run scripts/issue_list.py owner/repo --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Optional filters
    parser.add_argument(
        "--state", "-s",
        default="open",
        choices=["open", "closed", "all"],
        help="Filter by state (default: open)"
    )
    parser.add_argument(
        "--labels", "-l",
        help="Comma-separated list of label names"
    )
    parser.add_argument(
        "--assignee", "-a",
        help="Filter by assignee username"
    )
    parser.add_argument(
        "--sort",
        default="created",
        choices=["created", "updated", "comments"],
        help="Sort by (default: created)"
    )
    parser.add_argument(
        "--direction", "-d",
        default="desc",
        choices=["asc", "desc"],
        help="Sort direction (default: desc)"
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
    
    # Get token and fetch issues
    token = get_token()
    issues = list_issues(
        token, owner, repo,
        state=args.state,
        labels=args.labels,
        assignee=args.assignee,
        sort=args.sort,
        direction=args.direction,
        per_page=args.per_page,
        page=args.page,
    )
    
    # Output results
    if args.json:
        print(json.dumps(issues, indent=2))
    else:
        print(format_issues_for_display(issues, args.state))


if __name__ == "__main__":
    main()
