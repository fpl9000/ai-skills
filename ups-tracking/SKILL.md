---
name: ups-tracking
description: Track UPS packages using valid tracking numbers. Use this skill when the user wants to check the status, location, or delivery information for a UPS package. The script uses the UPS tracking API or web scraping to retrieve real-time package information. Requires a valid UPS tracking number (typically 18 characters, starting with "1Z").
---

# UPS Package Tracking Skill

This skill provides UPS package tracking capabilities via a Python script that retrieves real-time tracking information for UPS shipments.

## Overview

The UPS tracking skill allows the AI agent to:
- Look up package status using a UPS tracking number
- Display delivery status, location, and estimated delivery date
- Show tracking history and package journey
- Support multiple tracking numbers in a single query

## Prerequisites

**Tool Dependency**:
- `uv` - The scripts in this skill require the [uv](https://docs.astral.sh/uv/) package manager/runner. Most cloud-based AI agents have `uv` pre-installed (or they can install it). Local agents should install it via `curl -LsSf https://astral.sh/uv/install.sh | sh` or see the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/).

**Network Access**:
The script requires network access to UPS tracking services:
- `www.ups.com`
- `wwwapps.ups.com`
- `*.ups.com`

If the AI agent has network restrictions, the user may need to whitelist these domains.

## UPS Tracking Number Format

UPS tracking numbers typically follow these formats:
- **1Z tracking numbers**: 18 characters starting with "1Z" (most common)
  - Example: `1Z999AA10123456784`
- **Tracking numbers without "1Z"**: Various formats, typically 10-12 alphanumeric characters

## Available Scripts

### Track Package (`scripts/track.py`)

Retrieve tracking information for one or more UPS packages.

```bash
# Track a single package
uv run scripts/track.py 1Z999AA10123456784

# Track multiple packages
uv run scripts/track.py 1Z999AA10123456784 1Z999AA10123456785

# JSON output for programmatic processing
uv run scripts/track.py --json 1Z999AA10123456784

# Detailed output with full tracking history
uv run scripts/track.py --detailed 1Z999AA10123456784

# Quiet mode (only show delivery status)
uv run scripts/track.py --quiet 1Z999AA10123456784
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `tracking_number` | One or more UPS tracking numbers (required) |
| `--json`, `-j` | Output as JSON instead of human-readable format |
| `--detailed`, `-d` | Show full tracking history with timestamps |
| `--quiet`, `-q` | Show only delivery status (no detailed information) |

**Output Format:**

The script provides:
- **Current Status**: Current location and status of the package
- **Estimated Delivery**: Expected delivery date and time
- **Tracking History**: Chronological list of scan events
- **Package Details**: Weight, service type, and destination (when available)

## Usage Examples

### Basic Tracking

```bash
uv run scripts/track.py 1Z999AA10123456784
```

Output:
```
Tracking Number: 1Z999AA10123456784
Status: In Transit
Current Location: ATLANTA, GA, US
Estimated Delivery: Friday, 01/10/2026 by 7:00 PM
Last Update: January 08, 2026 at 10:30 AM

Recent Activity:
  - Jan 08, 10:30 AM - Departure Scan - ATLANTA, GA, US
  - Jan 08, 08:15 AM - Arrival Scan - ATLANTA, GA, US
  - Jan 07, 06:45 PM - Departure Scan - CHARLOTTE, NC, US
```

### JSON Output

```bash
uv run scripts/track.py --json 1Z999AA10123456784
```

Useful for processing tracking data programmatically or integrating with other tools.

### Multiple Packages

```bash
uv run scripts/track.py 1Z999AA10123456784 1Z999AA10123456785
```

Tracks multiple packages in sequence and displays results for each.

## Common Use Cases

### Quick Status Check

When the user asks: "Where is my UPS package?" or "What's the status of tracking number 1Z999AA10123456784?"

```bash
uv run scripts/track.py --quiet 1Z999AA10123456784
```

### Full Tracking History

When the user wants detailed information about the package journey:

```bash
uv run scripts/track.py --detailed 1Z999AA10123456784
```

### Monitoring Multiple Shipments

When tracking several packages at once:

```bash
uv run scripts/track.py 1Z123 1Z456 1Z789
```

## Error Handling

The script handles common error scenarios:

- **Invalid tracking number**: Clear error message indicating the format issue
- **Package not found**: Indicates the tracking number doesn't exist in UPS system
- **Network errors**: Timeout and connection error handling with retries
- **Rate limiting**: Implements delays between requests when tracking multiple packages

## Privacy & Security

- The script does not store tracking numbers or results
- All queries go directly to UPS tracking services
- No personal information is retained after the query completes
- The user's tracking data is not shared with third parties

## Troubleshooting

### "Tracking number not found"
- Verify the tracking number is correct (check for typos)
- Ensure the package has been picked up by UPS (new labels may not be in the system yet)
- Wait a few hours if the shipping label was just created

### "Network error" or timeouts
- Check internet connectivity
- Verify UPS domains are not blocked by firewall or network restrictions
- The script will retry automatically for transient network issues

### Invalid format errors
- UPS tracking numbers typically start with "1Z" and are 18 characters
- Remove any spaces or special characters from the tracking number
- Some older tracking numbers may use different formats (10-12 characters)

## API Information

This skill uses web scraping of the UPS tracking website, which:
- Does not require API keys or registration
- Works for any valid tracking number
- Provides real-time tracking information
- May be subject to rate limiting for excessive queries

For high-volume tracking needs, users should consider the official UPS Tracking API with proper authentication.
