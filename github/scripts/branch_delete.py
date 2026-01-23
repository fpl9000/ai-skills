#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Branch Deleter
=====================
Delete a branch from a GitHub repository.

This script deletes branches by removing the git reference.
Use with caution - this action cannot be undone easily.

Usage:
    uv run scripts/branch_delete.py owner/repo --name feature/old-feature
    uv run scripts/branch_delete.py owner/repo --name hotfix/merged-fix --force

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token

Note:
    - Cannot delete the default branch
    - Cannot delete protected branches (unless you have admin access)
    - Commonly used after merging a pull request
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
    get_default_branch,
)


# =============================================================================
# API Functions
# =============================================================================

def delete_branch(
    token: str,
    owner: str,
    repo: str,
    branch_name: str
) -> bool:
    """
    Delete a branch from a GitHub repository.
    
    Deletes the git reference for the branch. This cannot be undone
    without knowledge of the commit SHA the branch pointed to.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        branch_name: Name of the branch to delete (without refs/heads/)
        
    Returns:
        True if deletion was successful
    """
    headers = get_headers(token)
    
    # Branch refs are in the refs/heads namespace
    url = f"{API_BASE}/repos/{owner}/{repo}/git/refs/heads/{branch_name}"
    
    response = make_request_with_retry('delete', url, headers)
    
    # Handle specific error cases
    if response.status_code == 404:
        print(f"Error: Branch '{branch_name}' not found in {owner}/{repo}",
              file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 422:
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        print(f"Error: {error_msg}", file=sys.stderr)
        
        # Check for protected branch
        if "protected" in error_msg.lower():
            print("Hint: This branch is protected and cannot be deleted",
                  file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 403:
        error_msg = response.json().get("message", "Forbidden")
        print(f"Error: {error_msg}", file=sys.stderr)
        print("You may not have permission to delete this branch", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code != 204:
        # 204 No Content is the success response for DELETE
        try:
            error_msg = response.json().get("message", "Unknown error")
        except ValueError:
            error_msg = response.text or "Unknown error"
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return True


def check_branch_exists(token: str, owner: str, repo: str, branch_name: str) -> dict:
    """
    Check if a branch exists and get its info.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        branch_name: Name of the branch to check
        
    Returns:
        Branch info dictionary, or None if not found
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/branches/{branch_name}"
    
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 200:
        return response.json()
    return None


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the branch deleter.
    
    Parses command-line arguments and deletes the specified branch.
    """
    parser = argparse.ArgumentParser(
        description="Delete a branch from a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete a branch (with confirmation)
  uv run scripts/branch_delete.py owner/repo --name feature/old-feature

  # Delete without confirmation
  uv run scripts/branch_delete.py owner/repo --name hotfix/merged-fix --force

  # Common workflow after merging a PR:
  # 1. Merge the PR (via web UI or pr_merge.py)
  # 2. Delete the branch
  uv run scripts/branch_delete.py owner/repo --name feature/my-feature --force

Note:
  - Cannot delete the default branch
  - Cannot delete protected branches without admin access
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Required: branch name
    parser.add_argument(
        "--name", "-n",
        required=True,
        help="Name of the branch to delete"
    )
    
    # Optional: skip confirmation
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompt"
    )
    
    # Output format
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output result as JSON"
    )
    
    args = parser.parse_args()
    
    # Parse repository
    owner, repo = parse_repo(args.repo)
    
    # Get token
    token = get_token()
    
    # Check if trying to delete default branch
    default_branch = get_default_branch(token, owner, repo)
    if args.name == default_branch:
        print(f"Error: Cannot delete the default branch '{default_branch}'",
              file=sys.stderr)
        sys.exit(1)
    
    # Get branch info for confirmation and display
    branch_info = check_branch_exists(token, owner, repo, args.name)
    if not branch_info:
        print(f"Error: Branch '{args.name}' not found in {owner}/{repo}",
              file=sys.stderr)
        sys.exit(1)
    
    # Check if branch is protected
    if branch_info.get("protected", False):
        print(f"Warning: Branch '{args.name}' is protected", file=sys.stderr)
        if not args.force:
            print("Use --force to attempt deletion anyway", file=sys.stderr)
            sys.exit(1)
    
    # Confirmation prompt (unless --force)
    if not args.force:
        sha = branch_info.get("commit", {}).get("sha", "")[:8]
        print(f"About to delete branch '{args.name}' (SHA: {sha})")
        print("This action cannot be easily undone.")
        response = input("Are you sure? [y/N]: ")
        if response.lower() not in ("y", "yes"):
            print("Cancelled.")
            sys.exit(0)
    
    # Delete the branch
    delete_branch(token, owner, repo, args.name)
    
    # Output results
    if args.json:
        result = {
            "deleted": True,
            "branch": args.name,
            "repository": f"{owner}/{repo}",
            "last_commit_sha": branch_info.get("commit", {}).get("sha", ""),
        }
        print(json.dumps(result, indent=2))
    else:
        sha = branch_info.get("commit", {}).get("sha", "")[:8]
        print(f"🗑️  Deleted branch: {args.name}")
        print(f"   Last commit: {sha}")
        print(f"   Repository: {owner}/{repo}")


if __name__ == "__main__":
    main()
