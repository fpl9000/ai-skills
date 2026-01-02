#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Notifications Reader
============================
View your Bluesky notifications (likes, reposts, follows, mentions, replies).

This script retrieves your recent notifications and displays them
in a readable format, grouped by type.

Usage:
    uv run scripts/notifications.py
    uv run scripts/notifications.py --limit 50
    uv run scripts/notifications.py --json

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


def get_notification_emoji(reason: str) -> str:
    """
    Get an emoji representing the notification type.
    
    Args:
        reason: The notification reason/type from the API
        
    Returns:
        An emoji string for display
    """
    # Map notification reasons to appropriate emojis
    emoji_map = {
        "like": "❤️",
        "repost": "🔁",
        "follow": "👤",
        "mention": "💬",
        "reply": "↩️",
        "quote": "💭",
    }
    
    return emoji_map.get(reason, "🔔")


def format_notification_for_display(notification) -> str:
    """
    Format a notification for human-readable display.
    
    Different notification types have different relevant information:
    - like: who liked which of your posts
    - repost: who reposted which of your posts
    - follow: who followed you
    - mention: who mentioned you and in what post
    - reply: who replied to your post
    - quote: who quoted your post
    
    Args:
        notification: A notification object from the API
        
    Returns:
        A formatted string representation of the notification
    """
    # Extract common fields
    reason = notification.reason
    author = notification.author
    indexed_at = notification.indexed_at
    is_read = notification.is_read
    
    # Get display name and handle
    display_name = author.display_name or author.handle
    
    # Format the timestamp
    time_str = format_timestamp(indexed_at) if indexed_at else ""
    
    # Get the appropriate emoji
    emoji = get_notification_emoji(reason)
    
    # Read status indicator
    read_indicator = "" if is_read else "● "
    
    # Build the notification line based on type
    if reason == "like":
        action = "liked your post"
    elif reason == "repost":
        action = "reposted your post"
    elif reason == "follow":
        action = "followed you"
    elif reason == "mention":
        action = "mentioned you"
    elif reason == "reply":
        action = "replied to you"
    elif reason == "quote":
        action = "quoted your post"
    else:
        action = reason
    
    # Main notification line
    line = f"  {read_indicator}{emoji} {display_name} (@{author.handle}) {action} · {time_str}"
    
    # For notifications with content (mentions, replies, quotes), show the text
    record = getattr(notification, "record", None)
    if record and hasattr(record, "text"):
        text = record.text
        if text:
            # Truncate long text
            preview = text[:80].replace("\n", " ")
            if len(text) > 80:
                preview += "..."
            line += f"\n      \"{preview}\""
    
    return line


def notification_to_dict(notification) -> dict:
    """
    Convert a notification to a dictionary for JSON output.
    
    Args:
        notification: A notification object from the API
        
    Returns:
        A dictionary containing the notification data
    """
    author = notification.author
    
    result = {
        "uri": notification.uri,
        "cid": notification.cid,
        "reason": notification.reason,
        "is_read": notification.is_read,
        "indexed_at": notification.indexed_at,
        "author": {
            "did": author.did,
            "handle": author.handle,
            "display_name": author.display_name,
        },
    }
    
    # Include post text for content-based notifications
    record = getattr(notification, "record", None)
    if record and hasattr(record, "text"):
        result["text"] = record.text
    
    return result


def fetch_notifications(client, limit: int = 25, cursor: str = None):
    """
    Fetch notifications for the authenticated user.
    
    Args:
        client: An authenticated Client instance
        limit: Maximum number of notifications to fetch
        cursor: Pagination cursor for fetching more results
        
    Returns:
        A tuple of (list of notifications, next cursor or None)
    """
    # Build parameters for the request
    params = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    
    # Fetch notifications using the notifications endpoint
    response = client.app.bsky.notification.list_notifications(params=params)
    
    # Extract notifications and cursor
    notifications = response.notifications
    next_cursor = response.cursor
    
    return notifications, next_cursor


def get_unread_count(client) -> int:
    """
    Get the count of unread notifications.
    
    Args:
        client: An authenticated Client instance
        
    Returns:
        The number of unread notifications
    """
    response = client.app.bsky.notification.get_unread_count()
    
    return response.count


def mark_notifications_read(client):
    """
    Mark all notifications as read.
    
    This updates the 'seen' timestamp for your notifications,
    marking everything up to now as read.
    
    Args:
        client: An authenticated Client instance
    """
    from datetime import datetime, timezone
    
    # Set the seen timestamp to now
    # This marks all notifications up to this point as read
    seen_at = datetime.now(timezone.utc).isoformat()
    
    client.app.bsky.notification.update_seen({"seen_at": seen_at})


def main():
    """
    Main entry point for the notifications reader.
    
    Parses command-line arguments and displays notifications
    in either human-readable or JSON format.
    """
    parser = argparse.ArgumentParser(
        description="View your Bluesky notifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View recent notifications
  uv run scripts/notifications.py

  # View more notifications
  uv run scripts/notifications.py --limit 50

  # Output as JSON
  uv run scripts/notifications.py --json

  # Just show the unread count
  uv run scripts/notifications.py --count

  # Mark all notifications as read
  uv run scripts/notifications.py --mark-read
        """
    )
    
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=25,
        help="Number of notifications to fetch (default: 25)"
    )
    
    parser.add_argument(
        "--cursor", "-c",
        help="Pagination cursor for fetching more results"
    )
    
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON"
    )
    
    parser.add_argument(
        "--count",
        action="store_true",
        help="Only show the unread notification count"
    )
    
    parser.add_argument(
        "--mark-read", "-m",
        action="store_true",
        help="Mark all notifications as read"
    )
    
    args = parser.parse_args()
    
    # Get credentials and create authenticated client
    handle, password = get_credentials()
    client = create_client_and_login(handle, password)
    
    if args.count:
        # Just show the unread count
        count = get_unread_count(client)
        
        if args.json:
            print(json.dumps({"unread_count": count}))
        else:
            print(f"🔔 You have {count} unread notification(s)")
        
        return
    
    if args.mark_read:
        # Mark all notifications as read
        mark_notifications_read(client)
        print("✅ All notifications marked as read")
        return
    
    # Fetch notifications
    notifications, next_cursor = fetch_notifications(
        client,
        limit=args.limit,
        cursor=args.cursor
    )
    
    # Get unread count for display
    unread_count = get_unread_count(client)
    
    if args.json:
        # Output as JSON
        output = {
            "unread_count": unread_count,
            "count": len(notifications),
            "notifications": [notification_to_dict(n) for n in notifications],
        }
        if next_cursor:
            output["cursor"] = next_cursor
            
        print(json.dumps(output, indent=2))
    else:
        # Output as formatted text
        print(f"\n🔔 Your Notifications ({len(notifications)} shown, {unread_count} unread)")
        print("=" * 60)
        
        if not notifications:
            print("\n  No notifications to display.")
        else:
            # Group by type for cleaner display
            for notification in notifications:
                print(format_notification_for_display(notification))
                print()
        
        # Show pagination info if there are more results
        if next_cursor:
            print(f"\n📄 More notifications available. Use --cursor \"{next_cursor}\" to continue")


if __name__ == "__main__":
    main()
