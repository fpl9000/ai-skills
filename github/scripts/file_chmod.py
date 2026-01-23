#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub File Mode Changer
========================
Change file permissions (mode) for files in a GitHub repository.

This script uses the GitHub Git Data API to modify file modes, which is
necessary because the Contents API doesn't support setting file modes.

The workflow is:
1. Get current branch commit SHA
2. Get the tree from that commit
3. Find the files and verify they exist
4. Create a new tree with modified modes
5. Create a new commit pointing to the new tree
6. Update the branch reference to the new commit

Usage:
    # Make a single file executable
    uv run scripts/file_chmod.py owner/repo --path script.py --mode 755

    # Make multiple files executable in one commit
    uv run scripts/file_chmod.py owner/repo \\
        --path scripts/build.sh \\
        --path scripts/deploy.sh \\
        --path scripts/test.py \\
        --mode 755

    # Remove executable bit
    uv run scripts/file_chmod.py owner/repo --path script.py --mode 644

    # On a specific branch
    uv run scripts/file_chmod.py owner/repo --path script.py --mode 755 --branch develop

    # With custom commit message
    uv run scripts/file_chmod.py owner/repo \\
        --path script.py \\
        --mode 755 \\
        --message "Make script executable"

Common modes:
    755 - Executable (rwxr-xr-x)
    644 - Regular file (rw-r--r--)

Environment Variables Required:
    GITHUB_TOKEN - Your GitHub Personal Access Token
