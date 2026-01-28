#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atproto>=0.0.50",
# ]
# ///
"""
Bluesky Post Script
===================
Creates posts on Bluesky with support for:
- Plain text posts
- Posts with images (up to 4)
- Posts with link card embeds

Usage:
    uv run scripts/post.py --text "Hello world!"
    uv run scripts/post.py --text "Check this out" --image photo.jpg
    uv run scripts/post.py --text "Read this" --link-url https://example.com

Environment Variables Required:
    BLUESKY_HANDLE   - Your Bluesky handle (e.g., yourname.bsky.social)
    BLUESKY_PASSWORD - Your Bluesky app password (create in Settings > App Passwords)
"""

import argparse
import os
import re
import sys
from pathlib import Path


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
    # The login() method returns your profile information
    profile = client.login(handle, password)
    
    # Print a confirmation message with the authenticated user's display name
    print(f"Logged in as: {profile.display_name} (@{profile.handle})")
    
    return client


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


def upload_image(client, image_path: str, alt_text: str = ""):
    """
    Upload an image to Bluesky and return the blob reference.
    
    Images must be uploaded separately before they can be attached to posts.
    Bluesky stores the image and returns a "blob" reference that you include
    in your post's embed data.
    
    Args:
        client: An authenticated Client instance
        image_path: Path to the image file to upload
        alt_text: Accessibility description for the image (recommended)
        
    Returns:
        A tuple of (blob_reference, alt_text) for use in post embeds
    """
    # Import the models module for constructing embed objects
    from atproto import models
    
    # Resolve the image path and verify it exists
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        print(f"Error: Image file not found: {image_path}", file=sys.stderr)
        sys.exit(1)
    
    # Read the image file as binary data
    # The entire file is loaded into memory, so be mindful of file sizes
    with open(path, "rb") as f:
        image_data = f.read()
    
    # Determine the MIME type based on file extension
    # Bluesky accepts JPEG, PNG, and WebP images
    suffix = path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(suffix, "image/jpeg")
    
    # Upload the image blob to the server
    # This returns a BlobRef that can be used in post embeds
    upload_response = client.upload_blob(image_data, mime_type)
    
    print(f"Uploaded image: {path.name} ({len(image_data)} bytes)")
    
    # Return the blob reference along with its alt text
    return upload_response.blob, alt_text


def create_post_with_images(client, text: str, images: list):
    """
    Create a post with one or more images attached.
    
    Bluesky supports up to 4 images per post. Each image requires
    a blob reference (from upload_image) and optional alt text.
    
    Args:
        client: An authenticated Client instance
        text: The post text content
        images: List of tuples, each containing (blob_ref, alt_text)
        
    Returns:
        The created post reference (contains URI and CID)
    """
    # Import models for constructing the embed structure
    from atproto import models
    
    # Bluesky limits posts to 4 images maximum
    if len(images) > 4:
        print("Warning: Bluesky only supports up to 4 images per post", file=sys.stderr)
        print("Only the first 4 images will be included", file=sys.stderr)
        images = images[:4]
    
    # Build the list of image objects for the embed
    # Each image needs an Image object with the blob and alt text
    image_objects = []
    for blob_ref, alt_text in images:
        # Create an Image object with the blob reference and alt text
        image_obj = models.AppBskyEmbedImages.Image(
            image=blob_ref,
            alt=alt_text or "",  # Alt text is required but can be empty
        )
        image_objects.append(image_obj)
    
    # Create the images embed container
    # This wraps the list of images in the proper structure
    embed = models.AppBskyEmbedImages.Main(images=image_objects)
    
    # Build the text with proper link facets for any URLs
    text_builder = build_text_with_facets(text)
    
    # Send the post with the images embed
    post_ref = client.send_post(text=text_builder, embed=embed)
    
    return post_ref


def create_post_with_link_card(client, text: str, url: str, title: str = "", description: str = ""):
    """
    Create a post with an external link card embed.
    
    Link cards show a preview of the linked content, similar to how
    links appear on Twitter/X. The title and description are optional
    but recommended for better presentation.
    
    Args:
        client: An authenticated Client instance
        text: The post text content
        url: The URL to embed as a link card
        title: Title text for the link card (optional)
        description: Description text for the link card (optional)
        
    Returns:
        The created post reference (contains URI and CID)
    """
    # Import models for constructing the embed structure
    from atproto import models
    
    # Create the External object with link card details
    # The URI is required; title and description are optional but improve UX
    external = models.AppBskyEmbedExternal.External(
        uri=url,
        title=title or url,  # Use URL as fallback title
        description=description or "",
    )
    
    # Wrap the External object in the Main container
    embed = models.AppBskyEmbedExternal.Main(external=external)
    
    # Build the text with proper link facets for any URLs
    text_builder = build_text_with_facets(text)
    
    # Send the post with the link card embed
    post_ref = client.send_post(text=text_builder, embed=embed)
    
    return post_ref


