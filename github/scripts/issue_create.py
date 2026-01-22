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

This script creates issues with:
- Title and body/description
- Labels
- Assignees
- Milestone

Usage:
    uv run scripts/issue_create.py owner/repo --title "Bug report" --body "Description..."
    uv run scripts/issue_create.py owner/repo --title "Feature" --labels "enhancement"
    uv run scripts/issue_create.py owner/repo --title "Task" --assignees "user1,user2"

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import json
import os
import sys

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


def create_issue(token: str, owner: str, repo: str,
                 title: str, body: str = None,
                 labels: list = None, assignees: list = None,
                 milestone: int = None) -> dict:
    """
    Create a new issue in a GitHub repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        title: Issue title
        body: Issue body/description
        labels: List of label names
        assignees: List of usernames to assign
        milestone: Milestone number
        
    Returns:
        Created issue dictionary
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/issues"
    
    # Build request body
    data = {
        "title": title,
    }
    
    if body:
        data["body"] = body
    if labels:
        data["labels"] = labels
    if assignees:
        data["assignees"] = assignees
    if milestone:
        data["milestone"] = milestone
    
    # Make the API request
    response = requests.post(url, headers=headers, json=data)
    
    # Handle errors
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 403:
        print("Error: Permission denied. Check your token has 'repo' scope.", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 422:
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        errors = error_data.get("errors", [])
        print(f"Error: {error_msg}", file=sys.stderr)
        for err in errors:
            field = err.get("field", "")
            code = err.get("code", "")
            print(f"  - {field}: {code}", file=sys.stderr)
        sys.exit(1)
    elif response.status_code != 201:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_issue_for_display(issue: dict) -> str:
    """Format the created issue for human-readable display."""
    lines = []
    
    number = issue.get("number", 0)
    title = issue.get("title", "")
    html_url = issue.get("html_url", "")
    
    lines.append(f"✅ Created issue #{number}: {title}")
    lines.append("")
    
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
    
    # Milestone
    milestone = issue.get("milestone")
    if milestone:
        lines.append(f"   Milestone: {milestone.get('title', '')}")
    
    # Link
    if html_url:
        lines.append("")
        lines.append(f"🔗 View: {html_url}")
    
    return "\n".join(lines)


def main():
    """Main entry point for the issue creator."""
    parser = argparse.ArgumentParser(
        description="Create a new issue in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a simple issue
  uv run scripts/issue_create.py owner/repo \\
      --title "Bug: Something is broken" \\
      --body "Description of the bug..."

  # Create issue with labels
  uv run scripts/issue_create.py owner/repo \\
      --title "Feature request" \\
      --body "Please add this feature" \\
      --labels "enhancement,help-wanted"

  # Create issue with assignees
  uv run scripts/issue_create.py owner/repo \\
      --title "Task" \\
      --assignees "octocat,contributor"

  # Output as JSON
  uv run scripts/issue_create.py owner/repo \\
      --title "New issue" \\
      --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Required: title
    parser.add_argument(
        "--title", "-t",
        required=True,
        help="Issue title"
    )
    
    # Optional: body
    parser.add_argument(
        "--body", "-b",
        help="Issue body/description"
    )
    
    # Optional: labels
    parser.add_argument(
        "--labels", "-l",
        help="Comma-separated list of label names"
    )
    
    # Optional: assignees
    parser.add_argument(
        "--assignees", "-a",
        help="Comma-separated list of usernames to assign"
    )
    
    # Optional: milestone
    parser.add_argument(
        "--milestone", "-m",
        type=int,
        help="Milestone number"
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
    
    # Parse comma-separated lists
    labels = args.labels.split(",") if args.labels else None
    assignees = args.assignees.split(",") if args.assignees else None
    
    # Strip whitespace from list items
    if labels:
        labels = [l.strip() for l in labels]
    if assignees:
        assignees = [a.strip() for a in assignees]
    
    # Get token and create issue
    token = get_token()
    issue = create_issue(
        token, owner, repo,
        title=args.title,
        body=args.body,
        labels=labels,
        assignees=assignees,
        milestone=args.milestone,
    )
    
    # Output results
    if args.json:
        print(json.dumps(issue, indent=2))
    else:
        print(format_issue_for_display(issue))


if __name__ == "__main__":
    main()
