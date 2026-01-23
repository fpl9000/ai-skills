#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Pull Request Viewer
==========================
Get details for a specific pull request.

This script retrieves detailed PR information including:
- Title, body, and state
- Branch info (head/base)
- Author and reviewers
- Review status
- Merge status and conflicts
- Commit and file change counts

Usage:
    uv run scripts/pr_get.py owner/repo 123
    uv run scripts/pr_get.py owner/repo 123 --json

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


def get_pull_request(token: str, owner: str, repo: str, pr_number: int) -> dict:
    """Get details for a specific pull request."""
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
    
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 404:
        print(f"Error: Pull request #{pr_number} not found in {owner}/{repo}",
              file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Pull request #{pr_number}")
    return response.json()


def format_pr_for_display(pr: dict) -> str:
    """Format a pull request for detailed display."""
    lines = []
    
    number = pr.get("number", 0)
    title = pr.get("title", "")
    state = pr.get("state", "open")
    merged = pr.get("merged", False)
    draft = pr.get("draft", False)
    mergeable = pr.get("mergeable")
    mergeable_state = pr.get("mergeable_state", "unknown")
    
    # State indicator
    if merged:
        state_icon, state_text = "🟣", "merged"
    elif state == "closed":
        state_icon, state_text = "🔴", "closed"
    elif draft:
        state_icon, state_text = "⚪", "draft"
    else:
        state_icon, state_text = "🟢", "open"
    
    lines.append(f"{state_icon} Pull Request #{number}: {title}")
    lines.append(f"   Status: {state_text}")
    lines.append("")
    
    # Branch info
    base = pr.get("base", {}).get("ref", "")
    head = pr.get("head", {}).get("ref", "")
    lines.append(f"Branches: {head} → {base}")
    
    # Author info
    author = pr.get("user", {}).get("login", "Unknown")
    created = pr.get("created_at", "")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    lines.append(f"Author: {author}")
    lines.append(f"Created: {created}")
    
    # Update time
    updated = pr.get("updated_at", "")
    if updated:
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            updated = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
        lines.append(f"Updated: {updated}")
    
    lines.append("")
    
    # Stats
    commits = pr.get("commits", 0)
    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)
    changed_files = pr.get("changed_files", 0)
    
    lines.append(f"Stats: {commits} commits, {changed_files} files changed")
    lines.append(f"       +{additions} additions, -{deletions} deletions")
    lines.append("")
    
    # Merge status (for open PRs)
    if state == "open" and not merged:
        if mergeable is None:
            lines.append("Mergeable: checking...")
        elif mergeable:
            lines.append(f"Mergeable: ✅ yes ({mergeable_state})")
        else:
            lines.append(f"Mergeable: ❌ no ({mergeable_state})")
            if mergeable_state == "dirty":
                lines.append("           Conflicts need to be resolved")
        lines.append("")
    
    # Merged info
    if merged:
        merged_at = pr.get("merged_at", "")
        merged_by = pr.get("merged_by", {}).get("login", "Unknown")
        merge_commit = pr.get("merge_commit_sha", "")[:8]
        
        if merged_at:
            try:
                dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                merged_at = dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass
        
        lines.append(f"Merged: {merged_at} by {merged_by}")
        lines.append(f"Merge commit: {merge_commit}")
        lines.append("")
    
    # Reviewers
    requested_reviewers = pr.get("requested_reviewers", [])
    if requested_reviewers:
        reviewer_names = [r.get("login", "") for r in requested_reviewers]
        lines.append(f"Reviewers requested: {', '.join(reviewer_names)}")
    
    # Labels
    labels = pr.get("labels", [])
    if labels:
        label_names = [l.get("name", "") for l in labels]
        lines.append(f"Labels: {', '.join(label_names)}")
    
    # Body/description
    body = pr.get("body", "")
    if body:
        lines.append("")
        lines.append("Description:")
        lines.append("─" * 40)
        # Truncate long bodies
        if len(body) > 500:
            body = body[:500] + "..."
        lines.append(body)
        lines.append("─" * 40)
    
    # URL
    html_url = pr.get("html_url", "")
    if html_url:
        lines.append("")
        lines.append(f"🔗 {html_url}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Get details for a pull request")
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("pr_number", type=int, help="Pull request number")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    pr = get_pull_request(token, owner, repo, args.pr_number)
    
    if args.json:
        print(json.dumps(pr, indent=2))
    else:
        print(format_pr_for_display(pr))


if __name__ == "__main__":
    main()
