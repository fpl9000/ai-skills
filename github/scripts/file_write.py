#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub File Writer
==================
Create or update files in a GitHub repository.

This script uses the GitHub Contents API to:
- Create new files with a commit
- Update existing files (requires the file's current SHA)
- Create files on specific branches
- Optionally set file mode (e.g., executable) via --mode

Supports both text and binary files (e.g., images, archives, executables).

Usage:
    uv run scripts/file_write.py owner/repo --path docs/README.md --content "..." --message "Add docs"
    uv run scripts/file_write.py owner/repo --path config.json --from-file local.json --message "Update config"
    uv run scripts/file_write.py owner/repo --path README.md --content "..." --sha abc123 --message "Update"
    
    # Create an executable script
    uv run scripts/file_write.py owner/repo --path scripts/build.sh --from-file build.sh --message "Add build script" --mode 755
    
    # Upload a binary file (e.g., ZIP archive, image)
    uv run scripts/file_write.py owner/repo --path assets/logo.png --from-file logo.png --message "Add logo"

Note on --mode:
    The GitHub Contents API doesn't support setting file modes directly.
    When --mode is specified, this script creates the file first, then
    makes a second commit to set the file mode using the Git Data API.
    This results in two commits but correctly sets the file permissions.

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import base64
import json
import sys
from typing import Union

# Import shared utilities from the common module
from github_common import (
    API_BASE,
    get_token,
    get_headers,
    parse_repo,
    make_request_with_retry,
    get_branch_head_sha,
    get_commit_tree_sha,
    get_tree_recursive,
    create_tree_with_changes,
    create_commit,
    update_branch_ref,
    user_mode_to_git_mode,
    git_mode_to_display,
    get_default_branch,
)


# =============================================================================
# API Functions
# =============================================================================

def set_file_mode(
    token: str,
    owner: str,
    repo: str,
    path: str,
    mode: str,
    branch: str,
) -> str:
    """
    Set the mode of a file using the Git Data API.
    
    This is called after creating/updating a file via the Contents API
    when the user specifies a --mode. The Contents API doesn't support
    setting modes, so we need a separate Git Data API operation.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        path: Path to the file
        mode: Target mode (user format like '755')
        branch: Branch the file is on
        
    Returns:
        The new commit SHA if mode was changed, None if already correct
        
    Exits:
        Exits with code 1 on API errors
    """
    # Convert user mode to git mode
    try:
        git_mode = user_mode_to_git_mode(mode)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Get current state
    head_sha = get_branch_head_sha(token, owner, repo, branch)
    tree_sha = get_commit_tree_sha(token, owner, repo, head_sha)
    tree_entries = get_tree_recursive(token, owner, repo, tree_sha)
    
    # Find the file
    normalized_path = path.strip("/")
    file_entry = None
    for entry in tree_entries:
        if entry["path"] == normalized_path:
            file_entry = entry
            break
    
    if not file_entry:
        print(f"Error: File '{path}' not found in tree", file=sys.stderr)
        sys.exit(1)
    
    if file_entry["mode"] == git_mode:
        # Already has correct mode
        return None
    
    # Create new tree with modified mode
    tree_changes = [{
        "path": normalized_path,
        "mode": git_mode,
        "type": "blob",
        "sha": file_entry["sha"],
    }]
    
    new_tree_sha = create_tree_with_changes(token, owner, repo, tree_sha, tree_changes)
    
    # Create commit for the mode change
    mode_display = git_mode[-3:]
    message = f"Set mode {mode_display} on {path}"
    new_commit_sha = create_commit(token, owner, repo, new_tree_sha, head_sha, message)
    
    # Update branch
    update_branch_ref(token, owner, repo, branch, new_commit_sha)
    
    return new_commit_sha


def create_or_update_file(
    token: str,
    owner: str,
    repo: str,
    path: str,
    content: Union[str, bytes],
    message: str,
    sha: str = None,
    branch: str = None
) -> tuple[dict, bool]:
    """
    Create or update a file in a GitHub repository.
    
    The distinction between create and update is determined by whether
    a SHA is provided. When updating, the SHA must match the current
    file's SHA to prevent overwriting concurrent changes.
    
    Supports both text (str) and binary (bytes) content. Binary content
    is useful for uploading images, archives, compiled files, etc.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        path: Path for the file in the repository
        content: File content as a string (text) or bytes (binary)
        message: Commit message
        sha: SHA of file being replaced (required for updates)
        branch: Branch to commit to (default: repo's default branch)
        
    Returns:
        Tuple of (API response dictionary, is_create boolean)
        is_create is True if this was a new file, False if update
    """
    headers = get_headers(token)
    
    # Build URL - path should not have leading slash
    path = path.lstrip("/")
    url = f"{API_BASE}/repos/{owner}/{repo}/contents/{path}"
    
    # Encode content as base64 (GitHub API requirement)
    # Handle both string (text) and bytes (binary) content
    if isinstance(content, str):
        # Text content: encode to UTF-8 bytes first
        content_bytes = content.encode("utf-8")
    else:
        # Binary content: already bytes, use directly
        content_bytes = content
    
    # Base64 encode the bytes for the GitHub API
    content_b64 = base64.b64encode(content_bytes).decode("utf-8")
    
    # Build request body
    body = {
        "message": message,
        "content": content_b64,
    }
    
    # Add optional parameters
    # SHA indicates this is an update (file already exists)
    if sha:
        body["sha"] = sha
    if branch:
        body["branch"] = branch
    
    # Determine if this is a create or update based on SHA
    # This is used for display purposes later
    is_create = sha is None
    
    # Make the API request
    response = make_request_with_retry('put', url, headers, json=body)
    
    # Handle specific error cases with helpful messages
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        if branch:
            print(f"(or branch '{branch}' does not exist)", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 409:
        # SHA mismatch - file was modified since it was read
        print("Error: File has been modified since you read it (SHA mismatch)",
              file=sys.stderr)
        print("Get the current SHA with: uv run scripts/repo_contents.py --json --path <path>",
              file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 422:
        # Validation error - often means SHA is required but not provided
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        errors = error_data.get("errors", [])
        
        print(f"Error: {error_msg}", file=sys.stderr)
        for err in errors:
            if isinstance(err, dict):
                print(f"  - {err}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        
        # Check if this is a "SHA required" error
        error_str = str(errors).lower()
        if "sha" in error_str or "sha" in error_msg.lower():
            print("\nHint: The file already exists. You need to provide --sha",
                  file=sys.stderr)
            print("Get the current SHA with: uv run scripts/repo_contents.py --json --path <path>",
                  file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code not in (200, 201):
        error_msg = response.json().get("message", "Unknown error")
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    # Return both the result and whether this was a create operation
    # Status 201 = created, 200 = updated
    # But we also track based on SHA presence for more reliable detection
    return response.json(), is_create


# =============================================================================
# Display Formatting Functions
# =============================================================================

def format_result_for_display(result: dict, path: str, is_create: bool) -> str:
    """
    Format the API result for human-readable display.
    
    Args:
        result: API response dictionary
        path: File path that was created/updated
        is_create: True if file was created, False if updated
        
    Returns:
        Formatted string with commit info
    """
    lines = []
    
    commit = result.get("commit", {})
    content = result.get("content", {})
    
    # Use the is_create flag to determine action
    # This fixes a bug where we previously used the presence of commit
    # (which is always present for both create and update)
    action = "Created" if is_create else "Updated"
    
    lines.append(f"✅ {action}: {path}")
    lines.append("")
    
    # Commit info
    if commit:
        sha = commit.get("sha", "")[:8]
        message = commit.get("message", "")
        author = commit.get("author", {}).get("name", "Unknown")
        date = commit.get("author", {}).get("date", "")
        
        lines.append(f"📝 Commit: {sha}")
        lines.append(f"   Message: {message}")
        lines.append(f"   Author: {author}")
        if date:
            lines.append(f"   Date: {date}")
    
    # Content info (new file metadata)
    if content:
        new_sha = content.get("sha", "")[:8]
        size = content.get("size", 0)
        html_url = content.get("html_url", "")
        
        lines.append("")
        lines.append(f"📄 File SHA: {new_sha}")
        lines.append(f"   Size: {size:,} bytes")
        if html_url:
            lines.append(f"   View: {html_url}")
    
    return "\n".join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the file writer.
    
    Parses command-line arguments and creates/updates the file.
    """
    parser = argparse.ArgumentParser(
        description="Create or update a file in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new file
  uv run scripts/file_write.py owner/repo \\
      --path docs/new-file.md \\
      --content "# New Document\\n\\nContent here." \\
      --message "Add new document"

  # Update an existing file (SHA required)
  uv run scripts/file_write.py owner/repo \\
      --path README.md \\
      --content "# Updated README" \\
      --message "Update README" \\
      --sha abc123def456...

  # Create file from local file
  uv run scripts/file_write.py owner/repo \\
      --path remote/path.py \\
      --from-file local/path.py \\
      --message "Upload script"

  # Create on specific branch
  uv run scripts/file_write.py owner/repo \\
      --path config.json \\
      --content '{"key": "value"}' \\
      --message "Add config" \\
      --branch develop

  # Create an executable script (with mode)
  uv run scripts/file_write.py owner/repo \\
      --path scripts/build.sh \\
      --from-file build.sh \\
      --message "Add build script" \\
      --mode 755

  # Upload a binary file (image, archive, etc.)
  uv run scripts/file_write.py owner/repo \\
      --path assets/logo.png \\
      --from-file logo.png \\
      --message "Add logo image"
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Required: path in repository
    parser.add_argument(
        "--path", "-p",
        required=True,
        help="Path for the file in the repository"
    )
    
    # Content source (one of these required)
    content_group = parser.add_mutually_exclusive_group(required=True)
    content_group.add_argument(
        "--content", "-c",
        help="File content as a string"
    )
    content_group.add_argument(
        "--from-file", "-f",
        help="Read content from this local file (supports both text and binary files)"
    )
    
    # Required: commit message
    parser.add_argument(
        "--message", "-m",
        required=True,
        help="Commit message"
    )
    
    # Optional: SHA (required for updates to existing files)
    parser.add_argument(
        "--sha",
        help="SHA of file being replaced (required when updating existing file)"
    )
    
    # Optional: target branch
    parser.add_argument(
        "--branch", "-b",
        help="Branch to commit to (default: repo's default branch)"
    )
    
    # Optional: file mode (for creating executable scripts, etc.)
    parser.add_argument(
        "--mode",
        help="File mode to set (e.g., 755 for executable, 644 for regular). "
             "If specified, a second commit will set the file mode after creation."
    )
    
    # Output format
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output commit details as JSON"
    )
    
    args = parser.parse_args()
    
    # Get content from file if specified
    # Use binary mode to support both text and binary files
    if args.from_file:
        try:
            # Read file in binary mode to handle any file type
            # (text files, images, archives, executables, etc.)
            with open(args.from_file, "rb") as f:
                content = f.read()
        except FileNotFoundError:
            print(f"Error: Local file not found: {args.from_file}", file=sys.stderr)
            sys.exit(1)
        except IOError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Content from --content argument is always a string
        content = args.content
    
    # Parse repository
    owner, repo = parse_repo(args.repo)
    
    # Get token and create/update file
    token = get_token()
    
    # Determine branch (need it for mode setting)
    branch = args.branch
    if branch is None and args.mode:
        # We need to know the branch for mode setting
        branch = get_default_branch(token, owner, repo)
    
    result, is_create = create_or_update_file(
        token, owner, repo,
        path=args.path,
        content=content,
        message=args.message,
        sha=args.sha,
        branch=branch,
    )
    
    # If mode was specified, set it in a second commit
    mode_commit_sha = None
    if args.mode:
        # Determine the branch (use what we passed or get from result)
        if branch is None:
            branch = get_default_branch(token, owner, repo)
        
        mode_commit_sha = set_file_mode(
            token, owner, repo,
            path=args.path,
            mode=args.mode,
            branch=branch,
        )
    
    # Output results
    if args.json:
        output = result
        if mode_commit_sha:
            output["mode_commit"] = mode_commit_sha
            output["mode_set"] = args.mode
        print(json.dumps(output, indent=2))
    else:
        display = format_result_for_display(result, args.path, is_create)
        print(display)
        
        # Add mode information if set
        if mode_commit_sha:
            try:
                git_mode = user_mode_to_git_mode(args.mode)
                mode_display = git_mode_to_display(git_mode)
            except ValueError:
                mode_display = args.mode
            print(f"\n🔧 Mode set to {mode_display}")
            print(f"   Commit: {mode_commit_sha[:8]}")


if __name__ == "__main__":
    main()
