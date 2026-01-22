#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Branch Lister
====================
List branches in a GitHub repository.

This script retrieves branch information including:
- Branch name
- Commit SHA
- Protected status

Usage:
    uv run scripts/branch_list.py owner/repo
    uv run scripts/branch_list.py owner/repo --json

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
    """
    Retrieve GitHub token from environment variable.
    
    Returns the token if set, exits with error if missing.
    """
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        print("Create a token at: https://github.com/settings/tokens", file=sys.stderr)
        sys.exit(1)
    
    return token


def get_headers(token: str) -> dict:
    """
    Build HTTP headers for GitHub API requests.
    
    Args:
        token: GitHub Personal Access Token
        
    Returns:
        Dictionary of headers including authorization
    """
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "github-skill-script",
    }


def parse_repo(repo_string: str) -> tuple:
    """
    Parse owner/repo string into components.
    
    Args:
        repo_string: Repository in "owner/repo" format
        
    Returns:
        Tuple of (owner, repo)
    """
    parts = repo_string.split("/")
    if len(parts) != 2:
        print(f"Error: Invalid repository format '{repo_string}'", file=sys.stderr)
        print("Expected format: owner/repo (e.g., octocat/hello-world)", file=sys.stderr)
        sys.exit(1)
    
    return parts[0], parts[1]


def get_default_branch(token: str, owner: str, repo: str) -> str:
    """
    Get the default branch of a repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        
    Returns:
        Default branch name
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get("default_branch", "main")
    
    return "main"  # Fallback


def list_branches(token: str, owner: str, repo: str,
                  per_page: int = 30, page: int = 1) -> list:
    """
    List branches in a GitHub repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        per_page: Results per page (max 100)
        page: Page number
        
    Returns:
        List of branch dictionaries
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/branches"
    
    params = {
        "per_page": min(per_page, 100),
        "page": page,
    }
    
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
    
    return response.json()


def format_branches_for_display(branches: list, default_branch: str) -> str:
    """
    Format branches for human-readable display.
    
    Args:
        branches: List of branch dictionaries from GitHub API
        default_branch: Name of the default branch
        
    Returns:
        Formatted string with branch list
    """
    if not branches:
        return "No branches found."
    
    lines = []
    lines.append(f"Found {len(branches)} branches:\n")
    
    for branch in branches:
        name = branch.get("name", "Unknown")
        sha = branch.get("commit", {}).get("sha", "")[:8]
        protected = branch.get("protected", False)
        
        # Build display line
        # Mark default branch with a star
        if name == default_branch:
            prefix = "⭐"
        elif protected:
            prefix = "🔒"
        else:
            prefix = "  "
        
        lines.append(f"{prefix} {name:<40} {sha}")
    
    lines.append("")
    lines.append("Legend: ⭐ = default branch, 🔒 = protected")
    
    return "\n".join(lines)


def main():
    """
    Main entry point for the branch lister.
    """
    parser = argparse.ArgumentParser(
        description="List branches in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all branches
  uv run scripts/branch_list.py owner/repo

  # Output as JSON
  uv run scripts/branch_list.py owner/repo --json

  # Pagination
  uv run scripts/branch_list.py owner/repo --per-page 100 --page 2
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
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
    
    # Get token and fetch branches
    token = get_token()
    branches = list_branches(token, owner, repo, args.per_page, args.page)
    
    # Output results
    if args.json:
        print(json.dumps(branches, indent=2))
    else:
        default_branch = get_default_branch(token, owner, repo)
        print(format_branches_for_display(branches, default_branch))


if __name__ == "__main__":
    main()
