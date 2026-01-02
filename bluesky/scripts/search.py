#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Search Script
=====================
Search for posts on Bluesky by keywords, hashtags, or phrases.

The search API allows you to find posts containing specific terms,
with support for pagination to retrieve large result sets.

Usage:
    uv run scripts/search.py "python programming"
    uv run scripts/search.py "#datascience" --limit 50
    uv run scripts/search.py "machine learning" --json

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
        A human-readable relative time string
    """
    try:
        if iso_timestamp.endswith("Z"):
            dt = datetime.fromisoformat(iso_timestamp[:-1])
        else:
            dt = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return iso_timestamp
    
    now = datetime.utcnow()
    diff = now - dt
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    elif seconds < 604800:
        return f"{int(seconds / 86400)}d ago"
    else:
        return dt.strftime("%b %d, %Y")


def format_post_for_display(post) -> str:
    """
    Format a search result post for human-readable display.
    
    Search results return PostView objects directly (not wrapped in
    FeedViewPost like the timeline). The structure is slightly different.
    
    Args:
        post: A PostView object from the search response
        
    Returns:
        A formatted string representation of the post
    """
    # Extract author information
    author = post.author
    display_name = author.display_name or author.handle
    handle = author.handle
    
    # Extract post content from the record
    record = post.record
    text = record.text if hasattr(record, "text") else ""
    created_at = record.created_at if hasattr(record, "created_at") else ""
    
    # Format the timestamp
    time_str = format_timestamp(created_at) if created_at else ""
    
    # Extract engagement metrics
    like_count = post.like_count or 0
    repost_count = post.repost_count or 0
    reply_count = post.reply_count or 0
    
    # Build the formatted output
    lines = []
    
    # Add author and timestamp header
    lines.append(f"  {display_name} (@{handle}) · {time_str}")
    
    # Add the post text, indented for readability
    if text:
        for line in text.split("\n"):
            lines.append(f"    {line}")
    
    # Add engagement metrics
    lines.append(f"    ❤️ {like_count}  🔁 {repost_count}  💬 {reply_count}")
    
    # Add separator
    lines.append("  " + "─" * 50)
    
    return "\n".join(lines)


def post_to_dict(post) -> dict:
    """
    Convert a search result post to a dictionary for JSON output.
    
    Args:
        post: A PostView object from the search response
        
    Returns:
        A dictionary containing the post data
    """
    author = post.author
    record = post.record
    
    return {
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


def search_posts(client, query: str, limit: int = 25, cursor: str = None):
    """
    Search for posts matching the given query.
    
    The search API supports:
    - Keywords: "python programming"
    - Hashtags: "#machinelearning"
    - Phrases: "hello world"
    - Combinations: "#python tutorial"
    
    Args:
        client: An authenticated Client instance
        query: The search query string
        limit: Maximum number of results to return
        cursor: Pagination cursor for fetching more results
        
    Returns:
        A tuple of (list of posts, next cursor or None)
    """
    # Build the search parameters
    params = {
        "q": query,
        "limit": limit,
    }
    
    # Add cursor if provided for pagination
    if cursor:
        params["cursor"] = cursor
    
    # Execute the search using the app.bsky.feed.search_posts endpoint
    # This is accessed through the client's namespace hierarchy
    response = client.app.bsky.feed.search_posts(params=params)
    
    # Extract posts and pagination cursor
    posts = response.posts
    next_cursor = response.cursor
    
    return posts, next_cursor


def search_all_posts(client, query: str, max_results: int = 100):
    """
    Search for posts with automatic pagination to collect more results.
    
    This function handles pagination automatically, making multiple API
    calls to collect up to max_results posts.
    
    Args:
        client: An authenticated Client instance
        query: The search query string
        max_results: Maximum total number of results to collect
        
    Returns:
        A list of all collected posts
    """
    all_posts = []
    cursor = None
    
    # Continue fetching until we have enough results or run out of pages
    while len(all_posts) < max_results:
        # Calculate how many more posts we need
        remaining = max_results - len(all_posts)
        
        # Fetch a batch of results (API limit is typically 100 per request)
        batch_size = min(remaining, 100)
        posts, cursor = search_posts(client, query, limit=batch_size, cursor=cursor)
        
        # Add the fetched posts to our collection
        all_posts.extend(posts)
        
        # If no cursor returned, we've exhausted the results
        if not cursor:
            break
        
        # Print progress for long searches
        print(f"  Fetched {len(all_posts)} posts so far...", file=sys.stderr)
    
    return all_posts


def main():
    """
    Main entry point for the search script.
    
    Parses command-line arguments and executes the search query,
    displaying results in either human-readable or JSON format.
    """
    parser = argparse.ArgumentParser(
        description="Search for posts on Bluesky",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search for posts about Python
  uv run scripts/search.py "python programming"

  # Search for a hashtag
  uv run scripts/search.py "#machinelearning"

  # Search with more results
  uv run scripts/search.py "artificial intelligence" --limit 100

  # Output as JSON
  uv run scripts/search.py "data science" --json

  # Paginate through results
  uv run scripts/search.py "web dev" --cursor "abc123..."
        """
    )
    
    # Required argument: the search query
    parser.add_argument(
        "query",
        help="Search query (keywords, hashtags, or phrases)"
    )
    
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=25,
        help="Maximum number of results to return (default: 25)"
    )
    
    parser.add_argument(
        "--cursor", "-c",
        help="Pagination cursor for fetching more results"
    )
    
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Fetch all results up to --limit using automatic pagination"
    )
    
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON instead of formatted text"
    )
    
    args = parser.parse_args()
    
    # Get credentials and create authenticated client
    handle, password = get_credentials()
    client = create_client_and_login(handle, password)
    
    # Execute the search
    if args.all:
        # Fetch all results with automatic pagination
        posts = search_all_posts(client, args.query, max_results=args.limit)
        next_cursor = None  # No cursor when using --all
    else:
        # Fetch a single page of results
        posts, next_cursor = search_posts(
            client,
            args.query,
            limit=args.limit,
            cursor=args.cursor
        )
    
    if args.json:
        # Output as JSON
        output = {
            "query": args.query,
            "count": len(posts),
            "posts": [post_to_dict(post) for post in posts],
        }
        
        # Only include cursor if we have one
        if next_cursor:
            output["cursor"] = next_cursor
            
        print(json.dumps(output, indent=2))
    else:
        # Output as formatted text
        print(f"\n🔍 Search results for: \"{args.query}\" ({len(posts)} posts)")
        print("=" * 54)
        
        if not posts:
            print("\n  No posts found matching your query.")
        else:
            for post in posts:
                print(format_post_for_display(post))
                print()
        
        # Show pagination info if there are more results
        if next_cursor:
            print(f"\n📄 More results available. Use --cursor \"{next_cursor}\" to continue")


if __name__ == "__main__":
    main()
