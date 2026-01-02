---
name: bluesky
description: Read from and post to Bluesky social network using the AT Protocol. Use this skill when the user wants to interact with Bluesky including posting text/images/links, reading their timeline, searching posts, viewing profiles, following/unfollowing users, or checking notifications. All scripts use PEP 723 inline metadata for dependencies and run via `uv run`. Requires BLUESKY_HANDLE and BLUESKY_PASSWORD environment variables.
---

# Bluesky Skill

Interact with Bluesky social network via the AT Protocol Python SDK (`atproto`).

## Prerequisites

**Environment Variables** (must be set before running any script):
- `BLUESKY_HANDLE` - Your Bluesky handle (e.g., `yourname.bsky.social`)
- `BLUESKY_PASSWORD` - Your Bluesky App Password (create in Settings > App Passwords)

**Important**: Use an App Password, not your main account password. App Passwords can be revoked individually if compromised.

### Domains Accessed by the Scripts

The scripts in this skill access the following domains:

- bsky.social
- bsky.app
- bsky.network
- public.api.bsky.app
- *.bsky.network

If this skill is used in the AI's cloud-based remote environemnt, these domains may need to be enabled in the AIs network egress settings.  This is definitely the case for Claude, and may be for others as well.

## Available Scripts

All scripts include PEP 723 inline metadata declaring their dependencies. Just run with `uv run`—no manual dependency installation or `--with` flags needed.

### Post to Bluesky (`scripts/post.py`)

Create posts with text, images, or link cards.

```bash
# Simple text post
uv run scripts/post.py --text "Hello, Bluesky!"

# Post with image
uv run scripts/post.py --text "Check this out" --image photo.jpg

# Post with multiple images (up to 4)
uv run scripts/post.py --text "Photos" --image a.jpg --image b.jpg

# Post with image and alt text
uv run scripts/post.py --text "My cat" --image cat.jpg --alt "Orange cat sleeping"

# Post with link card
uv run scripts/post.py --text "Read this" \
    --link-url "https://example.com" \
    --link-title "Article Title" \
    --link-description "Description text"
```

### Read Timeline (`scripts/read_timeline.py`)

View posts from accounts you follow.

```bash
# Default (25 posts)
uv run scripts/read_timeline.py

# More posts
uv run scripts/read_timeline.py --limit 50

# JSON output
uv run scripts/read_timeline.py --json

# Paginate
uv run scripts/read_timeline.py --cursor "cursor_string"
```

### Search Posts (`scripts/search.py`)

Find posts by keywords or hashtags.

```bash
# Keyword search
uv run scripts/search.py "python programming"

# Hashtag search
uv run scripts/search.py "#machinelearning"

# More results with auto-pagination
uv run scripts/search.py "topic" --limit 100 --all

# JSON output
uv run scripts/search.py "query" --json
```

### View Profiles (`scripts/profile.py`)

View profile information for any user.

```bash
# Your own profile
uv run scripts/profile.py

# Another user
uv run scripts/profile.py someone.bsky.social

# JSON output
uv run scripts/profile.py --json
```

### Follow/Unfollow (`scripts/follow.py`)

Manage your social connections.

```bash
# Follow a user
uv run scripts/follow.py someone.bsky.social

# Unfollow a user
uv run scripts/follow.py --unfollow someone.bsky.social

# List who you follow
uv run scripts/follow.py --list

# List your followers
uv run scripts/follow.py --list --followers

# List another user's follows
uv run scripts/follow.py --list someone.bsky.social
```

### Notifications (`scripts/notifications.py`)

View and manage your notifications.

```bash
# View notifications
uv run scripts/notifications.py

# More notifications
uv run scripts/notifications.py --limit 50

# Just show unread count
uv run scripts/notifications.py --count

# Mark all as read
uv run scripts/notifications.py --mark-read

# JSON output
uv run scripts/notifications.py --json
```

## Common Patterns

### Setting Credentials

```bash
# Set for current session
export BLUESKY_HANDLE="yourname.bsky.social"
export BLUESKY_PASSWORD="your-app-password"

# Or inline with command
BLUESKY_HANDLE="yourname.bsky.social" BLUESKY_PASSWORD="pass" uv run scripts/post.py --text "Hello"
```

### JSON Output for Processing

All scripts support `--json` for machine-readable output:

```bash
# Get timeline as JSON and extract first post
uv run scripts/read_timeline.py --json | jq '.posts[0]'

# Search and count results
uv run scripts/search.py "topic" --json | jq '.count'
```

### Pagination

Scripts that return lists support cursor-based pagination:

```bash
# First page
uv run scripts/read_timeline.py --json > page1.json

# Get cursor from response, then fetch next page
CURSOR=$(jq -r '.cursor' page1.json)
uv run scripts/read_timeline.py --cursor "$CURSOR" --json > page2.json
```

## Key Concepts

- **Handle**: Your username (e.g., `user.bsky.social`)
- **DID**: Decentralized Identifier—permanent unique ID (handles can change, DIDs don't)
- **URI**: Resource identifier for posts/records (format: `at://did/collection/rkey`)
- **CID**: Content hash identifier for specific versions of records
- **App Password**: Revocable credential for API access (recommended over main password)

## Error Handling

Scripts exit with non-zero status on errors. Common issues:
- Missing credentials: Set `BLUESKY_HANDLE` and `BLUESKY_PASSWORD`
- Invalid handle: Verify the handle exists on Bluesky
- Rate limits: The API has rate limits; space out bulk operations
- Image format: Only JPEG, PNG, and WebP are supported
