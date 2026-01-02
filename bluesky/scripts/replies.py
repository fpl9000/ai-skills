#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Replies Script
======================
Fetches and displays the reply thread for a specific Bluesky post.

Accepts either an AT Protocol URI or a Bluesky web URL as input.

Usage:
    # Using a web URL (most common)
    uv run scripts/replies.py https://bsky.app/profile/handle/post/rkey

    # Using an AT Protocol URI
    uv run scripts/replies.py "at://did:plc:xxx/app.bsky.feed.post/rkey"

    # Limit reply depth
    uv run scripts/replies.py --depth 2 https://bsky.app/profile/handle/post/rkey

    # JSON output for processing
    uv run scripts/replies.py --json https://bsky.app/profile/handle/post/rkey

    # Skip parent posts, show only target post and its replies
    uv run scripts/replies.py --no-parents https://bsky.app/profile/handle/post/rkey

Environment Variables Required:
    BLUESKY_HANDLE   - Your Bluesky handle (e.g., yourname.bsky.social)
    BLUESKY_PASSWORD - Your Bluesky app password (create in Settings > App Passwords)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime


def get_credentials():
    """
    Retrieve Bluesky credentials from environment variables.
    
    Returns a tuple of (handle, password) if both are set.
    Exits with an error message if either is missing.
    """
    # Get the handle from the environment
    handle = os.environ.get("BLUESKY_HANDLE")
    
    # Get the password from the environment
    # IMPORTANT: Use an App Password, not your main account password
    password = os.environ.get("BLUESKY_PASSWORD")
    
    # Validate that both credentials are present
    if not handle:
        print("Error: BLUESKY_HANDLE environment variable not set", file=sys.stderr)
        print("Set it to your Bluesky handle (e.g., yourname.bsky.social)", file=sys.stderr)
        sys.exit(1)
        
    if not password:
        print("Error: BLUESKY_PASSWORD environment variable not set", file=sys.stderr)
        print("Set it to your Bluesky App Password (create in Settings > App Passwords)", file=sys.stderr)
        sys.exit(1)
    
    return handle, password


def create_client_and_login(handle: str, password: str):
    """
    Create an authenticated Bluesky client.
    
    The atproto library handles session management automatically,
    including token refresh when needed.
    
    Args:
        handle: Your Bluesky handle (e.g., yourname.bsky.social)
        password: Your Bluesky app password
        
    Returns:
        An authenticated Client instance
    """
    # Import the Client class from the atproto library
    from atproto import Client
    
    # Create a new client instance
    client = Client()
    
    # Authenticate with the provided credentials
    client.login(handle, password)
    
    return client


def parse_post_identifier(client, identifier: str) -> str:
    """
    Parse a post identifier and return a valid AT Protocol URI.
    
    Accepts two formats:
    1. AT Protocol URI: at://did:plc:xxx/app.bsky.feed.post/rkey
    2. Web URL: https://bsky.app/profile/handle/post/rkey
    
    For web URLs, this function resolves the handle to a DID
    and constructs the proper AT URI.
    
    Args:
        client: An authenticated Client instance (needed for handle resolution)
        identifier: Either an AT URI or a Bluesky web URL
        
    Returns:
        A valid AT Protocol URI for the post
    """
    # Check if it's already an AT Protocol URI
    if identifier.startswith("at://"):
        return identifier
    
    # Try to parse as a Bluesky web URL
    # Format: https://bsky.app/profile/{handle}/post/{rkey}
    web_url_pattern = r"https?://bsky\.app/profile/([^/]+)/post/([^/]+)"
    match = re.match(web_url_pattern, identifier)
    
    if match:
        # Extract handle and record key from the URL
        handle = match.group(1)
        rkey = match.group(2)
        
        # Resolve the handle to a DID
        # The handle could already be a DID (did:plc:xxx format)
        if handle.startswith("did:"):
            did = handle
        else:
            # Use the client to resolve the handle to a DID
            # This makes an API call to the identity resolution service
            resolved = client.resolve_handle(handle)
            did = resolved.did
        
        # Construct and return the AT Protocol URI
        return f"at://{did}/app.bsky.feed.post/{rkey}"
    
    # If we get here, the identifier format is not recognized
    print(f"Error: Unrecognized post identifier format: {identifier}", file=sys.stderr)
    print("Expected either:", file=sys.stderr)
    print("  - AT URI: at://did:plc:xxx/app.bsky.feed.post/rkey", file=sys.stderr)
    print("  - Web URL: https://bsky.app/profile/handle/post/rkey", file=sys.stderr)
    sys.exit(1)


