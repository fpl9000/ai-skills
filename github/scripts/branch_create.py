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
    
    if response.status_code != 200:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json().get("default_branch", "main")


def get_ref_sha(token: str, owner: str, repo: str, ref: str) -> str:
    """
    Get the SHA for a given ref (branch, tag, or commit).
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        ref: Branch name, tag name, or commit SHA
        
    Returns:
        The commit SHA for the ref
    """
    headers = get_headers(token)
    
    # First try as a branch
    url = f"{API_BASE}/repos/{owner}/{repo}/git/refs/heads/{ref}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get("object", {}).get("sha")
    
    # Try as a tag
    url = f"{API_BASE}/repos/{owner}/{repo}/git/refs/tags/{ref}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        obj = response.json().get("object", {})
        # Tags can point to tag objects or directly to commits
        if obj.get("type") == "tag":
            # Need to dereference the tag object
            tag_url = obj.get("url")
            tag_response = requests.get(tag_url, headers=headers)
            if tag_response.status_code == 200:
                return tag_response.json().get("object", {}).get("sha")
        return obj.get("sha")
    
    # Try as a commit SHA directly
    url = f"{API_BASE}/repos/{owner}/{repo}/git/commits/{ref}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json().get("sha")
    
    # Nothing found
    print(f"Error: Could not find ref '{ref}'", file=sys.stderr)
    print("Make sure it's a valid branch name, tag name, or commit SHA", file=sys.stderr)
    sys.exit(1)


def create_branch(token: str, owner: str, repo: str,
                  name: str, sha: str) -> dict:
    """
    Create a new branch in a GitHub repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        name: Name for the new branch
        sha: Commit SHA to point the branch to
        
    Returns:
        Dictionary with ref data from API response
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/git/refs"
    
    # The ref must be in the format "refs/heads/<branch_name>"
    body = {
        "ref": f"refs/heads/{name}",
        "sha": sha,
    }
    
    response = requests.post(url, headers=headers, json=body)
    
    # Handle errors
    if response.status_code == 422:
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        
        if "Reference already exists" in error_msg:
            print(f"Error: Branch '{name}' already exists", file=sys.stderr)
        else:
            print(f"Error: {error_msg}", file=sys.stderr)
        sys.exit(1)
    elif response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        sys.exit(1)
    elif response.status_code != 201:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_result_for_display(result: dict, name: str, source: str) -> str:
    """
    Format the API result for human-readable display.
    
    Args:
        result: API response dictionary
        name: New branch name
        source: Source ref that was used
        
    Returns:
        Formatted string with branch info
    """
    lines = []
    
    sha = result.get("object", {}).get("sha", "")[:8]
    ref = result.get("ref", "")
    url = result.get("url", "")
    
    lines.append(f"✅ Created branch: {name}")
    lines.append("")
    lines.append(f"   From: {source}")
    lines.append(f"   SHA: {sha}")
    lines.append(f"   Ref: {ref}")
    
    # Build web URL
    # Extract owner/repo from the API URL
    if "/repos/" in url:
        parts = url.split("/repos/")[1].split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            web_url = f"https://github.com/{owner}/{repo}/tree/{name}"
            lines.append(f"   View: {web_url}")
    
    return "\n".join(lines)


def main():
    """
    Main entry point for the branch creator.
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
        source_ref = args.source
    else:
        source_ref = get_default_branch(token, owner, repo)
    
    # Get SHA for the source ref
    sha = get_ref_sha(token, owner, repo, source_ref)
    
    # Create the branch
    result = create_branch(token, owner, repo, args.name, sha)
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result_for_display(result, args.name, source_ref))


if __name__ == "__main__":
    main()
