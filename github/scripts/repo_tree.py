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
need to see the entire structure of a repository. Uses the Git Trees API
which returns all files in a single request.

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
    get_ref_sha,
    format_size,
)


# =============================================================================
# API Functions
# =============================================================================

def get_tree(
    token: str,
    owner: str,
    repo: str,
    tree_sha: str,
    recursive: bool = True
) -> dict:
    """
    Get the git tree for a repository.
    
    The Git Trees API is more efficient than the Contents API for getting
    a full repository structure, as it returns all items in a single request.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        tree_sha: SHA of the tree (usually from a commit)
        recursive: Whether to get all nested items (default: True)
        
    Returns:
        Tree dictionary with 'sha', 'tree' (list of items), and 'truncated'
    """
    headers = get_headers(token)
    
    url = f"{API_BASE}/repos/{owner}/{repo}/git/trees/{tree_sha}"
    
    # Request recursive listing to get all files
    params = {}
    if recursive:
        params["recursive"] = "1"
    
    response = make_request_with_retry('get', url, headers, params=params)
    
    handle_api_error(response, f"Tree {tree_sha[:8]}")
    
    return response.json()


def get_tree_for_ref(
    token: str,
    owner: str,
    repo: str,
    ref: str = None
) -> dict:
    """
    Get the tree for a specific git reference (branch, tag, or commit).
    
    This resolves the ref to a commit SHA, then fetches the associated tree.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        ref: Git reference (branch, tag, commit SHA, or None for default)
        
    Returns:
        Tree dictionary from the API
    """
    # If no ref specified, use the default branch
    if not ref:
        ref = get_default_branch(token, owner, repo)
    
    # Get the commit SHA for the ref
    commit_sha = get_ref_sha(token, owner, repo, ref)
    
    # Get the tree for that commit
    return get_tree(token, owner, repo, commit_sha, recursive=True)


# =============================================================================
# Display Formatting Functions
# =============================================================================

def filter_tree_by_path(tree_items: list, path_prefix: str) -> list:
    """
    Filter tree items to only those under a specific path.
    
    Args:
        tree_items: List of tree items from the API
        path_prefix: Path prefix to filter by (e.g., "src/")
        
    Returns:
        Filtered list of tree items
    """
    if not path_prefix:
        return tree_items
    
    # Normalize path prefix (ensure trailing slash for directories)
    path_prefix = path_prefix.rstrip("/") + "/"
    
    return [
        item for item in tree_items
        if item["path"].startswith(path_prefix) or item["path"] == path_prefix.rstrip("/")
    ]


def format_tree_for_display(tree: dict, path_filter: str = None) -> str:
    """
    Format a repository tree for human-readable display.
    
    Creates a hierarchical view similar to the 'tree' command, with
    file sizes and emoji indicators.
    
    Args:
        tree: Tree dictionary from the API
        path_filter: Optional path prefix to filter items
        
    Returns:
        Formatted string with the tree structure
    """
    lines = []
    
    # Header
    sha = tree.get("sha", "")[:8]
    lines.append(f"🌲 Repository tree (SHA: {sha})")
    
    if path_filter:
        lines.append(f"   Filtered to: {path_filter}")
    
    tree_items = tree.get("tree", [])
    
    # Apply path filter if specified
    if path_filter:
        tree_items = filter_tree_by_path(tree_items, path_filter)
    
    lines.append(f"   {len(tree_items)} items")
    lines.append("")
    
    # Sort items: directories first at each level, then alphabetically
    # Group by first path component for better display
    sorted_items = sorted(
        tree_items,
        key=lambda x: (
            # Put directories before files at same level
            0 if x["type"] == "tree" else 1,
            # Then sort alphabetically
            x["path"].lower()
        )
    )
    
    # Display each item with appropriate indentation based on path depth
    for item in sorted_items:
        path = item["path"]
        item_type = item["type"]
        
        # Calculate indentation based on path depth
        depth = path.count("/")
        indent = "   " + "    " * depth
        
        # Get just the name (last component of path)
        name = path.split("/")[-1]
        
        if item_type == "tree":
            # Directory
            lines.append(f"{indent}📁 {name}/")
        elif item_type == "blob":
            # File - show size
            size = format_size(item.get("size", 0))
            lines.append(f"{indent}📄 {name:<40} {size:>10}")
        else:
            # Other (submodule, symlink, etc.)
            lines.append(f"{indent}🔗 {name} ({item_type})")
    
    # Note if tree was truncated (very large repos)
    if tree.get("truncated"):
        lines.append("")
        lines.append("⚠️  Tree was truncated due to size. Use --path to filter.")
    
    return "\n".join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the tree viewer.
    
    Parses command-line arguments and displays the repository tree.
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

  # JSON output
  uv run scripts/repo_tree.py owner/repo --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Optional: git reference
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
    
    # Parse repository and get token
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    # Fetch tree
    tree = get_tree_for_ref(token, owner, repo, args.ref)
    
    # Output based on format
    if args.json:
        # If filtering, apply filter to JSON output too
        if args.path:
            tree["tree"] = filter_tree_by_path(tree["tree"], args.path)
        print(json.dumps(tree, indent=2))
    else:
        print(format_tree_for_display(tree, args.path))


if __name__ == "__main__":
    main()