"""

import argparse
import json
import sys

# Import shared utilities from the common module
from github_common import (
    get_token,
    get_headers,
    parse_repo,
    get_branch_head_sha,
    get_commit_tree_sha,
    get_tree_recursive,
    create_tree_with_changes,
    create_commit,
    update_branch_ref,
    user_mode_to_git_mode,
    git_mode_to_display,
)


# =============================================================================
# Core Functions
# =============================================================================

def find_files_in_tree(tree_entries: list[dict], paths: list[str]) -> dict:
    """
    Find specific files in a tree and return their current metadata.
    
    Args:
        tree_entries: List of tree entries from get_tree_recursive()
        paths: List of file paths to find
        
    Returns:
        Dictionary mapping path -> entry dict (with mode, sha, type)
        Missing files will not be in the returned dict
    """
    # Build a quick lookup by path
    tree_by_path = {entry["path"]: entry for entry in tree_entries}
    
    found = {}
    for path in paths:
        # Normalize path (remove leading/trailing slashes)
        normalized = path.strip("/")
        if normalized in tree_by_path:
            found[normalized] = tree_by_path[normalized]
    
    return found


def change_file_modes(
    token: str,
    owner: str,
    repo: str,
    paths: list[str],
    mode: str,
    branch: str,
    message: str = None,
) -> dict:
    """
    Change the mode of one or more files in a single commit.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        paths: List of file paths to change
        mode: Target mode (user format like '755' or git format like '100755')
        branch: Branch to commit to
        message: Commit message (auto-generated if not provided)
        
    Returns:
        Dictionary with results:
        - commit_sha: New commit SHA
        - changed: List of files that were changed
        - skipped: List of files that already had the target mode
        - not_found: List of files that don't exist
        
    Exits:
        Exits with code 1 on API errors
    """
    # Convert user mode to git mode
    try:
        git_mode = user_mode_to_git_mode(mode)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Step 1: Get current branch head
    head_sha = get_branch_head_sha(token, owner, repo, branch)
    
    # Step 2: Get tree SHA from the commit
    tree_sha = get_commit_tree_sha(token, owner, repo, head_sha)
    
    # Step 3: Get full tree to find files
    tree_entries = get_tree_recursive(token, owner, repo, tree_sha)
    
    # Step 4: Find the requested files
    found_files = find_files_in_tree(tree_entries, paths)
    
    # Categorize files
    changed = []
    skipped = []
    not_found = []
    
    # Normalize paths for consistent comparison
    normalized_paths = [p.strip("/") for p in paths]
    
    for path in normalized_paths:
        if path not in found_files:
            not_found.append(path)
        elif found_files[path]["type"] != "blob":
            # Can't chmod directories or submodules
            print(f"Warning: '{path}' is not a file (type: {found_files[path]['type']}), skipping",
                  file=sys.stderr)
            skipped.append(path)
        elif found_files[path]["mode"] == git_mode:
            # Already has target mode
            skipped.append(path)
        else:
            changed.append(path)
    
    # Report not found files
    if not_found:
        print(f"Error: The following files were not found:", file=sys.stderr)
        for path in not_found:
            print(f"  - {path}", file=sys.stderr)
        sys.exit(1)
    
    # Report skipped files (already correct mode)
    if skipped:
        for path in skipped:
            if path in found_files and found_files[path]["mode"] == git_mode:
                print(f"Warning: '{path}' already has mode {git_mode_to_display(git_mode)}",
                      file=sys.stderr)
    
    # If nothing to change, exit early
    if not changed:
        return {
            "commit_sha": None,
            "changed": [],
            "skipped": skipped,
            "not_found": not_found,
        }
    
    # Step 5: Build tree changes
    tree_changes = []
    for path in changed:
        file_entry = found_files[path]
        tree_changes.append({
            "path": path,
            "mode": git_mode,
            "type": "blob",
            "sha": file_entry["sha"],  # Keep same content, just change mode
        })
    
    # Step 6: Create new tree
    new_tree_sha = create_tree_with_changes(token, owner, repo, tree_sha, tree_changes)
    
    # Step 7: Create commit
    if message is None:
        # Auto-generate message
        mode_display = git_mode[-3:]  # Just the permission bits
        if len(changed) == 1:
            message = f"Change mode to {mode_display}: {changed[0]}"
        else:
            file_list = ", ".join(changed[:3])
            if len(changed) > 3:
                file_list += f", ... ({len(changed)} files total)"
            message = f"Change mode to {mode_display}: {file_list}"
    
    new_commit_sha = create_commit(token, owner, repo, new_tree_sha, head_sha, message)
    
    # Step 8: Update branch ref
    update_branch_ref(token, owner, repo, branch, new_commit_sha)
    
    return {
        "commit_sha": new_commit_sha,
        "changed": changed,
        "skipped": skipped,
        "not_found": not_found,
    }


# =============================================================================
# Display Formatting
# =============================================================================

def format_result_for_display(result: dict, owner: str, repo: str, mode: str, branch: str) -> str:
    """
    Format the result for human-readable display.
    
    Args:
        result: Result dictionary from change_file_modes()
        owner: Repository owner
        repo: Repository name
        mode: Target mode (user format)
        branch: Branch name
        
    Returns:
        Formatted string
    """
    lines = []
    
    try:
        git_mode = user_mode_to_git_mode(mode)
        mode_display = git_mode_to_display(git_mode)
    except ValueError:
        mode_display = mode
    
    if result["changed"]:
        lines.append(f"✅ Changed {len(result['changed'])} file(s) to mode {mode_display}")
        lines.append("")
        
        for path in result["changed"]:
            lines.append(f"   • {path}")
        
        lines.append("")
        lines.append(f"📝 Commit: {result['commit_sha'][:8]}")
        lines.append(f"   Branch: {branch}")
        lines.append(f"   View: https://github.com/{owner}/{repo}/commit/{result['commit_sha']}")
    else:
        lines.append("ℹ️  No changes needed")
    
    if result["skipped"]:
        lines.append("")
        lines.append(f"⏭️  Skipped {len(result['skipped'])} file(s) (already had target mode):")
        for path in result["skipped"]:
            lines.append(f"   • {path}")
    
    return "\n".join(lines)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """
    Main entry point for the file mode changer.
    
    Parses command-line arguments and changes file modes.
    """
    parser = argparse.ArgumentParser(
        description="Change file mode/permissions in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Make a script executable
  uv run scripts/file_chmod.py owner/repo --path script.py --mode 755

  # Make multiple files executable in one commit
  uv run scripts/file_chmod.py owner/repo \\
      --path build.sh \\
      --path deploy.sh \\
      --mode 755

  # Remove executable bit
  uv run scripts/file_chmod.py owner/repo --path script.py --mode 644

  # On a specific branch with custom message
  uv run scripts/file_chmod.py owner/repo \\
      --path scripts/run.py \\
      --mode 755 \\
      --branch develop \\
      --message "Make run.py executable"

Common modes:
  755 - Executable file (rwxr-xr-x)
  644 - Regular file (rw-r--r--)
        """
    )
    
    # Required: repository
    parser.add_argument(
        "repo",
        help="Repository in owner/repo format"
    )
    
    # Required: path(s) - can be specified multiple times
    parser.add_argument(
        "--path", "-p",
        action="append",
        required=True,
        dest="paths",
        help="Path to file (can be specified multiple times)"
    )
    
    # Required: target mode
    parser.add_argument(
        "--mode", "-m",
        required=True,
        help="Target mode (e.g., 755 for executable, 644 for regular)"
    )
    
    # Optional: branch
    parser.add_argument(
        "--branch", "-b",
        default="main",
        help="Branch to commit to (default: main)"
    )
    
    # Optional: commit message
    parser.add_argument(
        "--message",
        help="Commit message (auto-generated if not provided)"
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
    
    # Get token and change modes
    token = get_token()
    result = change_file_modes(
        token, owner, repo,
        paths=args.paths,
        mode=args.mode,
        branch=args.branch,
        message=args.message,
    )
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result_for_display(result, owner, repo, args.mode, args.branch))


if __name__ == "__main__":
    main()
