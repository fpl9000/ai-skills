#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28.0",
# ]
# ///
"""
GitHub API Common Utilities
===========================
Shared functions used across all GitHub skill scripts.

This module provides:
- Token retrieval from environment
- HTTP header construction with explicit API versioning
- Repository string parsing
- Common API request helpers

Centralizing these functions:
1. Reduces code duplication across scripts
2. Makes API versioning updates a single-file change
3. Ensures consistent error handling patterns

API Versioning:
    Uses explicit GitHub API versioning (2022-11-28) via the
    X-GitHub-Api-Version header for long-term stability.
    See: https://docs.github.com/en/rest/about-the-rest-api/api-versions
"""

import os
import sys
import time
import random
from typing import Optional, Tuple

import requests


# =============================================================================
# Constants
# =============================================================================

# GitHub API base URL - all API requests go through this endpoint
API_BASE = "https://api.github.com"

# Explicit API version for stability
# GitHub supports versions for 24+ months after a new version releases
# See: https://docs.github.com/en/rest/about-the-rest-api/api-versions
API_VERSION = "2022-11-28"


# =============================================================================
# Authentication Functions
# =============================================================================

def get_token() -> str:
    """
    Retrieve GitHub token from environment variable.
    
    The token is expected in the GITHUB_TOKEN environment variable.
    This function will exit with an error message if the token is not set,
    providing guidance on how to create one.
    
    Returns:
        str: The GitHub Personal Access Token
        
    Exits:
        Exits with code 1 if GITHUB_TOKEN is not set
    """
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set", file=sys.stderr)
        print("Create a token at: https://github.com/settings/tokens", file=sys.stderr)
        sys.exit(1)
    
    return token


# =============================================================================
# HTTP Header Functions
# =============================================================================

def get_headers(token: str) -> dict:
    """
    Build HTTP headers for GitHub API requests.
    
    Uses explicit API versioning for long-term stability. The headers include:
    - Authorization: Bearer token for authentication
    - Accept: GitHub's recommended JSON media type
    - X-GitHub-Api-Version: Explicit version pinning (2022-11-28)
    - User-Agent: Required by GitHub API
    
    Args:
        token: GitHub Personal Access Token
        
    Returns:
        Dictionary of headers for use with requests library
    """
    return {
        "Authorization": f"token {token}",
        # Updated media type per GitHub's current recommendations
        "Accept": "application/vnd.github+json",
        # Explicit API versioning for stability
        # This ensures consistent behavior even if GitHub releases new versions
        "X-GitHub-Api-Version": API_VERSION,
        # User-Agent is required by GitHub API
        "User-Agent": "github-skill-script",
    }


# =============================================================================
# Repository Parsing Functions
# =============================================================================

def parse_repo(repo_string: str) -> Tuple[str, str]:
    """
    Parse owner/repo string into components.
    
    GitHub repositories are commonly referenced as "owner/repo" (e.g.,
    "octocat/hello-world"). This function splits that format into its
    component parts.
    
    Args:
        repo_string: Repository in "owner/repo" format
        
    Returns:
        Tuple of (owner, repo) strings
        
    Exits:
        Exits with code 1 if the format is invalid
    """
    parts = repo_string.split("/")
    
    if len(parts) != 2:
        print(f"Error: Invalid repository format '{repo_string}'", file=sys.stderr)
        print("Expected format: owner/repo (e.g., octocat/hello-world)", file=sys.stderr)
        sys.exit(1)
    
    return parts[0], parts[1]


# =============================================================================
# API Request Helpers
# =============================================================================

