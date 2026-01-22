#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Repository Lister
========================
List repositories for a user, organization, or the authenticated user.

This script retrieves repository information including:
- Repository name and description
- Visibility (public/private)
- Language and topics
- Star and fork counts
- Last updated timestamp

Usage:
    uv run scripts/repo_list.py
    uv run scripts/repo_list.py --user octocat
    uv run scripts/repo_list.py --org github
    uv run scripts/repo_list.py --json

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


def list_repos(token: str, user: str = None, org: str = None, 
               repo_type: str = "all", sort: str = "updated",
               per_page: int = 30, page: int = 1) -> list:
    """
    List repositories from GitHub API.
    
    Args:
        token: GitHub Personal Access Token
        user: Username to list repos for (optional)
        org: Organization to list repos for (optional)
        repo_type: Filter type (all, public, private, forks, sources, member)
        sort: Sort field (created, updated, pushed, full_name)
        per_page: Results per page (max 100)
        page: Page number
        
    Returns:
        List of repository dictionaries
    """
    headers = get_headers(token)
    
    # Determine the correct endpoint based on arguments
    if org:
        # Organization repositories
        url = f"{API_BASE}/orgs/{org}/repos"
    elif user:
        # Specific user's repositories
        url = f"{API_BASE}/users/{user}/repos"
    else:
        # Authenticated user's repositories
        url = f"{API_BASE}/user/repos"
    
    # Build query parameters
    params = {
        "type": repo_type,
        "sort": sort,
        "per_page": min(per_page, 100),  # GitHub max is 100
        "page": page,
    }
    
    # Make the API request
    response = requests.get(url, headers=headers, params=params)
    
    # Handle errors
    if response.status_code != 200:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_repo_for_display(repo: dict) -> str:
    """
    Format a repository for human-readable display.
    
    Args:
        repo: Repository dictionary from GitHub API
        
    Returns:
        Formatted string representation
    """
    lines = []
    
    # Repository name with visibility indicator
    visibility = "🔒" if repo.get("private") else "🌐"
    name = repo.get("full_name", repo.get("name", "Unknown"))
    lines.append(f"{visibility} {name}")
    
    # Description (if any)
    description = repo.get("description")
    if description:
        # Truncate long descriptions
        if len(description) > 70:
            description = description[:67] + "..."
        lines.append(f"   {description}")
    
    # Stats line
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    language = repo.get("language") or "Unknown"
    
    stats = f"   ⭐ {stars}  🍴 {forks}  📝 {language}"
    
    # Add last updated
    updated = repo.get("updated_at")
    if updated:
        # Parse and format the date
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            stats += f"  📅 {dt.strftime('%Y-%m-%d')}"
        except ValueError:
            pass
    
    lines.append(stats)
    
    return "\n".join(lines)


def format_repos_for_display(repos: list) -> str:
    """
    Format a list of repositories for display.
    
    Args:
        repos: List of repository dictionaries
        
    Returns:
        Formatted string with all repositories
    """
    if not repos:
        return "No repositories found."
    
    output = [f"Found {len(repos)} repositories:\n"]
    
    for repo in repos:
        output.append(format_repo_for_display(repo))
        output.append("")  # Blank line between repos
    
    return "\n".join(output)


def main():
    """
    Main entry point for the repository lister.
    """
    parser = argparse.ArgumentParser(
        description="List GitHub repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List your own repositories
  uv run scripts/repo_list.py

  # List a user's public repositories
  uv run scripts/repo_list.py --user octocat

  # List organization repositories
  uv run scripts/repo_list.py --org github

  # Filter and sort
  uv run scripts/repo_list.py --type public --sort stars

  # Output as JSON
  uv run scripts/repo_list.py --json
        """
    )
    
    # Target selection (mutually exclusive)
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--user", "-u",
        help="List repositories for this user"
    )
    target_group.add_argument(
        "--org", "-o",
        help="List repositories for this organization"
    )
    
    # Filtering and sorting
    parser.add_argument(
        "--type", "-t",
        dest="repo_type",
        default="all",
        choices=["all", "public", "private", "forks", "sources", "member"],
        help="Filter by repository type (default: all)"
    )
    parser.add_argument(
        "--sort", "-s",
        default="updated",
        choices=["created", "updated", "pushed", "full_name"],
        help="Sort repositories by (default: updated)"
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
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    # Get token and fetch repositories
    token = get_token()
    repos = list_repos(
        token,
        user=args.user,
        org=args.org,
        repo_type=args.repo_type,
        sort=args.sort,
        per_page=args.per_page,
        page=args.page,
    )
    
    # Output results
    if args.json:
        print(json.dumps(repos, indent=2))
    else:
        print(format_repos_for_display(repos))


if __name__ == "__main__":
    main()