def create_text_post(client, text: str):
    """
    Create a simple text-only post.
    
    This is the most basic type of post - just text content
    with no embeds or attachments. URLs in the text will be
    automatically detected and made clickable.
    
    Args:
        client: An authenticated Client instance
        text: The post text content (max 300 characters)
        
    Returns:
        The created post reference (contains URI and CID)
    """
    # Build the text with proper link facets for any URLs
    # This is necessary because send_post() does NOT auto-detect URLs
    # when passed a plain string - it only extracts facets from TextBuilder
    text_builder = build_text_with_facets(text)
    
    # send_post handles:
    # 1. Creating the post record with proper timestamps
    # 2. Extracting facets from the TextBuilder (mentions, links, tags)
    # 3. Submitting to the user's PDS
    post_ref = client.send_post(text=text_builder)
    
    return post_ref


def main():
    """
    Main entry point for the posting script.
    
    Parses command-line arguments and creates the appropriate type of post
    based on the provided options.
    """
    # Set up the argument parser with a description
    parser = argparse.ArgumentParser(
        description="Post to Bluesky with optional images or link cards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple text post
  uv run scripts/post.py --text "Hello, Bluesky!"

  # Post with an image
  uv run scripts/post.py --text "Look at this!" --image photo.jpg

  # Post with multiple images
  uv run scripts/post.py --text "Photos from today" \\
      --image pic1.jpg --image pic2.jpg --image pic3.jpg

  # Post with image and alt text
  uv run scripts/post.py --text "My cat" \\
      --image cat.jpg --alt "A fluffy orange cat sleeping on a couch"

  # Post with a link card
  uv run scripts/post.py --text "Check out this article" \\
      --link-url "https://example.com/article" \\
      --link-title "Amazing Article" \\
      --link-description "An interesting read about technology"
        """
    )
    
    # Required argument: the post text
    parser.add_argument(
        "--text", "-t",
        required=True,
        help="The text content of the post (max 300 characters)"
    )
    
    # Optional: one or more images to attach
    parser.add_argument(
        "--image", "-i",
        action="append",  # Allows multiple --image flags
        dest="images",
        help="Path to an image file to attach (can be specified up to 4 times)"
    )
    
    # Optional: alt text for images (applied to all images if single value)
    parser.add_argument(
        "--alt", "-a",
        action="append",
        dest="alt_texts",
        help="Alt text for images (specify once per image, in order)"
    )
    
    # Optional: link card URL
    parser.add_argument(
        "--link-url",
        help="URL for a link card embed"
    )
    
    # Optional: link card title
    parser.add_argument(
        "--link-title",
        help="Title for the link card (optional)"
    )
    
    # Optional: link card description
    parser.add_argument(
        "--link-description",
        help="Description for the link card (optional)"
    )
    
    # Parse the command-line arguments
    args = parser.parse_args()
    
    # Validate that we don't have both images and link card
    # Bluesky posts can have only one type of embed
    if args.images and args.link_url:
        print("Error: Cannot include both images and a link card in the same post", file=sys.stderr)
        print("Please choose one or the other", file=sys.stderr)
        sys.exit(1)
    
    # Get credentials from environment and authenticate
    handle, password = get_credentials()
    client = create_client_and_login(handle, password)
    
    # Determine which type of post to create based on arguments
    if args.images:
        # Post with images
        # Match up images with their alt texts
        alt_texts = args.alt_texts or []
        
        # Upload each image and collect the blob references
        uploaded_images = []
        for i, image_path in enumerate(args.images):
            # Get the alt text for this image (if provided)
            alt_text = alt_texts[i] if i < len(alt_texts) else ""
            
            # Upload the image and store the blob reference
            blob_ref, alt = upload_image(client, image_path, alt_text)
            uploaded_images.append((blob_ref, alt))
        
        # Create the post with all uploaded images
        post_ref = create_post_with_images(client, args.text, uploaded_images)
        
    elif args.link_url:
        # Post with link card
        post_ref = create_post_with_link_card(
            client,
            args.text,
            args.link_url,
            args.link_title or "",
            args.link_description or ""
        )
        
    else:
        # Simple text post
        post_ref = create_text_post(client, args.text)
    
    # Print success message with post details
    print(f"\n✅ Post created successfully!")
    print(f"   URI: {post_ref.uri}")
    print(f"   CID: {post_ref.cid}")
    
    # Construct the web URL for viewing the post
    # The URI format is: at://did:plc:xxx/app.bsky.feed.post/rkey
    # We need to extract the rkey (record key) for the web URL
    rkey = post_ref.uri.split("/")[-1]
    print(f"   View at: https://bsky.app/profile/{handle}/post/{rkey}")


if __name__ == "__main__":
    main()