def make_request_with_retry(
    method: str,
    url: str,
    headers: dict,
    max_retries: int = 3,
    **kwargs
) -> requests.Response:
    """
    Make an HTTP request with retry logic for rate limits and transient errors.
    
    Implements exponential backoff with jitter to handle:
    - GitHub API rate limits (403 with rate limit message)
    - Transient server errors (5xx status codes)
    
    The retry strategy uses exponential backoff (2^attempt seconds) with
    random jitter to prevent thundering herd problems.
    
    Args:
        method: HTTP method ('get', 'post', 'put', 'delete', 'patch')
        url: Full URL to request
        headers: HTTP headers dictionary
        max_retries: Maximum number of retry attempts (default: 3)
        **kwargs: Additional arguments passed to requests (json, params, etc.)
        
    Returns:
        requests.Response object from the final attempt
        
    Note:
        This function does NOT raise exceptions for HTTP errors.
        The caller should check response.status_code.
    """
    # Map method names to requests functions
    request_methods = {
        'get': requests.get,
        'post': requests.post,
        'put': requests.put,
        'delete': requests.delete,
        'patch': requests.patch,
    }
    
    request_func = request_methods.get(method.lower())
    if not request_func:
        raise ValueError(f"Unsupported HTTP method: {method}")
    
    response = None
    
    for attempt in range(max_retries):
        response = request_func(url, headers=headers, **kwargs)
        
        # Check for rate limit response (403 with specific message)
        if response.status_code == 403:
            response_text = response.text.lower()
            if 'rate limit' in response_text or 'abuse' in response_text:
                # Try to get retry delay from headers
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    sleep_time = int(retry_after)
                else:
                    # Use X-RateLimit-Reset if available
                    reset_time = response.headers.get('X-RateLimit-Reset')
                    if reset_time:
                        sleep_time = max(0, int(reset_time) - int(time.time()))
                    else:
                        # Default exponential backoff
                        sleep_time = (2 ** attempt) * 60
                
                # Add jitter and cap at 5 minutes
                jitter = random.uniform(0, 5)
                sleep_time = min(sleep_time + jitter, 300)
                
                if attempt < max_retries - 1:
                    print(f"Rate limited. Waiting {sleep_time:.1f}s before retry...", 
                          file=sys.stderr)
                    time.sleep(sleep_time)
                    continue
        
        # Retry on server errors (5xx)
        if response.status_code >= 500 and attempt < max_retries - 1:
            # Exponential backoff with jitter
            sleep_time = (2 ** attempt) + random.uniform(0, 1)
            print(f"Server error {response.status_code}. Retrying in {sleep_time:.1f}s...",
                  file=sys.stderr)
            time.sleep(sleep_time)
            continue
        
        # Success or non-retryable error - return response
        break
    
    return response


