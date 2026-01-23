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
import sys

# Import shared utilities from the common module
from github_common import (
    API_BASE,
    get_token,
    get_headers,
    parse_repo,
    make_request_with_retry,
    handle_api_error,
    format_size,
)


# =============================================================================
# API Functions
# =============================================================================

def get_contents(
    token: str,
    owner: str,
    repo: str,
    path: str = "",
    ref: str = None
) -> dict | list:
    """
    Get contents of a file or directory from GitHub.
    
    The GitHub Contents API returns different structures depending on
    whether the path points to a file or directory:
    - File: Returns a single object with content (base64 encoded)
    - Directory: Returns a list of objects (no content, just metadata)
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        path: Path to file or directory (default: root)
        ref: Git ref (branch, tag, or commit SHA) - optional
        
    Returns:
        Dictionary (file) or list of dictionaries (directory) from API
    """
    headers = get_headers(token)
    
    # Build URL - ensure path doesn't have leading slash
    path = path.lstrip("/")
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    
    # Add ref parameter if specified
    params = {}
    if ref:
        params["ref"] = ref
    
    # Make the API request
    response = make_request_with_retry('get', url, headers, params=params)
    
    # Handle specific error cases with helpful messages
    if response.status_code == 404:
        print(f"Error: Path '{path or '/'}' not found in {owner}/{repo}",
              file=sys.stderr)
        if ref:
            print(f"(on ref '{ref}')", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Contents at '{path}'")
    
    return response.json()


# =============================================================================
# Display Formatting Functions
# =============================================================================

def format_directory_for_display(contents: list, path: str) -> str:
    """
    Format a directory listing for human-readable display.
    
    Sorts items with directories first, then files, both alphabetically.
    Uses emoji indicators for item types.
    
    Args:
        contents: List of content items from the API
        path: The directory path being displayed
        
    Returns:
        Formatted string with the directory listing
    """
    lines = []
    
    # Header showing the path
    display_path = path if path else "/"
    lines.append(f"📁 {display_path}")
    lines.append("")
    
    # Sort: directories first, then files, alphabetically within each group
    dirs = sorted([c for c in contents if c["type"] == "dir"], 
                  key=lambda x: x["name"])
    files = sorted([c for c in contents if c["type"] == "file"], 
                   key=lambda x: x["name"])
    
    # Display directories first
    for item in dirs:
        lines.append(f"  📁 {item['name']}/")
    
    # Then display files with their sizes
    for item in files:
        size = format_size(item.get("size", 0))
        lines.append(f"  📄 {item['name']}  ({size})")
    
    # Summary line
    lines.append("")
    lines.append(f"Total: {len(dirs)} directories, {len(files)} files")
    
    return "\n".join(lines)


def format_file_for_display(content: dict) -> str:
    """
    Format a file's contents for human-readable display.
    
    Decodes base64 content and displays with metadata header.
    
    Args:
        content: File content dictionary from the API
        
    Returns:
        Formatted string with file metadata and contents
    """
    lines = []
    
    # File header with metadata
    name = content.get("name", "Unknown")
    size = format_size(content.get("size", 0))
    sha = content.get("sha", "")[:8]  # Short SHA for display
    
    lines.append(f"📄 {content.get('path', name)}")
    lines.append(f"   Size: {size}  |  SHA: {sha}")
    lines.append("")
    lines.append("─" * 60)
    
    # Decode and display content if available
    encoded_content = content.get("content", "")
    if encoded_content:
        try:
            # GitHub returns base64-encoded content
            decoded = base64.b64decode(encoded_content).decode("utf-8")
            lines.append(decoded)
        except (UnicodeDecodeError, ValueError):
            lines.append("[Binary content - cannot display as text]")
    else:
        lines.append("[No content available]")
    
    lines.append("─" * 60)
    
    return "\n".join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the contents viewer.
    
    Parses command-line arguments and displays file or directory contents.
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

  # JSON output (includes metadata like SHA, size, etc.)
  uv run scripts/repo_contents.py owner/repo --path README.md --json
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Optional: path within repository
    parser.add_argument(
        "--path", "-p",
        default="",
        help="Path to file or directory (default: root)"
    )
    
    # Optional: git reference
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
    
    # Parse repository and get token
    owner, repo = parse_repo(args.repo)
    token = get_token()
    
    # Fetch contents
    contents = get_contents(token, owner, repo, args.path, args.ref)
    
    # Output based on format and content type
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
