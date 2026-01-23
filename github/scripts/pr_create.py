#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Pull Request Creator
============================
Create a new pull request in a GitHub repository.

Usage:
    uv run scripts/pr_create.py owner/repo --title "Add feature" --head feature-branch
    uv run scripts/pr_create.py owner/repo --title "Fix bug" --head fix-123 --base develop
    uv run scripts/pr_create.py owner/repo --title "WIP" --head wip-branch --draft

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import json
import sys

from github_common import (
    API_BASE, get_token, get_headers, parse_repo,
    make_request_with_retry, get_default_branch,
)


def create_pull_request(
    token: str, owner: str, repo: str,
    title: str, head: str, base: str = None,
    body: str = None, draft: bool = False,
    maintainer_can_modify: bool = True
) -> dict:
    """
    Create a new pull request.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        title: PR title
        head: Branch containing changes (source)
        base: Branch to merge into (target, defaults to default branch)
        body: PR description
        draft: Create as draft PR
        maintainer_can_modify: Allow maintainers to push to head branch
        
    Returns:
        Created pull request dictionary
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls"
    
    # Use default branch if base not specified
    if not base:
        base = get_default_branch(token, owner, repo)
    
    payload = {
        "title": title,
        "head": head,
        "base": base,
        "draft": draft,
        "maintainer_can_modify": maintainer_can_modify,
    }
    if body:
        payload["body"] = body
    
    response = make_request_with_retry('post', url, headers, json=payload)
    
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found or head branch '{head}' doesn't exist",
              file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 422:
        error_data = response.json()
        errors = error_data.get("errors", [])
        error_msg = error_data.get("message", "Validation failed")
        
        print(f"Error: {error_msg}", file=sys.stderr)
        for err in errors:
            if isinstance(err, dict):
                msg = err.get("message", str(err))
            else:
                msg = str(err)
            print(f"  - {msg}", file=sys.stderr)
        
        # Common error hints
        if "no commits between" in str(errors).lower():
            print("\nHint: The head branch has no new commits compared to base", file=sys.stderr)
        if "pull request already exists" in str(errors).lower():
            print("\nHint: A PR already exists for this branch combination", file=sys.stderr)
        sys.exit(1)
    elif response.status_code not in (200, 201):
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_pr_for_display(pr: dict) -> str:
    """Format the created PR for display."""
    lines = []
    
    number = pr.get("number", 0)
    title = pr.get("title", "")
    html_url = pr.get("html_url", "")
    draft = pr.get("draft", False)
    
    status = "draft" if draft else "open"
    icon = "⚪" if draft else "🟢"
    
    lines.append(f"✅ Created pull request #{number}: {title}")
    lines.append("")
    
    base = pr.get("base", {}).get("ref", "")
    head = pr.get("head", {}).get("ref", "")
    lines.append(f"   {head} → {base}")
    lines.append(f"   Status: {icon} {status}")
    
    if html_url:
        lines.append("")
        lines.append(f"🔗 {html_url}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Create a new pull request",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic PR
  uv run scripts/pr_create.py owner/repo --title "Add feature" --head feature-branch

  # PR to specific base branch
  uv run scripts/pr_create.py owner/repo --title "Fix bug" --head fix-123 --base develop

  # Draft PR
  uv run scripts/pr_create.py owner/repo --title "WIP: New feature" --head wip-branch --draft

  # PR with description
  uv run scripts/pr_create.py owner/repo --title "Add tests" --head test-branch \\
      --body "This PR adds unit tests for the auth module."
        """
    )
    
    parser.add_argument("repo", help="Repository in owner/repo format")
    parser.add_argument("--title", "-t", required=True, help="PR title")
    parser.add_argument("--head", "-h", required=True, dest="head_branch",
                        help="Branch containing changes (source)")
    parser.add_argument("--base", "-b", help="Branch to merge into (default: repo's default branch)")
    parser.add_argument("--body", help="PR description/body")
    parser.add_argument("--draft", "-d", action="store_true", help="Create as draft PR")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    pr = create_pull_request(
        token, owner, repo,
        title=args.title,
        head=args.head_branch,
        base=args.base,
        body=args.body,
        draft=args.draft,
    )
    
    if args.json:
        print(json.dumps(pr, indent=2))
    else:
        print(format_pr_for_display(pr))


if __name__ == "__main__":
    main()