def fetch_thread(client, uri: str, depth: int = None):
    """
    Fetch the thread for a post, including parent posts and replies.
    
    Uses the app.bsky.feed.getPostThread endpoint from the AT Protocol.
    
    Args:
        client: An authenticated Client instance
        uri: The AT Protocol URI of the post
        depth: Maximum depth of replies to fetch (None for default)
        
    Returns:
        The thread response from the API
    """
    # Build the parameters for the API call
    params = {"uri": uri}
    
    # Add depth parameter if specified
    # The API accepts depth as an integer controlling reply depth
    if depth is not None:
        params["depth"] = depth
    
    # Call the getPostThread endpoint
    # This returns the post, its parents (if any), and its replies
    response = client.app.bsky.feed.get_post_thread(params)
    
    return response


def format_timestamp(iso_timestamp: str) -> str:
    """
    Format an ISO timestamp into a human-readable string.
    
    Args:
        iso_timestamp: An ISO 8601 formatted timestamp string
        
    Returns:
        A formatted date/time string (e.g., "2024-01-15 14:30")
    """
    try:
        # Parse the ISO timestamp
        # Handle both 'Z' suffix and timezone offset formats
        timestamp = iso_timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp)
        
        # Format as a readable string
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        # If parsing fails, return the original string
        return iso_timestamp


def format_post(post_view, indent: int = 0) -> str:
    """
    Format a single post for human-readable display.
    
    Args:
        post_view: A PostView object from the API response
        indent: Number of spaces to indent (for nested replies)
        
    Returns:
        A formatted string representation of the post
    """
    # Build the indent prefix
    prefix = "  " * indent
    
    # Extract post details from the PostView object
    author = post_view.author
    record = post_view.record
    
    # Get author display name and handle
    display_name = author.display_name or author.handle
    handle = author.handle
    
    # Get the post text
    text = record.text if hasattr(record, 'text') else "[no text]"
    
    # Get and format the timestamp
    created_at = record.created_at if hasattr(record, 'created_at') else ""
    timestamp = format_timestamp(created_at)
    
    # Get engagement stats
    like_count = post_view.like_count or 0
    reply_count = post_view.reply_count or 0
    repost_count = post_view.repost_count or 0
    
    # Build the formatted output
    lines = [
        f"{prefix}┌─ {display_name} (@{handle}) · {timestamp}",
        f"{prefix}│  {text}",
        f"{prefix}│  ♡ {like_count}  ↺ {repost_count}  💬 {reply_count}",
        f"{prefix}└─"
    ]
    
    # Handle multi-line post text by indenting continuation lines
    if "\n" in text:
        text_lines = text.split("\n")
        lines = [
            f"{prefix}┌─ {display_name} (@{handle}) · {timestamp}",
        ]
        for text_line in text_lines:
            lines.append(f"{prefix}│  {text_line}")
        lines.extend([
            f"{prefix}│  ♡ {like_count}  ↺ {repost_count}  💬 {reply_count}",
            f"{prefix}└─"
        ])
    
    return "\n".join(lines)


