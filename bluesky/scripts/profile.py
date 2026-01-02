#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Profile Viewer
======================
View profile information for any Bluesky user, including your own.

This script retrieves detailed profile information including:
- Display name and handle
- Bio/description
- Follower and following counts
- Post count
- Avatar and banner URLs

Usage:
    uv run scripts/profile.py
    uv run scripts/profile.py username.bsky.social
    uv run scripts/profile.py --json

Environment Variables Required:
    BLUESKY_HANDLE   - Your Bluesky handle (e.g., yourname.bsky.social)
    BLUESKY_PASSWORD - Your Bluesky app password
"""

import argparse
import json
import os
import sys


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


def get_profile(client, actor: str):
    """
    Fetch the profile for a given user.
    
    The 'actor' parameter can be either a handle (e.g., "user.bsky.social")
    or a DID (decentralized identifier like "did:plc:xyz123").
    
    Args:
        client: An authenticated Client instance
        actor: The handle or DID of the user to look up
        
    Returns:
        A ProfileViewDetailed object containing the user's profile data
    """
    # The get_profile method fetches detailed profile information
    # It accepts either a handle or a DID as the actor parameter
    profile = client.get_profile(actor)
    
    return profile


def format_profile_for_display(profile) -> str:
    """
    Format a profile for human-readable display.
    
    Creates a nicely formatted display of the user's profile
    information with labels and visual separators.
    
    Args:
        profile: A ProfileViewDetailed object
        
    Returns:
        A formatted string representation of the profile
    """
    lines = []
    
    # Header with display name and handle
    display_name = profile.display_name or profile.handle
    lines.append(f"╭{'─' * 52}╮")
    lines.append(f"│ 👤 {display_name:<48} │")
    lines.append(f"│    @{profile.handle:<47} │")
    lines.append(f"├{'─' * 52}┤")
    
    # DID (decentralized identifier) - unique across the network
    lines.append(f"│ DID: {profile.did:<46} │")
    
    # Bio/description
    description = profile.description or "(No bio)"
    lines.append(f"├{'─' * 52}┤")
    lines.append(f"│ Bio:                                               │")
    
    # Wrap the description to fit in the box
    # Split into lines of max 48 characters
    if description:
        words = description.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= 48:
                current_line += (" " if current_line else "") + word
            else:
                lines.append(f"│   {current_line:<49} │")
                current_line = word
        if current_line:
            lines.append(f"│   {current_line:<49} │")
    
    # Statistics section
    lines.append(f"├{'─' * 52}┤")
    lines.append(f"│ 📊 Statistics                                      │")
    
    # Follower and following counts
    followers = profile.followers_count or 0
    following = profile.follows_count or 0
    posts = profile.posts_count or 0
    
    lines.append(f"│   Followers: {followers:<39} │")
    lines.append(f"│   Following: {following:<39} │")
    lines.append(f"│   Posts:     {posts:<39} │")
    
    # Avatar and banner URLs (if present)
    if profile.avatar or profile.banner:
        lines.append(f"├{'─' * 52}┤")
        lines.append(f"│ 🖼️  Images                                         │")
        
        if profile.avatar:
            # Truncate URL if too long
            avatar_url = profile.avatar
            if len(avatar_url) > 46:
                avatar_url = avatar_url[:43] + "..."
            lines.append(f"│   Avatar: {avatar_url:<41} │")
            
        if profile.banner:
            banner_url = profile.banner
            if len(banner_url) > 46:
                banner_url = banner_url[:43] + "..."
            lines.append(f"│   Banner: {banner_url:<41} │")
    
    # Labels (moderation labels, if any)
    if hasattr(profile, "labels") and profile.labels:
        lines.append(f"├{'─' * 52}┤")
        lines.append(f"│ 🏷️  Labels                                         │")
        for label in profile.labels:
            label_val = getattr(label, "val", str(label))
            lines.append(f"│   • {label_val:<47} │")
    
    # Close the box
    lines.append(f"╰{'─' * 52}╯")
    
    # Add web URL
    lines.append(f"\n  🔗 View on web: https://bsky.app/profile/{profile.handle}")
    
    return "\n".join(lines)


def profile_to_dict(profile) -> dict:
    """
    Convert a profile to a dictionary for JSON output.
    
    Extracts all relevant profile fields into a clean dictionary
    structure suitable for JSON serialization.
    
    Args:
        profile: A ProfileViewDetailed object
        
    Returns:
        A dictionary containing the profile data
    """
    result = {
        "did": profile.did,
        "handle": profile.handle,
        "display_name": profile.display_name,
        "description": profile.description,
        "avatar": profile.avatar,
        "banner": profile.banner,
        "followers_count": profile.followers_count or 0,
        "follows_count": profile.follows_count or 0,
        "posts_count": profile.posts_count or 0,
        "web_url": f"https://bsky.app/profile/{profile.handle}",
    }
    
    # Add indexed_at if present (when the profile was indexed)
    if hasattr(profile, "indexed_at") and profile.indexed_at:
        result["indexed_at"] = profile.indexed_at
    
    # Add labels if present
    if hasattr(profile, "labels") and profile.labels:
        result["labels"] = [
            getattr(label, "val", str(label)) for label in profile.labels
        ]
    
    return result


def main():
    """
    Main entry point for the profile viewer.
    
    Parses command-line arguments and displays the requested profile
    in either human-readable or JSON format.
    """
    parser = argparse.ArgumentParser(
        description="View Bluesky user profiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View your own profile
  uv run scripts/profile.py

  # View another user's profile
  uv run scripts/profile.py someone.bsky.social

  # Output as JSON
  uv run scripts/profile.py --json

  # View profile by DID
  uv run scripts/profile.py did:plc:abc123xyz
        """
    )
    
    # Optional: the user to look up (defaults to self)
    parser.add_argument(
        "user",
        nargs="?",  # Makes this argument optional
        help="Handle or DID of the user to look up (defaults to your own profile)"
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
    
    # Determine which user to look up
    # If no user specified, look up the authenticated user's profile
    target_user = args.user or handle
    
    # Fetch the profile
    try:
        profile = get_profile(client, target_user)
    except Exception as e:
        print(f"Error: Could not find user '{target_user}'", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.json:
        # Output as JSON
        print(json.dumps(profile_to_dict(profile), indent=2))
    else:
        # Output as formatted text
        print()
        print(format_profile_for_display(profile))
        print()


if __name__ == "__main__":
    main()
