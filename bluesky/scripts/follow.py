#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Follow/Unfollow Script
==============================
Follow or unfollow users on Bluesky.

This script allows you to manage your follows by adding or removing
users from your following list.

Usage:
    uv run scripts/follow.py username.bsky.social
    uv run scripts/follow.py --unfollow username.bsky.social
    uv run scripts/follow.py --list

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
        A tuple of (client, authenticated user's DID)
    """
    from atproto import Client
    
    client = Client()
    profile = client.login(handle, password)
    
    # Return both the client and the user's DID
    # The DID is needed for some operations like unfollowing
    return client, profile.did


def get_user_did(client, handle: str) -> str:
    """
    Resolve a user handle to their DID.
    
    DIDs (Decentralized Identifiers) are the permanent unique identifiers
    in the AT Protocol. Handles can change, but DIDs are forever.
    
    Args:
        client: An authenticated Client instance
        handle: The user's handle to resolve
        
    Returns:
        The user's DID string
    """
    # Fetch the profile to get the DID
    profile = client.get_profile(handle)
    
    return profile.did


def follow_user(client, user_did: str):
    """
    Follow a user by their DID.
    
    Following creates a 'follow' record in your repository that points
    to the target user's DID. This is how the AT Protocol tracks
    social graph relationships.
    
    Args:
        client: An authenticated Client instance
        user_did: The DID of the user to follow
        
    Returns:
        The URI of the created follow record
    """
    # The follow method creates a follow record in your repo
    # It returns information about the created record
    response = client.follow(user_did)
    
    return response.uri


def unfollow_user(client, user_did: str, my_did: str):
    """
    Unfollow a user by their DID.
    
    Unfollowing requires finding and deleting the follow record.
    We need to query for the existing follow relationship first.
    
    Args:
        client: An authenticated Client instance
        user_did: The DID of the user to unfollow
        my_did: The DID of the authenticated user (you)
        
    Returns:
        True if successfully unfollowed, False if not following
    """
    # To unfollow, we need to find the follow record first
    # The follow record URI has the format: at://my-did/app.bsky.graph.follow/rkey
    
    # Get the profile to check the viewer state
    # This tells us if we're currently following and the follow record URI
    profile = client.get_profile(user_did)
    
    # Check if we're following this user
    # The viewer field contains relationship state from our perspective
    viewer = getattr(profile, "viewer", None)
    
    if not viewer:
        print("Error: Could not determine follow status", file=sys.stderr)
        return False
    
    # The 'following' field contains the URI of our follow record (if it exists)
    follow_uri = getattr(viewer, "following", None)
    
    if not follow_uri:
        print(f"You are not following this user", file=sys.stderr)
        return False
    
    # Delete the follow record to unfollow
    # The unfollow method handles parsing the URI and deleting the record
    client.unfollow(follow_uri)
    
    return True


def list_following(client, actor: str, limit: int = 50):
    """
    List all users that the specified actor is following.
    
    Args:
        client: An authenticated Client instance
        actor: The handle or DID of the user whose follows to list
        limit: Maximum number of results per page
        
    Returns:
        A generator yielding follow records
    """
    cursor = None
    
    while True:
        # Fetch a page of follows
        params = {"actor": actor, "limit": limit}
        if cursor:
            params["cursor"] = cursor
            
        response = client.app.bsky.graph.get_follows(params=params)
        
        # Yield each follow record
        for follow in response.follows:
            yield follow
        
        # Check for more pages
        cursor = response.cursor
        if not cursor:
            break


def list_followers(client, actor: str, limit: int = 50):
    """
    List all users who follow the specified actor.
    
    Args:
        client: An authenticated Client instance
        actor: The handle or DID of the user whose followers to list
        limit: Maximum number of results per page
        
    Returns:
        A generator yielding follower records
    """
    cursor = None
    
    while True:
        # Fetch a page of followers
        params = {"actor": actor, "limit": limit}
        if cursor:
            params["cursor"] = cursor
            
        response = client.app.bsky.graph.get_followers(params=params)
        
        # Yield each follower record
        for follower in response.followers:
            yield follower
        
        # Check for more pages
        cursor = response.cursor
        if not cursor:
            break


def main():
    """
    Main entry point for the follow/unfollow script.
    
    Parses command-line arguments and executes the requested action.
    """
    parser = argparse.ArgumentParser(
        description="Follow or unfollow users on Bluesky",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Follow a user
  uv run scripts/follow.py someone.bsky.social

  # Unfollow a user
  uv run scripts/follow.py --unfollow someone.bsky.social

  # List who you're following
  uv run scripts/follow.py --list

  # List your followers
  uv run scripts/follow.py --list --followers

  # List who another user follows
  uv run scripts/follow.py --list someone.bsky.social

  # Output as JSON
  uv run scripts/follow.py --list --json
        """
    )
    
    # The user to follow/unfollow (optional when using --list without a target)
    parser.add_argument(
        "user",
        nargs="?",
        help="Handle of the user to follow/unfollow/list"
    )
    
    parser.add_argument(
        "--unfollow", "-u",
        action="store_true",
        help="Unfollow the specified user instead of following"
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List follows instead of following/unfollowing"
    )
    
    parser.add_argument(
        "--followers", "-f",
        action="store_true",
        help="When listing, show followers instead of following"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of results when listing (default: 100)"
    )
    
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.list and not args.user:
        parser.error("Please specify a user to follow/unfollow, or use --list")
    
    # Get credentials and create authenticated client
    handle, password = get_credentials()
    client, my_did = create_client_and_login(handle, password)
    
    if args.list:
        # List mode: show following or followers
        target = args.user or handle
        
        if args.followers:
            # List followers
            print(f"Fetching followers for @{target}...", file=sys.stderr)
            users = list(list_followers(client, target, limit=50))[:args.limit]
            label = "Followers"
        else:
            # List following
            print(f"Fetching follows for @{target}...", file=sys.stderr)
            users = list(list_following(client, target, limit=50))[:args.limit]
            label = "Following"
        
        if args.json:
            # Output as JSON
            output = {
                "actor": target,
                "type": "followers" if args.followers else "following",
                "count": len(users),
                "users": [
                    {
                        "did": u.did,
                        "handle": u.handle,
                        "display_name": u.display_name,
                        "description": u.description,
                    }
                    for u in users
                ],
            }
            print(json.dumps(output, indent=2))
        else:
            # Output as formatted text
            print(f"\n{label} for @{target} ({len(users)} users)")
            print("=" * 50)
            
            for user in users:
                display_name = user.display_name or user.handle
                print(f"  {display_name} (@{user.handle})")
                if user.description:
                    # Show first line of bio
                    bio_preview = user.description.split("\n")[0][:50]
                    if len(user.description) > 50:
                        bio_preview += "..."
                    print(f"    {bio_preview}")
            
            print()
    
    elif args.unfollow:
        # Unfollow mode
        print(f"Unfollowing @{args.user}...", file=sys.stderr)
        
        try:
            # Resolve handle to DID
            user_did = get_user_did(client, args.user)
            
            # Attempt to unfollow
            success = unfollow_user(client, user_did, my_did)
            
            if success:
                print(f"✅ Successfully unfollowed @{args.user}")
            else:
                sys.exit(1)
                
        except Exception as e:
            print(f"Error: Could not unfollow user: {e}", file=sys.stderr)
            sys.exit(1)
    
    else:
        # Follow mode
        print(f"Following @{args.user}...", file=sys.stderr)
        
        try:
            # Resolve handle to DID
            user_did = get_user_did(client, args.user)
            
            # Follow the user
            follow_uri = follow_user(client, user_did)
            
            print(f"✅ Successfully followed @{args.user}")
            print(f"   Follow URI: {follow_uri}")
            
        except Exception as e:
            # Check if already following
            if "already" in str(e).lower():
                print(f"You are already following @{args.user}")
            else:
                print(f"Error: Could not follow user: {e}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
