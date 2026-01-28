#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Reply Script
====================
Post a reply to an existing Bluesky post.

The AT Protocol requires replies to include threading information:
- "root": Reference to the original post that started the thread
- "parent": Reference to the post being directly replied to

This script automatically resolves the thread structure, so you only need
to specify the post you want to reply to.

Usage:
    uv run scripts/reply.py --to <post-url-or-uri> --text "Your reply"
    
Examples:
    # Reply using a web URL
    uv run scripts/reply.py --to https://bsky.app/profile/someone.bsky.social/post/abc123 \\
        --text "Great post!"
    
    # Reply using an AT Protocol URI
    uv run scripts/reply.py --to "at://did:plc:xxx/app.bsky.feed.post/abc123" \\
        --text "I agree!"

Environment Variables Required:
    BLUESKY_HANDLE   - Your Bluesky handle (e.g., yourname.bsky.social)
    BLUESKY_PASSWORD - Your Bluesky app password (create in Settings > App Passwords)
"""

import argparse
import os
import re
import sys


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
    # App Passwords can be created in Bluesky Settings > App Passwords
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
    # By default, this connects to the main Bluesky PDS at bsky.social
    client = Client()
    
    # Authenticate with the provided credentials
    # This establishes a session and stores auth tokens in the client
    profile = client.login(handle, password)
    
    # Print a confirmation message with the authenticated user's display name
    print(f"Logged in as: {profile.display_name} (@{profile.handle})")
    
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
    web_url_pattern = r"https?://bsky\.app/profile/([^/]+)/post/([a-zA-Z0-9]+)"
    match = re.match(web_url_pattern, identifier)
    
    if not match:
        print(f"Error: Invalid post identifier: {identifier}", file=sys.stderr)
        print("Expected formats:", file=sys.stderr)
        print("  - https://bsky.app/profile/handle/post/rkey", file=sys.stderr)
        print("  - at://did:plc:xxx/app.bsky.feed.post/rkey", file=sys.stderr)
        sys.exit(1)
    
    # Extract the handle and record key from the URL
    handle = match.group(1)
    rkey = match.group(2)
    
    # Resolve the handle to a DID
    # Handles can change, but DIDs are permanent identifiers
    try:
        # Use the identity resolution API to get the DID
        resolved = client.resolve_handle(handle)
        did = resolved.did
    except Exception as e:
        print(f"Error: Could not resolve handle '{handle}': {e}", file=sys.stderr)
        sys.exit(1)
    
    # Construct the AT Protocol URI
    # Format: at://{did}/app.bsky.feed.post/{rkey}
    at_uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    
    return at_uri


def get_post_thread(client, uri: str):
    """
    Fetch the thread context for a post.
    
    This retrieves the post along with its parent chain, which we need
    to properly construct the reply reference (root and parent).
    
    Args:
        client: An authenticated Client instance
        uri: The AT Protocol URI of the post
        
    Returns:
        The thread response containing the post and its context
    """
    # Import the models for type checking
    from atproto import models
    
    try:
        # Fetch the thread using the feed API
        # This returns the post with its parent/reply chain
        response = client.get_post_thread(uri=uri)
        return response
    except Exception as e:
        print(f"Error: Could not fetch post thread: {e}", file=sys.stderr)
        sys.exit(1)


def find_thread_root(thread):
    """
    Walk up the parent chain to find the root post of the thread.
    
    In AT Protocol, replies need a reference to both:
    - The immediate parent (the post being replied to)
    - The thread root (the original post that started the conversation)
    
    Args:
        thread: A thread response from get_post_thread
        
    Returns:
        A tuple of (root_uri, root_cid) for the thread's root post
    """
    # Import models for type checking
    from atproto import models
    
    # Start with the current thread position
    current = thread.thread
    
    # Walk up the parent chain until we find the root
    # The root is the post with no parent
    while hasattr(current, 'parent') and current.parent is not None:
        parent = current.parent
        
        # Check if the parent is a valid post (not blocked/deleted)
        if hasattr(parent, 'post'):
            current = parent
        else:
            # Parent is blocked, deleted, or not found
            # Stop here and use current as the effective root
            break
    
    # Extract the URI and CID from the root post
    root_uri = current.post.uri
    root_cid = current.post.cid
    
    return root_uri, root_cid


def build_text_with_facets(text: str):
    """
    Build a TextBuilder with proper link facets for URLs in the text.
    
    The atproto library's send_post() method does NOT automatically detect
    URLs in plain text strings. To make links clickable, we must use the
    TextBuilder class and explicitly mark URLs with the .link() method.
    
    This function detects URLs in the text (both with and without http(s)://
    schemes) and constructs a TextBuilder with proper link facets.
    
    Args:
        text: The post text that may contain URLs
        
    Returns:
        A TextBuilder instance with links properly marked as facets
    """
    # Import the client_utils module for TextBuilder
    from atproto import client_utils
    
    # Regex pattern to match URLs in text
    # This pattern matches:
    # 1. URLs with explicit scheme: http:// or https://
    # 2. URLs without scheme that start with common patterns like www. or domain.tld/
    # 
    # The pattern is designed to stop at whitespace, quotes, and common punctuation
    # that typically ends a URL in natural text.
    url_pattern = re.compile(
        r'('
        # Match URLs with explicit http:// or https:// scheme
        r'https?://[^\s<>\[\]()\"\']*[^\s<>\[\]()\"\'.,;:!?\)]'
        r'|'
        # Match www. URLs without scheme
        r'www\.[^\s<>\[\]()\"\']+[^\s<>\[\]()\"\'.,;:!?\)]'
        r'|'
        # Match domain.tld/path URLs without scheme (e.g., github.com/user/repo)
        # Requires at least one path segment to avoid matching plain domains in text
        r'[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s<>\[\]()\"\']*[^\s<>\[\]()\"\'.,;:!?\)])?'
        r')',
        re.IGNORECASE
    )
    
    # Find all URL matches with their positions
    matches = list(url_pattern.finditer(text))
    
    # If no URLs found, return a simple TextBuilder with just the text
    if not matches:
        tb = client_utils.TextBuilder()
        tb.text(text)
        return tb
    
    # Build the text with proper link facets
    # We iterate through the text, adding plain text segments and link segments
    tb = client_utils.TextBuilder()
    last_end = 0
    
    for match in matches:
        start, end = match.span()
        url_text = match.group(0)
        
        # Add any plain text before this URL
        if start > last_end:
            tb.text(text[last_end:start])
        
        # Determine the full URL (add https:// if no scheme present)
        # This is required for the facet's URI field
        if url_text.startswith(('http://', 'https://')):
            full_url = url_text
        elif url_text.startswith('www.'):
            full_url = 'https://' + url_text
        else:
            full_url = 'https://' + url_text
        
        # Add the URL as a link facet
        # The first argument is the display text, second is the actual URL
        tb.link(url_text, full_url)
        
        last_end = end
    
    # Add any remaining plain text after the last URL
    if last_end < len(text):
        tb.text(text[last_end:])
    
    return tb


def post_reply(client, parent_uri: str, parent_cid: str, 
               root_uri: str, root_cid: str, text: str):
    """
    Post a reply to an existing Bluesky post.
    
    AT Protocol replies require both root and parent references:
    - root: The original post that started the thread (maintains thread integrity)
    - parent: The specific post being replied to (creates the reply chain)
    
    This function also handles URL detection and creates proper link facets
    so that URLs in the reply text are clickable.
    
    Args:
        client: An authenticated Client instance
        parent_uri: AT URI of the post being replied to
        parent_cid: CID (content hash) of the post being replied to
        root_uri: AT URI of the thread's root post
        root_cid: CID of the thread's root post
        text: The reply text content (max 300 characters)
        
    Returns:
        The created post reference (contains URI and CID)
    """
    # Import models for constructing the reply reference
    from atproto import models
    
    # Create strong references for root and parent
    # Strong references include both URI and CID for content integrity
    root_ref = models.create_strong_ref(
        models.ComAtprotoRepoStrongRef.Main(
            uri=root_uri,
            cid=root_cid
        )
    )
    
    parent_ref = models.create_strong_ref(
        models.ComAtprotoRepoStrongRef.Main(
            uri=parent_uri,
            cid=parent_cid
        )
    )
    
    # Build the reply reference structure
    # This tells Bluesky where this reply fits in the thread hierarchy
    reply_ref = models.AppBskyFeedPost.ReplyRef(
        root=root_ref,
        parent=parent_ref
    )
    
    # Build the text with proper link facets for any URLs
    # This is necessary because send_post() does NOT auto-detect URLs
    # when passed a plain string - it only extracts facets from TextBuilder
    text_builder = build_text_with_facets(text)
    
    # Post the reply using send_post with the TextBuilder
    # When passed a TextBuilder, send_post extracts both the text and facets
    post_ref = client.send_post(
        text=text_builder,
        reply_to=reply_ref
    )
    
    return post_ref


def main():
    """
    Main entry point for the reply script.
    
    Parses command-line arguments, resolves the target post,
    determines the thread structure, and posts the reply.
    """
    # Set up the argument parser with description and examples
    parser = argparse.ArgumentParser(
        description="Post a reply to a Bluesky post",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reply to a post using its web URL
  uv run scripts/reply.py --to https://bsky.app/profile/someone.bsky.social/post/abc123 \\
      --text "Great post!"

  # Reply using an AT Protocol URI
  uv run scripts/reply.py --to "at://did:plc:xxx/app.bsky.feed.post/abc123" \\
      --text "I agree with this!"

  # Short form arguments
  uv run scripts/reply.py -p https://bsky.app/profile/someone/post/abc123 -t "Thanks!"
        """
    )
    
    # Required argument: the post to reply to
    parser.add_argument(
        "--to", "-p",
        required=True,
        dest="parent_post",
        help="The post to reply to: either a bsky.app URL or an AT Protocol URI"
    )
    
    # Required argument: the reply text
    parser.add_argument(
        "--text", "-t",
        required=True,
        help="The text content of the reply (max 300 characters)"
    )
    
    # Parse the command-line arguments
    args = parser.parse_args()
    
    # Validate text length (Bluesky's limit is 300 graphemes)
    if len(args.text) > 300:
        print(f"Error: Reply text is {len(args.text)} characters (max 300)", file=sys.stderr)
        sys.exit(1)
    
    # Get credentials and authenticate
    handle, password = get_credentials()
    client = create_client_and_login(handle, password)
    
    # Parse the post identifier (URL or AT URI) into an AT URI
    parent_uri = parse_post_identifier(client, args.parent_post)
    print(f"Replying to: {parent_uri}")
    
    # Fetch the thread to get the parent's CID and find the root
    thread_response = get_post_thread(client, parent_uri)
    
    # Extract the parent post's CID from the thread response
    parent_cid = thread_response.thread.post.cid
    
    # Find the thread root (walk up the parent chain)
    root_uri, root_cid = find_thread_root(thread_response)
    
    # Log the thread structure for transparency
    if root_uri == parent_uri:
        print("This is a top-level post (replying directly to the thread root)")
    else:
        print(f"Thread root: {root_uri}")
    
    # Post the reply
    post_ref = post_reply(
        client,
        parent_uri=parent_uri,
        parent_cid=parent_cid,
        root_uri=root_uri,
        root_cid=root_cid,
        text=args.text
    )
    
    # Print success message with the new post's details
    print(f"\n✅ Reply posted successfully!")
    print(f"   URI: {post_ref.uri}")
    print(f"   CID: {post_ref.cid}")
    
    # Construct the web URL for viewing the reply
    # Extract the record key from the URI for the web URL
    rkey = post_ref.uri.split("/")[-1]
    print(f"   View at: https://bsky.app/profile/{handle}/post/{rkey}")


if __name__ == "__main__":
    main()