def print_thread(thread, indent: int = 0, max_depth: int = None, current_depth: int = 0):
    """
    Recursively print a thread with replies.
    
    This function walks the thread tree, printing each post
    with appropriate indentation to show the reply hierarchy.
    
    Args:
        thread: A ThreadViewPost object from the API
        indent: Current indentation level
        max_depth: Maximum depth to display (None for unlimited)
        current_depth: Current depth in the reply tree
    """
    # Check if we've reached the maximum depth
    if max_depth is not None and current_depth > max_depth:
        return
    
    # Check if this is a valid thread view (not blocked, not found, etc.)
    # The thread can be a ThreadViewPost, NotFoundPost, or BlockedPost
    thread_type = getattr(thread, 'py_type', None)
    
    if thread_type == 'app.bsky.feed.defs#notFoundPost':
        print(f"{'  ' * indent}[Post not found]")
        return
    
    if thread_type == 'app.bsky.feed.defs#blockedPost':
        print(f"{'  ' * indent}[Blocked post]")
        return
    
    # Get the post from the thread
    # ThreadViewPost has a 'post' attribute containing the PostView
    post = getattr(thread, 'post', None)
    
    if post is None:
        # Fallback: try to access as if thread itself is the post
        print(f"{'  ' * indent}[Unable to display post]")
        return
    
    # Print this post
    print(format_post(post, indent))
    print()  # Add blank line between posts
    
    # Get and print replies
    replies = getattr(thread, 'replies', None) or []
    
    for reply in replies:
        # Recursively print each reply with increased indentation
        print_thread(reply, indent + 1, max_depth, current_depth + 1)


def print_parents(thread, show_parents: bool = True):
    """
    Print parent posts leading up to the main post.
    
    This walks up the parent chain and prints posts from
    oldest to newest (root to target).
    
    Args:
        thread: The ThreadViewPost for the target post
        show_parents: Whether to show parent posts
    """
    if not show_parents:
        return
    
    # Collect parents into a list (they're linked newest-to-oldest)
    parents = []
    parent = getattr(thread, 'parent', None)
    
    while parent is not None:
        # Check parent type - could be ThreadViewPost, NotFoundPost, etc.
        parent_type = getattr(parent, 'py_type', None)
        
        if parent_type == 'app.bsky.feed.defs#notFoundPost':
            parents.append(("[Parent not found]", None))
            break
        elif parent_type == 'app.bsky.feed.defs#blockedPost':
            parents.append(("[Blocked parent]", None))
            break
        else:
            # It's a ThreadViewPost
            post = getattr(parent, 'post', None)
            if post:
                parents.append((None, parent))
            parent = getattr(parent, 'parent', None)
    
    # Reverse to print from root to target
    parents.reverse()
    
    # Print each parent
    if parents:
        print("─── Thread Context ───\n")
        for msg, parent_thread in parents:
            if msg:
                print(msg)
            elif parent_thread:
                post = parent_thread.post
                print(format_post(post, 0))
                print()
        print("─── Target Post ───\n")


def thread_to_dict(thread, max_depth: int = None, current_depth: int = 0) -> dict:
    """
    Convert a thread to a dictionary for JSON output.
    
    Recursively converts the thread structure to a plain dict
    that can be serialized to JSON.
    
    Args:
        thread: A ThreadViewPost object
        max_depth: Maximum depth to include
        current_depth: Current depth in traversal
        
    Returns:
        A dictionary representation of the thread
    """
    # Check depth limit
    if max_depth is not None and current_depth > max_depth:
        return None
    
    # Check thread type
    thread_type = getattr(thread, 'py_type', None)
    
    if thread_type == 'app.bsky.feed.defs#notFoundPost':
        return {"type": "notFound", "uri": getattr(thread, 'uri', None)}
    
    if thread_type == 'app.bsky.feed.defs#blockedPost':
        return {"type": "blocked", "uri": getattr(thread, 'uri', None)}
    
    # Get the post
    post = getattr(thread, 'post', None)
    if post is None:
        return {"type": "unknown"}
    
    # Build the post dictionary
    author = post.author
    record = post.record
    
    result = {
        "type": "post",
        "uri": post.uri,
        "cid": post.cid,
        "author": {
            "did": author.did,
            "handle": author.handle,
            "displayName": author.display_name,
        },
        "text": record.text if hasattr(record, 'text') else None,
        "createdAt": record.created_at if hasattr(record, 'created_at') else None,
        "likeCount": post.like_count or 0,
        "replyCount": post.reply_count or 0,
        "repostCount": post.repost_count or 0,
    }
    
    # Add replies
    replies = getattr(thread, 'replies', None) or []
    result["replies"] = []
    
    for reply in replies:
        reply_dict = thread_to_dict(reply, max_depth, current_depth + 1)
        if reply_dict:
            result["replies"].append(reply_dict)
    
    return result


