#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Pull Request Lister
==========================
List pull requests in a GitHub repository.

Usage:
    uv run scripts/pr_list.py owner/repo
    uv run scripts/pr_list.py owner/repo --state all
    uv run scripts/pr_list.py owner/repo --base main
    uv run scripts/pr_list.py owner/repo --json

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


def list_pull_requests(
    token: str, owner: str, repo: str,
    state: str = "open", base: str = None, head: str = None,
    sort: str = "created", direction: str = "desc",
    per_page: int = 30, page: int = 1
) -> list:
    """List pull requests from a GitHub repository."""
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls"
    
    params = {
        "state": state, "sort": sort, "direction": direction,
        "per_page": min(per_page, 100), "page": page,
    }
    if base:
        params["base"] = base
    if head:
        params["head"] = head
    
    response = make_request_with_retry('get', url, headers, params=params)
    handle_api_error(response, f"Pull requests in {owner}/{repo}")
    return response.json()


def format_pr_for_display(pr: dict) -> str:
    """Format a single pull request for display."""
    lines = []
    number = pr.get("number", 0)
    title = pr.get("title", "")
    state = pr.get("state", "open")
    merged = pr.get("merged_at") is not None
    draft = pr.get("draft", False)
    
    if merged:
        state_icon, state_text = "🟣", "merged"
    elif state == "closed":
        state_icon, state_text = "🔴", "closed"
    elif draft:
        state_icon, state_text = "⚪", "draft"
    else:
        state_icon, state_text = "🟢", "open"
    
    lines.append(f"{state_icon} #{number}: {title}")
    
    base = pr.get("base", {}).get("ref", "")
    head = pr.get("head", {}).get("ref", "")
    lines.append(f"   {head} → {base}")
    
    author = pr.get("user", {}).get("login", "Unknown")
    created = pr.get("created_at", "")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    lines.append(f"   Author: {author}  |  Created: {created}  |  Status: {state_text}")
    
    return "\n".join(lines)


def format_prs_for_display(prs: list) -> str:
    """Format a list of pull requests for display."""
    if not prs:
        return "No pull requests found."
    lines = [f"Found {len(prs)} pull requests:\n"]
    for pr in prs:
        lines.append(format_pr_for_display(pr))
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="List pull requests")
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("--state", default="open", choices=["open", "closed", "all"])
    parser.add_argument("--base", help="Filter by base branch")
    parser.add_argument("--head", help="Filter by head branch")
    parser.add_argument("--sort", default="created", choices=["created", "updated", "popularity", "long-running"])
    parser.add_argument("--direction", default="desc", choices=["asc", "desc"])
    parser.add_argument("--per-page", type=int, default=30)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--json", "-j", action="store_true")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    prs = list_pull_requests(
        token, owner, repo,
        state=args.state, base=args.base, head=args.head,
        sort=args.sort, direction=args.direction,
        per_page=args.per_page, page=args.page,
    )
    
    if args.json:
        print(json.dumps(prs, indent=2))
    else:
        print(format_prs_for_display(prs))


if __name__ == "__main__":
    main()
