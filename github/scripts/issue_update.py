#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Issue Updater
====================
Update an existing issue in a GitHub repository.

This script can modify:
- Title and body
- State (open/closed)
- Labels and assignees
- Milestone

Usage:
    uv run scripts/issue_update.py owner/repo 123 --title "New title"
    uv run scripts/issue_update.py owner/repo 123 --state closed
    uv run scripts/issue_update.py owner/repo 123 --labels "bug,urgent"
    uv run scripts/issue_update.py owner/repo 123 --assignees "user1,user2"

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


def update_issue(
    token: str, owner: str, repo: str, issue_number: int,
    title: str = None, body: str = None, state: str = None,
    labels: list = None, assignees: list = None,
    milestone: int = None, state_reason: str = None
) -> dict:
    """
    Update an existing issue.
    
    Only provided parameters will be updated. Pass None to leave unchanged.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        issue_number: Issue number to update
        title: New title (optional)
        body: New body/description (optional)
        state: New state: 'open' or 'closed' (optional)
        labels: New labels list (replaces existing) (optional)
        assignees: New assignees list (replaces existing) (optional)
        milestone: Milestone number or None to clear (optional)
        state_reason: Reason for closing: 'completed' or 'not_planned' (optional)
        
    Returns:
        Updated issue dictionary
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/issues/{issue_number}"
    
    # Build payload with only provided values
    payload = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        payload["state"] = state
    if labels is not None:
        payload["labels"] = labels
    if assignees is not None:
        payload["assignees"] = assignees
    if milestone is not None:
        payload["milestone"] = milestone if milestone > 0 else None
    if state_reason is not None:
        payload["state_reason"] = state_reason
    
    if not payload:
        print("Error: No updates specified", file=sys.stderr)
        sys.exit(1)
    
    response = make_request_with_retry('patch', url, headers, json=payload)
    
    if response.status_code == 404:
        print(f"Error: Issue #{issue_number} not found in {owner}/{repo}",
              file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Issue #{issue_number}")
    return response.json()


def format_issue_for_display(issue: dict, changes: list) -> str:
    """Format the updated issue for display."""
    lines = []
    
    number = issue.get("number", 0)
    title = issue.get("title", "")
    state = issue.get("state", "open")
    html_url = issue.get("html_url", "")
    
    state_icon = "🟢" if state == "open" else "🔴"
    lines.append(f"✅ Updated issue #{number}: {title}")
    lines.append("")
    
    if changes:
        lines.append("Changes made:")
        for change in changes:
            lines.append(f"  • {change}")
        lines.append("")
    
    lines.append(f"Status: {state_icon} {state}")
    
    labels = issue.get("labels", [])
    if labels:
        label_names = [l.get("name", "") for l in labels]
        lines.append(f"Labels: {', '.join(label_names)}")
    
    assignees = issue.get("assignees", [])
    if assignees:
        assignee_names = [a.get("login", "") for a in assignees]
        lines.append(f"Assignees: {', '.join(assignee_names)}")
    
    if html_url:
        lines.append("")
        lines.append(f"🔗 {html_url}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Update an existing issue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Change title
  uv run scripts/issue_update.py owner/repo 123 --title "New title"

  # Close issue
  uv run scripts/issue_update.py owner/repo 123 --state closed

  # Close as not planned
  uv run scripts/issue_update.py owner/repo 123 --state closed --reason not_planned

  # Reopen issue
  uv run scripts/issue_update.py owner/repo 123 --state open

  # Update labels (replaces existing)
  uv run scripts/issue_update.py owner/repo 123 --labels "bug,high-priority"

  # Clear labels
  uv run scripts/issue_update.py owner/repo 123 --labels ""

  # Update assignees
  uv run scripts/issue_update.py owner/repo 123 --assignees "user1,user2"

  # Multiple updates at once
  uv run scripts/issue_update.py owner/repo 123 --title "New title" --state closed --labels "done"
        """
    )
    
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("issue_number", type=int, help="Issue number to update")
    parser.add_argument("--title", "-t", help="New title")
    parser.add_argument("--body", "-b", help="New body/description")
    parser.add_argument("--state", "-s", choices=["open", "closed"], help="New state")
    parser.add_argument("--reason", choices=["completed", "not_planned"],
                        help="Reason for closing (only with --state closed)")
    parser.add_argument("--labels", help="Comma-separated labels (replaces existing, empty to clear)")
    parser.add_argument("--assignees", help="Comma-separated usernames (replaces existing, empty to clear)")
    parser.add_argument("--milestone", type=int, help="Milestone number (0 to clear)")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    # Parse list arguments
    labels = None
    if args.labels is not None:
        labels = [l.strip() for l in args.labels.split(",") if l.strip()] if args.labels else []
    
    assignees = None
    if args.assignees is not None:
        assignees = [a.strip() for a in args.assignees.split(",") if a.strip()] if args.assignees else []
    
    # Track changes for display
    changes = []
    if args.title:
        changes.append(f"Title updated")
    if args.body:
        changes.append(f"Body updated")
    if args.state:
        if args.state == "closed" and args.reason:
            changes.append(f"State changed to {args.state} ({args.reason})")
        else:
            changes.append(f"State changed to {args.state}")
    if labels is not None:
        if labels:
            changes.append(f"Labels set to: {', '.join(labels)}")
        else:
            changes.append("Labels cleared")
    if assignees is not None:
        if assignees:
            changes.append(f"Assignees set to: {', '.join(assignees)}")
        else:
            changes.append("Assignees cleared")
    if args.milestone is not None:
        if args.milestone > 0:
            changes.append(f"Milestone set to #{args.milestone}")
        else:
            changes.append("Milestone cleared")
    
    issue = update_issue(
        token, owner, repo, args.issue_number,
        title=args.title, body=args.body, state=args.state,
        labels=labels, assignees=assignees,
        milestone=args.milestone, state_reason=args.reason,
    )
    
    if args.json:
        print(json.dumps(issue, indent=2))
    else:
        print(format_issue_for_display(issue, changes))


if __name__ == "__main__":
    main()
