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
import sys
from datetime import datetime

# Import shared utilities from the common module
# This reduces code duplication and centralizes API versioning
from github_common import (
    API_BASE,
    get_token,
    get_headers,
    make_request_with_retry,
    handle_api_error,
)


# =============================================================================
# API Functions
# =============================================================================

def list_repos(
    token: str,
    user: str = None,
    org: str = None,
    repo_type: str = "all",
    sort: str = "updated",
    per_page: int = 30,
    page: int = 1
) -> list:
    """
    List repositories from GitHub API.
    
    Retrieves repositories based on the target (authenticated user, specific
    user, or organization). Results can be filtered and sorted.
    
    Args:
        token: GitHub Personal Access Token
        user: Username to list repos for (optional)
        org: Organization to list repos for (optional)
        repo_type: Filter type (all, public, private, forks, sources, member)
        sort: Sort field (created, updated, pushed, full_name)
        per_page: Results per page (max 100)
        page: Page number
        
    Returns:
        List of repository dictionaries from the API
    """
    headers = get_headers(token)
    
    # Determine the correct endpoint based on arguments
    # Each target type has a different API endpoint
    if org:
        # Organization repositories
        url = f"{API_BASE}/orgs/{org}/repos"
    elif user:
        # Specific user's public repositories
        url = f"{API_BASE}/users/{user}/repos"
    else:
        # Authenticated user's repositories (includes private repos)
        url = f"{API_BASE}/user/repos"
    
    # Build query parameters for filtering and pagination
    params = {
        "type": repo_type,
        "sort": sort,
        "per_page": min(per_page, 100),  # GitHub's maximum is 100
        "page": page,
    }
    
    # Make the API request with retry logic for rate limits
    response = make_request_with_retry('get', url, headers, params=params)
    
    # Handle any API errors
    handle_api_error(response, "Repository listing")
    
    return response.json()


# =============================================================================
# Display Formatting Functions
# =============================================================================

def format_repo_for_display(repo: dict) -> str:
    """
    Format a single repository for human-readable display.
    
    Creates a multi-line string with repository details including
    name, description, stats, and last update time.
    
    Args:
        repo: Repository dictionary from GitHub API
        
    Returns:
        Formatted string representation of the repository
    """
    lines = []
    
    # Repository name with visibility indicator emoji
    # 🔒 = private, 🌐 = public
    visibility = "🔒" if repo.get("private") else "🌐"
    name = repo.get("full_name", repo.get("name", "Unknown"))
    lines.append(f"{visibility} {name}")
    
    # Description (truncated if too long to fit nicely)
    description = repo.get("description")
    if description:
        # Truncate long descriptions to keep output readable
        if len(description) > 70:
            description = description[:67] + "..."
        lines.append(f"   {description}")
    
    # Stats line: stars, forks, language, last updated
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    language = repo.get("language") or "Unknown"
    
    stats = f"   ⭐ {stars}  🍴 {forks}  📝 {language}"
    
    # Parse and format the last updated date
    updated = repo.get("updated_at")
    if updated:
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            stats += f"  📅 {dt.strftime('%Y-%m-%d')}"
        except ValueError:
            pass  # Skip date if parsing fails
    
    lines.append(stats)
    
    return "\n".join(lines)


def format_repos_for_display(repos: list) -> str:
    """
    Format a list of repositories for human-readable display.
    
    Args:
        repos: List of repository dictionaries from the API
        
    Returns:
        Formatted string with all repositories
    """
    if not repos:
        return "No repositories found."
    
    output = [f"Found {len(repos)} repositories:\n"]
    
    for repo in repos:
        output.append(format_repo_for_display(repo))
        output.append("")  # Blank line between repos for readability
    
    return "\n".join(output)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the repository lister.
    
    Parses command-line arguments and outputs repository information
    in either human-readable or JSON format.
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
    
    # Target selection - user OR org, not both
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--user", "-u",
        help="List repositories for this user"
    )
    target_group.add_argument(
        "--org", "-o",
        help="List repositories for this organization"
    )
    
    # Filtering and sorting options
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
    
    # Pagination options
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
    
    # Output results in requested format
    if args.json:
        print(json.dumps(repos, indent=2))
    else:
        print(format_repos_for_display(repos))


if __name__ == "__main__":
    main()