def handle_api_error(response: requests.Response, context: str = "") -> None:
    """
    Handle common GitHub API errors with helpful messages.
    
    This function checks for common error conditions and prints
    appropriate error messages before exiting.
    
    Args:
        response: The requests.Response object to check
        context: Optional context string for error messages (e.g., "repository")
        
    Exits:
        Exits with code 1 if the response indicates an error
    """
    if response.status_code >= 200 and response.status_code < 300:
        return  # Success - no error
    
    try:
        error_data = response.json()
        error_msg = error_data.get("message", "Unknown error")
        errors = error_data.get("errors", [])
    except (ValueError, KeyError):
        error_msg = response.text or "Unknown error"
        errors = []
    
    # Handle specific status codes with helpful messages
    if response.status_code == 401:
        print("Error: Authentication failed (401 Unauthorized)", file=sys.stderr)
        print("Check that your GITHUB_TOKEN is valid and not expired", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 403:
        print(f"Error: Access forbidden (403)", file=sys.stderr)
        if 'rate limit' in error_msg.lower():
            print("You have exceeded the GitHub API rate limit", file=sys.stderr)
            reset_time = response.headers.get('X-RateLimit-Reset')
            if reset_time:
                print(f"Rate limit resets at: {time.ctime(int(reset_time))}", 
                      file=sys.stderr)
        else:
            print(f"Message: {error_msg}", file=sys.stderr)
            print("Your token may lack the required scopes", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 404:
        print(f"Error: {context or 'Resource'} not found (404)", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 409:
        print("Error: Conflict (409)", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        print("This often means a SHA mismatch - the resource was modified", 
              file=sys.stderr)
        sys.exit(1)
        
    elif response.status_code == 422:
        print(f"Error: Validation failed (422)", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        for err in errors:
            if isinstance(err, dict):
                field = err.get('field', 'unknown')
                code = err.get('code', 'unknown')
                print(f"  - Field '{field}': {code}", file=sys.stderr)
            else:
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
        
    else:
        print(f"Error: GitHub API returned {response.status_code}", file=sys.stderr)
        print(f"Message: {error_msg}", file=sys.stderr)
        sys.exit(1)


def get_default_branch(token: str, owner: str, repo: str) -> str:
    """
    Get the default branch of a repository.
    
    Queries the repository metadata to find the default branch name
    (typically 'main' or 'master').
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        
    Returns:
        Name of the default branch (e.g., 'main')
        
    Exits:
        Exits with code 1 if the repository is not found or on API error
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}"
    
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Repository {owner}/{repo}")
    
    return response.json().get("default_branch", "main")


def get_ref_sha(token: str, owner: str, repo: str, ref: str) -> str:
    """
    Get the SHA for a git reference (branch, tag, or commit).
    
    This resolves a reference name to its commit SHA, which is needed
    for operations like creating branches.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        ref: Git reference (branch name, tag, or commit SHA)
        
    Returns:
        The 40-character commit SHA
        
    Exits:
        Exits with code 1 if the reference is not found
    """
    headers = get_headers(token)
    
    # Try as a branch first
    url = f"{API_BASE}/repos/{owner}/{repo}/git/ref/heads/{ref}"
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 200:
        return response.json()["object"]["sha"]
    
    # Try as a tag
    url = f"{API_BASE}/repos/{owner}/{repo}/git/ref/tags/{ref}"
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 200:
        return response.json()["object"]["sha"]
    
    # Try as a commit SHA directly
    url = f"{API_BASE}/repos/{owner}/{repo}/commits/{ref}"
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 200:
        return response.json()["sha"]
    
    # Not found
    print(f"Error: Reference '{ref}' not found", file=sys.stderr)
    print("It should be a branch name, tag, or commit SHA", file=sys.stderr)
    sys.exit(1)


# =============================================================================
# Git Data API Functions (for tree manipulation / file modes)
# =============================================================================

def get_branch_head_sha(token: str, owner: str, repo: str, branch: str) -> str:
    """
    Get the commit SHA that a branch currently points to.
    
    This is the first step in the Git Data API workflow for modifying
    file modes, as we need to know the current commit to build on.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        branch: Branch name (e.g., 'main', 'develop')
        
    Returns:
        The 40-character commit SHA the branch points to
        
    Exits:
        Exits with code 1 if the branch is not found
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/git/ref/heads/{branch}"
    
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 404:
        print(f"Error: Branch '{branch}' not found in {owner}/{repo}", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Branch {branch}")
    
    return response.json()["object"]["sha"]


def get_commit_tree_sha(token: str, owner: str, repo: str, commit_sha: str) -> str:
    """
    Get the tree SHA from a commit.
    
    Every Git commit points to a tree object that represents the state
    of all files at that point. We need the tree SHA to read or modify
    the file structure.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        commit_sha: The commit SHA to get the tree from
        
    Returns:
        The 40-character tree SHA
        
    Exits:
        Exits with code 1 if the commit is not found
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/git/commits/{commit_sha}"
    
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 404:
        print(f"Error: Commit '{commit_sha[:8]}' not found", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Commit {commit_sha[:8]}")
    
    return response.json()["tree"]["sha"]


def get_tree_recursive(
    token: str,
    owner: str,
    repo: str,
    tree_sha: str
) -> list[dict]:
    """
    Get all entries in a tree recursively.
    
    Returns the full tree structure including all nested directories
    and files. Each entry includes path, mode, type, sha, and size.
    
    Git tree entry modes:
    - 100644: Regular file (non-executable)
    - 100755: Executable file
    - 120000: Symbolic link
    - 040000: Subdirectory (tree)
    - 160000: Submodule (commit reference)
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        tree_sha: The tree SHA to retrieve
        
    Returns:
        List of tree entry dictionaries with keys:
        - path: File path relative to repo root
        - mode: Git mode string (e.g., "100644")
        - type: "blob" for files, "tree" for directories
        - sha: SHA of the blob/tree
        - size: File size in bytes (only for blobs)
        
    Exits:
        Exits with code 1 if the tree is not found or truncated
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1"
    
    response = make_request_with_retry('get', url, headers)
    
    if response.status_code == 404:
        print(f"Error: Tree '{tree_sha[:8]}' not found", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Tree {tree_sha[:8]}")
    
    data = response.json()
    
    # Check if tree was truncated (very large repos)
    if data.get("truncated", False):
        print("Warning: Tree was truncated due to size", file=sys.stderr)
        print("Some files may not be included in the listing", file=sys.stderr)
    
    return data.get("tree", [])


def create_tree_with_changes(
    token: str,
    owner: str,
    repo: str,
    base_tree_sha: str,
    changes: list[dict]
) -> str:
    """
    Create a new tree with specified changes.
    
    This creates a new tree object based on an existing tree, with
    modifications applied. The changes can include mode changes,
    content changes, or file deletions.
    
    Each change dict should have:
    - path: File path (required)
    - mode: New mode string, e.g., "100755" (required for mode changes)
    - type: "blob" for files (required)
    - sha: Blob SHA (use existing SHA for mode-only changes, or
           null/omit to delete the file)
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        base_tree_sha: SHA of the tree to base changes on
        changes: List of change dictionaries
        
    Returns:
        SHA of the newly created tree
        
    Exits:
        Exits with code 1 on API error
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/git/trees"
    
    body = {
        "base_tree": base_tree_sha,
        "tree": changes,
    }
    
    response = make_request_with_retry('post', url, headers, json=body)
    
    if response.status_code == 404:
        print(f"Error: Repository {owner}/{repo} not found", file=sys.stderr)
        sys.exit(1)
    
    if response.status_code == 422:
        error_data = response.json()
        error_msg = error_data.get("message", "Validation failed")
        print(f"Error creating tree: {error_msg}", file=sys.stderr)
        
        # Check for specific path errors
        errors = error_data.get("errors", [])
        for err in errors:
            if isinstance(err, dict):
                print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, "Tree creation")
    
    return response.json()["sha"]


def create_commit(
    token: str,
    owner: str,
    repo: str,
    tree_sha: str,
    parent_sha: str,
    message: str
) -> str:
    """
    Create a new commit pointing to a tree.
    
    This creates a commit object with the specified tree and parent.
    The commit is not yet attached to any branch - use update_branch_ref
    to make a branch point to this commit.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        tree_sha: SHA of the tree this commit points to
        parent_sha: SHA of the parent commit
        message: Commit message
        
    Returns:
        SHA of the newly created commit
        
    Exits:
        Exits with code 1 on API error
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/git/commits"
    
    body = {
        "message": message,
        "tree": tree_sha,
        "parents": [parent_sha],
    }
    
    response = make_request_with_retry('post', url, headers, json=body)
    
    handle_api_error(response, "Commit creation")
    
    return response.json()["sha"]


def update_branch_ref(
    token: str,
    owner: str,
    repo: str,
    branch: str,
    commit_sha: str,
    force: bool = False
) -> None:
    """
    Update a branch to point to a new commit.
    
    This is the final step in a Git Data API workflow - after creating
    a new tree and commit, we update the branch reference to point to
    the new commit.
    
    Args:
        token: GitHub Personal Access Token
        owner: Repository owner
        repo: Repository name
        branch: Branch name to update
        commit_sha: SHA of the commit the branch should point to
        force: If True, force update even if not fast-forward
        
    Exits:
        Exits with code 1 on API error
    """
    headers = get_headers(token)
    url = f"{API_BASE}/repos/{owner}/{repo}/git/refs/heads/{branch}"
    
    body = {
        "sha": commit_sha,
        "force": force,
    }
    
    response = make_request_with_retry('patch', url, headers, json=body)
    
    if response.status_code == 422:
        error_msg = response.json().get("message", "Update failed")
        print(f"Error updating branch: {error_msg}", file=sys.stderr)
        if "fast-forward" in error_msg.lower():
            print("The branch has been modified since you read it", file=sys.stderr)
            print("Use --force to overwrite (dangerous!)", file=sys.stderr)
        sys.exit(1)
    
    handle_api_error(response, f"Branch update for {branch}")


def user_mode_to_git_mode(user_mode: str) -> str:
    """
    Convert user-friendly mode (e.g., '755') to Git mode (e.g., '100755').
    
    Git stores file modes with a type prefix:
    - 100644: Regular file (non-executable)
    - 100755: Executable file
    - 120000: Symbolic link
    - 040000: Subdirectory
    - 160000: Submodule
    
    This function handles the common case of regular files (100xxx).
    For special modes (symlinks, etc.), the user should provide the
    full 6-digit mode.
    
    Args:
        user_mode: Mode string, either 3-digit (e.g., '755', '644')
                   or full 6-digit (e.g., '100755', '120000')
                   
    Returns:
        Full 6-digit Git mode string
        
    Raises:
        ValueError: If the mode format is invalid
    """
    # Remove any leading zeros for consistent handling
    user_mode = user_mode.lstrip('0') or '0'
    
    # If it's already a full mode (starts with 1, 0, or 16 for submodules)
    if len(user_mode) == 6 and user_mode[0] in ('1', '0'):
        return user_mode
    
    # Handle 3-digit modes (common case)
    if len(user_mode) <= 3:
        # Pad to 3 digits
        mode_3digit = user_mode.zfill(3)
        
        # Validate it's a valid permission octal
        try:
            mode_int = int(mode_3digit, 8)
            if mode_int < 0 or mode_int > 0o777:
                raise ValueError(f"Invalid mode: {user_mode}")
        except ValueError:
            raise ValueError(f"Invalid octal mode: {user_mode}")
        
        # Prepend regular file prefix
        return f"100{mode_3digit}"
    
    raise ValueError(
        f"Invalid mode format: {user_mode}. "
        "Use 3-digit (e.g., '755') or 6-digit (e.g., '100755')"
    )


def git_mode_to_display(git_mode: str) -> str:
    """
    Convert Git mode to human-readable display format.
    
    Args:
        git_mode: Full 6-digit Git mode (e.g., '100755')
        
    Returns:
        Human-readable string (e.g., '755 (executable)')
    """
    mode_map = {
        "100644": "644 (regular file)",
        "100755": "755 (executable)",
        "120000": "symlink",
        "040000": "directory",
        "160000": "submodule",
    }
    
    if git_mode in mode_map:
        return mode_map[git_mode]
    
    # Unknown mode - just show it
    return git_mode


# =============================================================================
# Output Formatting Helpers
# =============================================================================

def format_size(size_bytes: int) -> str:
    """
    Format a byte size as a human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 KB", "2.3 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
