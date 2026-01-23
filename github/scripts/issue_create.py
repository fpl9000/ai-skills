#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Issue Creator
====================
Create a new issue in a GitHub repository.

Usage:
    uv run scripts/issue_create.py owner/repo --title "Bug report" --body "Description..."
    uv run scripts/issue_create.py owner/repo --title "Feature" --labels "enhancement"
    uv run scripts/issue_create.py owner/repo --title "Task" --assignees "user1,user2"

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import json
import sys

from github_common import (
    API_BASE, get_token, get_headers, parse_repo,
    make_request_with_retry, handle_api_error,
)


def create_issue(
    token: str, owner: str, repo: str,
    title: str, body: str = None,
    labels: list = None, assignees: list = None,
    milestone: int = None
) -> dict:
    """Create a new issue in a GitHub repository."""
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/issues"
    
    payload = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees
    if milestone:
        payload["milestone"] = milestone
    
    response = make_request_with_retry('post', url, headers, json=payload)
    handle_api_error(response, "Issue creation")
    return response.json()


def format_issue_for_display(issue: dict) -> str:
    """Format the created issue for display."""
    lines = []
    
    number = issue.get("number", 0)
    title = issue.get("title", "")
    html_url = issue.get("html_url", "")
    
    lines.append(f"✅ Created issue #{number}: {title}")
    lines.append("")
    
    if html_url:
        lines.append(f"🔗 {html_url}")
    
    labels = issue.get("labels", [])
    if labels:
        label_names = [l.get("name", "") for l in labels]
        lines.append(f"   Labels: {', '.join(label_names)}")
    
    assignees = issue.get("assignees", [])
    if assignees:
        assignee_names = [a.get("login", "") for a in assignees]
        lines.append(f"   Assignees: {', '.join(assignee_names)}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Create a new issue")
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("--title", "-t", required=True, help="Issue title")
    parser.add_argument("--body", "-b", help="Issue body/description")
    parser.add_argument("--labels", help="Comma-separated list of label names")
    parser.add_argument("--assignees", help="Comma-separated list of usernames")
    parser.add_argument("--milestone", type=int, help="Milestone number")
    parser.add_argument("--json", "-j", action="store_true")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    labels = args.labels.split(",") if args.labels else None
    assignees = args.assignees.split(",") if args.assignees else None
    
    issue = create_issue(
        token, owner, repo,
        title=args.title, body=args.body,
        labels=labels, assignees=assignees,
        milestone=args.milestone,
    )
    
    if args.json:
        print(json.dumps(issue, indent=2))
    else:
        print(format_issue_for_display(issue))


if __name__ == "__main__":
    main()
