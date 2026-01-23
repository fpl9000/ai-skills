#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Branch Creator
=====================
Create a new branch in a GitHub repository.

This script creates branches by:
1. Getting the SHA of the source ref (branch, tag, or commit)
2. Creating a new ref pointing to that SHA

Usage:
    uv run scripts/branch_create.py owner/repo --name feature/new-feature
    uv run scripts/branch_create.py owner/repo --name hotfix/bug-123 --from develop

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
    get_default_branch,
    get_ref_sha,
)


# =============================================================================
# API Functions
# =============================================================================

def create_branch(
    token: str,
    owner: str,
    repo: str,
    branch_name: str,
    source_sha: str
) -> dict:
    """
    Create a new branch pointing to the given SHA.
    
    Creates a new git reference in the refs/heads namespace.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        branch_name: Name for the new branch (without refs/heads/)
        source_sha: SHA to point the branch at
        
    Returns:
        API response dictionary with ref info
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/git/refs"
    
    # Branch refs must be in the refs/heads namespace
    body = {
        "ref": f"refs/heads/{branch_name}",
        "sha": source_sha,
    }
    
    response = make_request_with_retry('post', url, headers, json=body)
    
    # Handle specific error cases
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 422:
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        
        # Check for common issues
        if "Reference already exists" in error_msg:
            print(f"Error: Branch '{branch_name}' already exists", file=sys.stderr)
        else:
            print(f"Error: {error_msg}", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code not in (200, 201):
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


# =============================================================================
# Display Formatting Functions
# =============================================================================

def format_branch_for_display(result: dict, branch_name: str, source: str) -> str:
    """
    Format the created branch for human-readable display.
    
    Args:
        result: API response dictionary
        branch_name: Name of the created branch
        source: Name of the source ref (branch/tag/SHA)
        
    Returns:
        Formatted string with branch info
    """
    lines = []
    
    sha = result.get("object", {}).get("sha", "")[:8]
    ref = result.get("ref", "")
    
    lines.append(f"✅ Created branch: {branch_name}")
    lines.append("")
    lines.append(f"🌿 Ref: {ref}")
    lines.append(f"   SHA: {sha}")
    lines.append(f"   Source: {source}")
    
    return "\n".join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the branch creator.
    
    Parses command-line arguments and creates the new branch.
    """
    parser = argparse.ArgumentParser(
        description="Create a new branch in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create branch from default branch
  uv run scripts/branch_create.py owner/repo --name feature/new-feature

  # Create branch from specific source branch
  uv run scripts/branch_create.py owner/repo \\
      --name hotfix/bug-123 \\
      --from develop

  # Create branch from specific commit SHA
  uv run scripts/branch_create.py owner/repo \\
      --name release/v1.0 \\
      --from abc123def456...
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
        help="Name for the new branch"
    )
    
    # Optional: source ref
    # Using metavar to show "--from" in help but store as "source"
    parser.add_argument(
        "--from", "-f",
        dest="source",
        help="Source branch, tag, or commit SHA (default: repo's default branch)"
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
    
    # Determine source ref
    if args.source:
        source = args.source
    else:
        source = get_default_branch(token, owner, repo)
    
    # Get the SHA for the source ref
    source_sha = get_ref_sha(token, owner, repo, source)
    
    # Create the branch
    result = create_branch(token, owner, repo, args.name, source_sha)
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_branch_for_display(result, args.name, source))


if __name__ == "__main__":
    main()
