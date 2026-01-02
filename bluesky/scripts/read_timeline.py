#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Timeline Reader
=======================
Fetches and displays posts from your Bluesky timeline (home feed).

This script retrieves posts from the accounts you follow, displaying
them in a readable format with author information, timestamps, and
engagement metrics.

Usage:
    uv run scripts/read_timeline.py
    uv run scripts/read_timeline.py --limit 50
    uv run scripts/read_timeline.py --json

Environment Variables Required:
    BLUESKY_HANDLE   - Your Bluesky handle (e.g., yourname.bsky.social)
    BLUESKY_PASSWORD - Your Bluesky app password
"""

import argparse
import json
import os
import sys
from datetime import datetime


def get_credentials():
    """
    Retrieve Bluesky credentials from environment variables.
    
    Returns a tuple of (handle, password) if both are set.
    Exits with an error message if either is missing.
    """
    handle = os.environ.get("BLUESKY_HANDLE")
    password = os.environ.get("BLUESKY_PASSWORD")
    
    if not handle:
        print("Error: BLUESKY_HANDLE environment variable not set", file=sys.stderr)
        sys.exit(1)
        
    if not password:
        print("Error: BLUESKY_PASSWORD environment variable not set", file=sys.stderr)
        sys.exit(1)
    
    return handle, password


def create_client_and_login(handle: str, password: str):
    """
    Create an authenticated Bluesky client.
    
    Args:
        handle: Your Bluesky handle
        password: Your Bluesky app password
        
    Returns:
        An authenticated Client instance
    """
    from atproto import Client
    
    client = Client()
    client.login(handle, password)
    
    return client


def format_timestamp(iso_timestamp: str) -> str:
    """
    Convert an ISO timestamp to a human-readable relative time.
    
    Args:
        iso_timestamp: An ISO 8601 formatted timestamp string
        
    Returns:
        A human-readable relative time string (e.g., "2 hours ago")
    """
    # Parse the ISO timestamp
    # Handle both 'Z' suffix and timezone offset formats
    try:
        # Remove 'Z' and parse as UTC
        if iso_timestamp.endswith("Z"):
            dt = datetime.fromisoformat(iso_timestamp[:-1])
        else:
            # Python 3.11+ handles timezone offsets directly
            dt = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        # If parsing fails, return the original string
        return iso_timestamp
    
    # Calculate the time difference from now
    now = datetime.utcnow()
    diff = now - dt
    
    # Convert to human-readable format
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d ago"
    else:
        # For older posts, show the actual date
        return dt.strftime("%b %d, %Y")


def format_post_for_display(feed_item) -> str:
    """
    Format a single feed item for human-readable display.
    
    The feed contains FeedViewPost objects, which wrap the actual post
    along with metadata about how it appears in your feed (e.g., if it's
    a repost, the reason is included).
    
    Args:
        feed_item: A FeedViewPost object from the timeline response
        
    Returns:
        A formatted string representation of the post
    """
    # Extract the post from the feed item
    # The feed_item.post contains the actual PostView
    post = feed_item.post
    
    # Extract author information
    author = post.author
    display_name = author.display_name or author.handle
    handle = author.handle
    
    # Extract post content
    # The record contains the actual post data (text, created_at, etc.)
    record = post.record
    text = record.text if hasattr(record, "text") else ""
    created_at = record.created_at if hasattr(record, "created_at") else ""
    
    # Format the timestamp
    time_str = format_timestamp(created_at) if created_at else ""
    
    # Extract engagement metrics
    # These show how the post has been interacted with
    like_count = post.like_count or 0
    repost_count = post.repost_count or 0
    reply_count = post.reply_count or 0
    
    # Check if this is a repost by someone else
    # The reason field indicates why this post is in your feed
    reason = getattr(feed_item, "reason", None)
    repost_line = ""
    if reason and hasattr(reason, "by"):
        # This is a repost - show who reposted it
        reposter = reason.by
        reposter_name = reposter.display_name or reposter.handle
        repost_line = f"  🔁 Reposted by {reposter_name}\n"
    
    # Build the formatted output
    lines = []
    
    # Add repost indicator if applicable
    if repost_line:
        lines.append(repost_line)
    
    # Add author and timestamp header
    lines.append(f"  {display_name} (@{handle}) · {time_str}")
    
    # Add the post text, indented for readability
    if text:
        # Wrap long lines and indent
        for line in text.split("\n"):
            lines.append(f"    {line}")
    
    # Add engagement metrics
    lines.append(f"    ❤️ {like_count}  🔁 {repost_count}  💬 {reply_count}")
    
    # Add separator
    lines.append("  " + "─" * 50)
    
    return "\n".join(lines)


def post_to_dict(feed_item) -> dict:
    """
    Convert a feed item to a dictionary for JSON output.
    
    This extracts the relevant fields into a clean dictionary structure
    suitable for JSON serialization or further processing.
    
    Args:
        feed_item: A FeedViewPost object from the timeline response
        
    Returns:
        A dictionary containing the post data
    """
    post = feed_item.post
    author = post.author
    record = post.record
    
    # Build the base post dictionary
    result = {
        "uri": post.uri,
        "cid": post.cid,
        "author": {
            "did": author.did,
            "handle": author.handle,
            "display_name": author.display_name,
        },
        "text": record.text if hasattr(record, "text") else "",
        "created_at": record.created_at if hasattr(record, "created_at") else "",
        "metrics": {
            "likes": post.like_count or 0,
            "reposts": post.repost_count or 0,
            "replies": post.reply_count or 0,
        },
    }
    
    # Add repost information if applicable
    reason = getattr(feed_item, "reason", None)
    if reason and hasattr(reason, "by"):
        result["reposted_by"] = {
            "did": reason.by.did,
            "handle": reason.by.handle,
            "display_name": reason.by.display_name,
        }
    
    return result


def fetch_timeline(client, limit: int = 25, cursor: str = None):
    """
    Fetch posts from the authenticated user's timeline.
    
    The timeline (home feed) contains posts from accounts you follow,
    including their reposts. Results are paginated using cursors.
    
    Args:
        client: An authenticated Client instance
        limit: Maximum number of posts to fetch (1-100)
        cursor: Pagination cursor for fetching more results
        
    Returns:
        A tuple of (list of feed items, next cursor or None)
    """
    # The get_timeline method fetches the home feed
    # It returns a Response object with 'feed' and 'cursor' attributes
    response = client.get_timeline(limit=limit, cursor=cursor)
    
    # Extract the feed items and the cursor for pagination
    feed = response.feed
    next_cursor = response.cursor
    
    return feed, next_cursor


def main():
    """
    Main entry point for the timeline reader.
    
    Parses command-line arguments and displays the user's timeline
    in either human-readable or JSON format.
    """
    parser = argparse.ArgumentParser(
        description="Read your Bluesky timeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Read your timeline (default 25 posts)
  uv run scripts/read_timeline.py

  # Read more posts
  uv run scripts/read_timeline.py --limit 50

  # Output as JSON for processing
  uv run scripts/read_timeline.py --json

  # Paginate through results
  uv run scripts/read_timeline.py --limit 25 --cursor "abc123..."
        """
    )
    
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=25,
        help="Number of posts to fetch (default: 25, max: 100)"
    )
    
    parser.add_argument(
        "--cursor", "-c",
        help="Pagination cursor for fetching more results"
    )
    
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON instead of formatted text"
    )
    
    args = parser.parse_args()
    
    # Clamp limit to valid range
    limit = max(1, min(100, args.limit))
    
    # Get credentials and create authenticated client
    handle, password = get_credentials()
    client = create_client_and_login(handle, password)
    
    # Fetch the timeline
    feed, next_cursor = fetch_timeline(client, limit=limit, cursor=args.cursor)
    
    if args.json:
        # Output as JSON
        output = {
            "posts": [post_to_dict(item) for item in feed],
            "cursor": next_cursor,
        }
        print(json.dumps(output, indent=2))
    else:
        # Output as formatted text
        print(f"\n📰 Your Bluesky Timeline ({len(feed)} posts)")
        print("=" * 54)
        
        for item in feed:
            print(format_post_for_display(item))
            print()
        
        # Show pagination info if there are more results
        if next_cursor:
            print(f"\n📄 More posts available. Use --cursor \"{next_cursor}\" to continue")


if __name__ == "__main__":
    main()
