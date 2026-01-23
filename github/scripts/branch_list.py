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
import sys

# Import shared utilities from the common module
from github_common import (
    API_BASE,
    get_token,
    get_headers,
    parse_repo,
    make_request_with_retry,
    handle_api_error,
    get_default_branch,
)


# =============================================================================
# API Functions
# =============================================================================

def list_branches(
    token: str,
    owner: str,
    repo: str,
    per_page: int = 30,
    page: int = 1
) -> list:
    """
    List branches in a GitHub repository.
    
    Retrieves all branches with their commit SHAs and protection status.
    Results are paginated.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        per_page: Results per page (max 100)
        page: Page number
        
    Returns:
        List of branch dictionaries from the API
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/branches"
    
    params = {
        "per_page": min(per_page, 100),
        "page": page,
    }
    
    response = make_request_with_retry('get', url, headers, params=params)
    
    handle_api_error(response, f"Branches in {owner}/{repo}")
    
    return response.json()


# =============================================================================
# Display Formatting Functions
# =============================================================================

def format_branches_for_display(
    branches: list,
    default_branch: str = None
) -> str:
    """
    Format branch list for human-readable display.
    
    Args:
        branches: List of branch dictionaries from the API
        default_branch: Name of the default branch (to mark it)
        
    Returns:
        Formatted string with branch listing
    """
    if not branches:
        return "No branches found."
    
    lines = [f"Found {len(branches)} branches:\n"]
    
    for branch in branches:
        name = branch.get("name", "Unknown")
        sha = branch.get("commit", {}).get("sha", "")[:8]
        protected = branch.get("protected", False)
        
        # Build status indicators
        indicators = []
        if name == default_branch:
            indicators.append("default")
        if protected:
            indicators.append("🔒 protected")
        
        status = f" ({', '.join(indicators)})" if indicators else ""
        
        lines.append(f"  🌿 {name:<30} {sha}{status}")
    
    return "\n".join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the branch lister.
    
    Parses command-line arguments and displays branch information.
    """
    parser = argparse.ArgumentParser(
        description="List branches in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all branches
  uv run scripts/branch_list.py owner/repo

  # JSON output
  uv run scripts/branch_list.py owner/repo --json

  # Pagination
  uv run scripts/branch_list.py owner/repo --per-page 100
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
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
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    # Parse repository
    owner, repo = parse_repo(args.repo)
    
    # Get token
    token = get_token()
    
    # Get default branch for display purposes
    default_branch = None
    if not args.json:
        try:
            default_branch = get_default_branch(token, owner, repo)
        except SystemExit:
            pass  # Continue without default branch info
    
    # List branches
    branches = list_branches(
        token, owner, repo,
        per_page=args.per_page,
        page=args.page,
    )
    
    # Output results
    if args.json:
        print(json.dumps(branches, indent=2))
    else:
        print(format_branches_for_display(branches, default_branch))


if __name__ == "__main__":
    main()