def main():
    """
    Main entry point for the replies script.
    
    Parses command-line arguments, fetches the thread,
    and displays the results.
    """
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Fetch and display replies to a Bluesky post",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View replies using a web URL
  uv run scripts/replies.py https://bsky.app/profile/someone.bsky.social/post/abc123

  # View replies using an AT Protocol URI
  uv run scripts/replies.py "at://did:plc:xxx/app.bsky.feed.post/abc123"

  # Limit reply depth to 2 levels
  uv run scripts/replies.py --depth 2 https://bsky.app/profile/someone/post/abc123

  # Output as JSON
  uv run scripts/replies.py --json https://bsky.app/profile/someone/post/abc123

  # Show only the post and its replies (no parent context)
  uv run scripts/replies.py --no-parents https://bsky.app/profile/someone/post/abc123
        """
    )
    
    # Positional argument: the post to look up
    parser.add_argument(
        "post",
        help="Post identifier: either a bsky.app URL or an AT Protocol URI"
    )
    
    # Optional: limit reply depth
    parser.add_argument(
        "--depth", "-d",
        type=int,
        default=None,
        help="Maximum depth of replies to fetch (default: no limit)"
    )
    
    # Optional: JSON output
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        dest="json_output",
        help="Output as JSON instead of human-readable format"
    )
    
    # Optional: skip parent posts
    parser.add_argument(
        "--no-parents",
        action="store_true",
        help="Don't show parent posts (only target post and replies)"
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Get credentials and create client
    handle, password = get_credentials()
    client = create_client_and_login(handle, password)
    
    # Parse the post identifier to get an AT URI
    uri = parse_post_identifier(client, args.post)
    
    # Fetch the thread
    # Note: We add 1 to depth because depth=0 means just the post itself
    fetch_depth = args.depth + 1 if args.depth is not None else None
    response = fetch_thread(client, uri, fetch_depth)
    
    # Get the thread from the response
    thread = response.thread
    
    # Output based on format
    if args.json_output:
        # Build a JSON structure
        output = {
            "uri": uri,
            "thread": thread_to_dict(thread, args.depth),
        }
        
        # Also include parent if available and requested
        if not args.no_parents:
            parent = getattr(thread, 'parent', None)
            if parent:
                # Walk up to find root
                parents = []
                current = parent
                while current:
                    parent_dict = thread_to_dict(current, max_depth=0)
                    if parent_dict:
                        # Remove the replies key since we're just showing parents
                        parent_dict.pop("replies", None)
                        parents.append(parent_dict)
                    current = getattr(current, 'parent', None)
                parents.reverse()
                output["parents"] = parents
        
        # Print JSON output
        print(json.dumps(output, indent=2, default=str))
    else:
        # Human-readable output
        # Print parent context if requested
        print_parents(thread, show_parents=not args.no_parents)
        
        # Print the main post and its replies
        print_thread(thread, indent=0, max_depth=args.depth)
        
        # Print summary
        replies = getattr(thread, 'replies', None) or []
        if replies:
            print(f"─── {len(replies)} direct repl{'y' if len(replies) == 1 else 'ies'} shown ───")
        else:
            print("─── No replies yet ───")


if __name__ == "__main__":
    main()
