#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub Repository Contents Viewer
=================================
Get file or directory contents from a GitHub repository.

This script retrieves:
- File contents (decoded from base64)
- Directory listings
- File metadata (SHA, size, type)

Usage:
    uv run scripts/repo_contents.py owner/repo
    uv run scripts/repo_contents.py owner/repo --path README.md
    uv run scripts/repo_contents.py owner/repo --path src/ --ref develop
    uv run scripts/repo_contents.py owner/repo --path config.json --json

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import base64
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


def get_contents(token: str, owner: str, repo: str, 
                 path: str = "", ref: str = None) -> dict | list:
    """
    Get contents of a file or directory from GitHub.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        path: Path to file or directory (empty for root)
        ref: Git ref (branch, tag, or commit SHA)
        
    Returns:
        Dictionary (for file) or list (for directory) of contents
    """
    headers = get_headers(token)
    
    # Build URL - path should not have leading slash
    path = path.lstrip("/")
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    
    # Add ref parameter if specified
    params = {}
    if ref:
        params["ref"] = ref
    
    # Make the API request
    response = requests.get(url, headers=headers, params=params)
    
    # Handle errors
    if response.status_code == 404:
        print(f"Error: Path '{path}' not found in {owner}/{repo}", file=sys.stderr)
        if ref:
            print(f"(ref: {ref})", file=sys.stderr)
        sys.exit(1)
    elif response.status_code != 200:
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    return response.json()


def format_file_for_display(content_data: dict) -> str:
    """
    Format a file's contents for human-readable display.
    
    Args:
        content_data: File data from GitHub API
        
    Returns:
        Formatted string with file info and content
    """
    lines = []
    
    # File header
    name = content_data.get("name", "Unknown")
    path = content_data.get("path", name)
    size = content_data.get("size", 0)
    sha = content_data.get("sha", "")[:8]  # First 8 chars of SHA
    
    lines.append(f"📄 {path}")
    lines.append(f"   Size: {size:,} bytes  |  SHA: {sha}")
    lines.append("")
    
    # Decode and display content
    encoding = content_data.get("encoding")
    content = content_data.get("content", "")
    
    if encoding == "base64" and content:
        try:
            decoded = base64.b64decode(content).decode("utf-8")
            lines.append("─" * 60)
            lines.append(decoded)
            lines.append("─" * 60)
        except (ValueError, UnicodeDecodeError) as e:
            lines.append(f"(Binary file - cannot display content: {e})")
    elif content_data.get("type") == "symlink":
        target = content_data.get("target", "Unknown")
        lines.append(f"(Symlink to: {target})")
    elif content_data.get("type") == "submodule":
        submodule_url = content_data.get("submodule_git_url", "Unknown")
        lines.append(f"(Submodule: {submodule_url})")
    else:
        lines.append("(No content available)")
    
    return "\n".join(lines)


def format_directory_for_display(contents: list, path: str = "") -> str:
    """
    Format a directory listing for human-readable display.
    
    Args:
        contents: List of content items from GitHub API
        path: Current directory path
        
    Returns:
        Formatted string with directory listing
    """
    if not contents:
        return f"📁 {path or '/'}\n   (Empty directory)"
    
    lines = []
    
    # Directory header
    lines.append(f"📁 {path or '/'}")
    lines.append(f"   {len(contents)} items")
    lines.append("")
    
    # Sort: directories first, then files
    dirs = [c for c in contents if c.get("type") == "dir"]
    files = [c for c in contents if c.get("type") != "dir"]
    
    # List directories
    for item in sorted(dirs, key=lambda x: x.get("name", "").lower()):
        name = item.get("name", "Unknown")
        lines.append(f"   📁 {name}/")
    
    # List files
    for item in sorted(files, key=lambda x: x.get("name", "").lower()):
        name = item.get("name", "Unknown")
        size = item.get("size", 0)
        item_type = item.get("type", "file")
        
        if item_type == "file":
            # Format size nicely
            if size >= 1024 * 1024:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            elif size >= 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
            lines.append(f"   📄 {name:<40} {size_str:>10}")
        elif item_type == "symlink":
            lines.append(f"   🔗 {name} (symlink)")
        elif item_type == "submodule":
            lines.append(f"   📦 {name} (submodule)")
        else:
            lines.append(f"   ❓ {name} ({item_type})")
    
    return "\n".join(lines)


def main():
    """
    Main entry point for the contents viewer.
    """
    parser = argparse.ArgumentParser(
        description="Get file or directory contents from a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get root directory listing
  uv run scripts/repo_contents.py owner/repo

  # Get a specific file
  uv run scripts/repo_contents.py owner/repo --path README.md

  # Get a directory listing
  uv run scripts/repo_contents.py owner/repo --path src/

  # Get contents from a specific branch
  uv run scripts/repo_contents.py owner/repo --path config.json --ref develop

  # Output as JSON (includes SHA and other metadata)
  uv run scripts/repo_contents.py owner/repo --path README.md --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Optional: path
    parser.add_argument(
        "--path", "-p",
        default="",
        help="Path to file or directory (default: root)"
    )
    
    # Optional: ref (branch, tag, or commit)
    parser.add_argument(
        "--ref", "-r",
        help="Git ref (branch, tag, or commit SHA)"
    )
    
    # Output format
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON with full metadata"
    )
    
    args = parser.parse_args()
    
    # Parse repository
    owner, repo = parse_repo(args.repo)
    
    # Get token and fetch contents
    token = get_token()
    contents = get_contents(token, owner, repo, args.path, args.ref)
    
    # Output results
    if args.json:
        print(json.dumps(contents, indent=2))
    elif isinstance(contents, list):
        # Directory listing
        print(format_directory_for_display(contents, args.path))
    else:
        # Single file
        print(format_file_for_display(contents))


if __name__ == "__main__":
    main()
