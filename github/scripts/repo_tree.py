#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Repository Tree Viewer
=============================
Get the full file tree of a GitHub repository (recursive listing).

This is more efficient than multiple calls to the contents API when you
need to see the entire structure of a repository.

Usage:
    uv run scripts/repo_tree.py owner/repo
    uv run scripts/repo_tree.py owner/repo --ref develop
    uv run scripts/repo_tree.py owner/repo --path src/
    uv run scripts/repo_tree.py owner/repo --json

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
        Default branch name (e.g., "main" or "master")
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


def get_tree(token: str, owner: str, repo: str, 
             ref: str = None, recursive: bool = True) -> dict:
    """
    Get the file tree of a repository.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        ref: Git ref (branch, tag, or commit SHA)
        recursive: Whether to get the full recursive tree
        
    Returns:
        Dictionary containing tree data
    """
    headers = get_headers(token)
    
    # If no ref specified, get the default branch
    if not ref:
        ref = get_default_branch(token, owner, repo)
    
    # Build URL for tree endpoint
    url = f"{API_BASE}/repos/{owner}/{repo}/git/trees/{ref}"
    
    # Add recursive parameter
    params = {}
    if recursive:
        params["recursive"] = "1"
    
    # Make the API request
    response = requests.get(url, headers=headers, params=params)
    
    # Handle errors
    if response.status_code == 404:
        print(f"Error: Ref '{ref}' not found in {owner}/{repo}", file=sys.stderr)
        sys.exit(1)
    elif response.status_code != 200:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def filter_tree_by_path(tree_items: list, path_prefix: str) -> list:
    """
    Filter tree items to only those under a specific path.
    
    Args:
        tree_items: List of tree items from GitHub API
        path_prefix: Path prefix to filter by
        
    Returns:
        Filtered list of tree items
    """
    if not path_prefix:
        return tree_items
    
    # Normalize the path prefix (remove leading/trailing slashes)
    path_prefix = path_prefix.strip("/")
    
    filtered = []
    for item in tree_items:
        item_path = item.get("path", "")
        if item_path.startswith(path_prefix):
            filtered.append(item)
    
    return filtered


def format_tree_for_display(tree_data: dict, path_filter: str = None) -> str:
    """
    Format the repository tree for human-readable display.
    
    Args:
        tree_data: Tree data from GitHub API
        path_filter: Optional path prefix to filter results
        
    Returns:
        Formatted string with tree structure
    """
    tree_items = tree_data.get("tree", [])
    sha = tree_data.get("sha", "")[:8]
    truncated = tree_data.get("truncated", False)
    
    # Filter by path if specified
    if path_filter:
        tree_items = filter_tree_by_path(tree_items, path_filter)
    
    if not tree_items:
        if path_filter:
            return f"No items found under path: {path_filter}"
        return "Empty repository"
    
    lines = []
    
    # Header
    lines.append(f"🌲 Repository tree (SHA: {sha})")
    if path_filter:
        lines.append(f"   Filtered to: {path_filter}")
    lines.append(f"   {len(tree_items)} items")
    if truncated:
        lines.append("   ⚠️  Tree was truncated (repository has many files)")
    lines.append("")
    
    # Build a tree structure
    # Sort items: directories first at each level, then alphabetically
    # We'll display with indentation based on path depth
    
    for item in sorted(tree_items, key=lambda x: (x.get("type") != "tree", x.get("path", "").lower())):
        path = item.get("path", "")
        item_type = item.get("type", "blob")
        size = item.get("size", 0)
        
        # Calculate indentation based on path depth
        depth = path.count("/")
        indent = "   " + "  " * depth
        
        # Get just the filename (last component of path)
        name = path.split("/")[-1] if "/" in path else path
        
        if item_type == "tree":
            lines.append(f"{indent}📁 {name}/")
        elif item_type == "blob":
            # Format size
            if size >= 1024 * 1024:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            elif size >= 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
            lines.append(f"{indent}📄 {name:<40} {size_str:>10}")
        elif item_type == "commit":
            # Submodule
            lines.append(f"{indent}📦 {name} (submodule)")
        else:
            lines.append(f"{indent}❓ {name} ({item_type})")
    
    return "\n".join(lines)


def main():
    """
    Main entry point for the tree viewer.
    """
    parser = argparse.ArgumentParser(
        description="Get the full file tree of a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get full tree of default branch
  uv run scripts/repo_tree.py owner/repo

  # Get tree from specific branch
  uv run scripts/repo_tree.py owner/repo --ref develop

  # Filter to specific directory
  uv run scripts/repo_tree.py owner/repo --path src/

  # Output as JSON
  uv run scripts/repo_tree.py owner/repo --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Optional: ref (branch, tag, or commit)
    parser.add_argument(
        "--ref", "-r",
        help="Git ref (branch, tag, or commit SHA)"
    )
    
    # Optional: path filter
    parser.add_argument(
        "--path", "-p",
        help="Filter to paths starting with this prefix"
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
    
    # Get token and fetch tree
    token = get_token()
    tree_data = get_tree(token, owner, repo, args.ref)
    
    # Output results
    if args.json:
        # Apply path filter to JSON output too
        if args.path:
            tree_data["tree"] = filter_tree_by_path(tree_data.get("tree", []), args.path)
        print(json.dumps(tree_data, indent=2))
    else:
        print(format_tree_for_display(tree_data, args.path))


if __name__ == "__main__":
    main()
