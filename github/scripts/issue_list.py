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
import sys
from datetime import datetime

from github_common import (
    API_BASE, get_token, get_headers, parse_repo,
    make_request_with_retry, handle_api_error,
)


def list_issues(
    token: str, owner: str, repo: str,
    state: str = "open", labels: str = None,
    assignee: str = None, sort: str = "created",
    direction: str = "desc", per_page: int = 30, page: int = 1
) -> list:
    """List issues from a GitHub repository."""
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/issues"
    
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
    
    response = make_request_with_retry('get', url, headers, params=params)
    handle_api_error(response, f"Issues in {owner}/{repo}")
    
    # Filter out pull requests (they also appear in issues endpoint)
    issues = [i for i in response.json() if "pull_request" not in i]
    return issues


def format_issue_for_display(issue: dict) -> str:
    """Format a single issue for display."""
    lines = []
    
    number = issue.get("number", 0)
    title = issue.get("title", "")
    state = issue.get("state", "open")
    
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
    
    # Created info
    created = issue.get("created_at", "")
    author = issue.get("user", {}).get("login", "Unknown")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    lines.append(f"   Created: {created} by {author}")
    
    return "\n".join(lines)


def format_issues_for_display(issues: list) -> str:
    """Format a list of issues for display."""
    if not issues:
        return "No issues found."
    
    lines = [f"Found {len(issues)} issues:\n"]
    for issue in issues:
        lines.append(format_issue_for_display(issue))
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="List issues in a GitHub repository")
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("--state", default="open", choices=["open", "closed", "all"])
    parser.add_argument("--labels", help="Comma-separated list of label names")
    parser.add_argument("--assignee", help="Filter by assignee username")
    parser.add_argument("--sort", default="created", choices=["created", "updated", "comments"])
    parser.add_argument("--direction", default="desc", choices=["asc", "desc"])
    parser.add_argument("--per-page", type=int, default=30)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--json", "-j", action="store_true")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    issues = list_issues(
        token, owner, repo,
        state=args.state, labels=args.labels,
        assignee=args.assignee, sort=args.sort,
        direction=args.direction, per_page=args.per_page, page=args.page,
    )
    
    if args.json:
        print(json.dumps(issues, indent=2))
    else:
        print(format_issues_for_display(issues))


if __name__ == "__main__":
    main()
