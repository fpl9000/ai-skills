#!/usr/bin/env python3
"""
Save Claude Code Transcript

A wrapper script for Simon Willison's claude-code-transcripts tool, designed 
to be run from within an active Claude Code session to export the current 
conversation as shareable HTML pages.

This script:
1. Locates the most recent Claude Code session in ~/.claude/projects/
2. Invokes claude-code-transcripts via uvx (or pip fallback)
3. Generates paginated HTML transcript pages
4. Optionally publishes to GitHub Gist for easy sharing

Usage:
    python save_transcript.py                    # Save to temp dir, open in browser
    python save_transcript.py --output ./out     # Save to specific directory
    python save_transcript.py --gist             # Publish to GitHub Gist
    python save_transcript.py -o ./out --gist    # Both: local save AND gist

Requirements:
    - uv (preferred) or pip with claude-code-transcripts installed
    - gh CLI (only for --gist option)

Author: Generated for use with Claude Code
License: Apache 2.0 (same as claude-code-transcripts)
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_uv_or_pip():
    """
    Locate the uv command, falling back to pip if uv is not available.
    
    Returns:
        tuple: (command_type, executable_path) where command_type is 'uv' or 'pip'
               Returns (None, None) if neither is found.
    
    The function checks:
    1. If 'uv' is in PATH (preferred - allows uvx without installation)
    2. If 'pip' is in PATH (fallback - requires package installation)
    """
    # First, try to find uv in PATH
    # uv is preferred because it allows running via uvx without permanent installation
    uv_path = shutil.which('uv')
    if uv_path:
        return ('uv', uv_path)
    
    # Fallback: check for pip
    # If pip is available, we can install claude-code-transcripts and run it
    pip_path = shutil.which('pip') or shutil.which('pip3')
    if pip_path:
        return ('pip', pip_path)
    
    # Neither found - return None to signal error
    return (None, None)


def find_gh_cli():
    """
    Locate the GitHub CLI (gh) for gist publishing.
    
    Returns:
        str or None: Path to gh executable, or None if not found.
    
    The gh CLI is required only for the --gist option.
    Users can install it via:
        - macOS: brew install gh
        - Linux: See https://cli.github.com/
        - Windows: winget install GitHub.cli
    """
    return shutil.which('gh')


def get_recent_sessions(limit=10):
    """
    Find recent Claude Code session files from the local projects directory.
    
    Args:
        limit: Maximum number of sessions to return (default 10)
    
    Returns:
        list: List of Path objects pointing to session JSONL files,
              sorted by modification time (most recent first).
    
    Claude Code stores session data in ~/.claude/projects/ as JSONL files.
    Each project directory can contain multiple session files.
    The file naming convention is typically session-related identifiers.
    """
    # Define the base directory where Claude Code stores project sessions
    # This is the standard location on macOS/Linux
    claude_projects_dir = Path.home() / '.claude' / 'projects'
    
    # Check if the directory exists
    # If not, user may not have any Claude Code sessions yet
    if not claude_projects_dir.exists():
        print(f"Warning: Claude projects directory not found: {claude_projects_dir}")
        return []
    
    # Find all JSONL files in the projects directory tree
    # Claude Code stores sessions as JSONL (JSON Lines) format
    # Each line in the file is a separate JSON object representing a message/event
    session_files = list(claude_projects_dir.rglob('*.jsonl'))
    
    # Sort by modification time, most recent first
    # This ensures we get the most recent/active session at the top
    session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    # Return only the requested number of sessions
    return session_files[:limit]


def run_transcript_tool(session_path=None, output_dir=None, gist=False, 
                        auto_name=False, include_json=False, open_browser=True):
    """
    Execute the claude-code-transcripts tool with the specified options.
    
    Args:
        session_path: Path to specific session file (optional, uses most recent if None)
        output_dir: Directory to save HTML output (optional, uses temp dir if None)
        gist: If True, publish to GitHub Gist
        auto_name: If True, auto-generate output subdirectory name from session ID
        include_json: If True, include original JSON/JSONL in output
        open_browser: If True, open the generated HTML in default browser
    
    Returns:
        int: Return code from the subprocess (0 = success)
    
    This function builds and executes the appropriate command based on whether
    uv (uvx) or pip is available.
    """
    # Determine which package manager/runner to use
    cmd_type, cmd_path = find_uv_or_pip()
    
    # Handle case where neither uv nor pip is available
    if cmd_type is None:
        print("Error: Neither 'uv' nor 'pip' found in PATH.")
        print("\nTo install uv (recommended):")
        print("  curl -LsSf https://astral.sh/uv/install.sh | sh")
        print("\nOr ensure pip is available in your Python environment.")
        return 1
    
    # Build the command to execute
    # Using uvx allows running without permanent installation
    # Using pip requires the package to be installed first
    if cmd_type == 'uv':
        # uvx runs the tool directly without needing to install it
        # This is the cleanest approach as it doesn't pollute the global environment
        cmd = ['uvx', 'claude-code-transcripts']
    else:
        # For pip, we need to ensure the package is installed
        # Check if claude-code-transcripts is already installed
        try:
            subprocess.run(
                [sys.executable, '-c', 'import claude_code_transcripts'],
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError:
            # Package not installed - install it now
            print("Installing claude-code-transcripts via pip...")
            subprocess.run(
                [cmd_path, 'install', 'claude-code-transcripts'],
                check=True
            )
        # Run via Python module execution
        cmd = [sys.executable, '-m', 'claude_code_transcripts']
    
    # Determine which subcommand to use based on inputs
    # The tool has three main modes: local, web, and json
    if session_path:
        # If a specific session file is provided, use 'json' subcommand
        # This directly processes a JSON/JSONL file
        cmd.append('json')
        cmd.append(str(session_path))
    else:
        # Default to 'local' which shows an interactive picker
        # of recent sessions from ~/.claude/projects/
        cmd.append('local')
    
    # Add output directory option if specified
    # Without this, output goes to a temp directory
    if output_dir:
        cmd.extend(['--output', str(output_dir)])
    
    # Add auto-naming flag if requested
    # This creates a subdirectory named after the session ID
    if auto_name:
        cmd.append('--output-auto')
    
    # Add gist publishing flag if requested
    # Requires gh CLI to be installed and authenticated
    if gist:
        # Verify gh CLI is available before adding the flag
        if not find_gh_cli():
            print("Warning: GitHub CLI (gh) not found. --gist option requires gh.")
            print("Install: brew install gh (macOS) or see https://cli.github.com/")
            print("Then run: gh auth login")
            # Continue without gist - user can still get local output
        else:
            cmd.append('--gist')
    
    # Add flag to include original JSON in output
    # Useful for archiving the raw session data alongside HTML
    if include_json:
        cmd.append('--json')
    
    # Add --open flag to open in browser
    # This is the default behavior when no output directory is specified
    if open_browser and not output_dir:
        cmd.append('--open')
    
    # Print the command being executed for transparency
    # This helps users understand what's happening and debug issues
    print(f"Running: {' '.join(cmd)}")
    print()
    
    # Execute the command
    # We use subprocess.run to wait for completion and capture the return code
    result = subprocess.run(cmd)
    
    return result.returncode


def main():
    """
    Main entry point for the save_transcript script.
    
    Parses command-line arguments and invokes the transcript tool
    with the appropriate options.
    """
    # Set up argument parser with descriptive help text
    parser = argparse.ArgumentParser(
        description='Save the current Claude Code session as an HTML transcript.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Interactive picker, opens in browser
  %(prog)s --output ./transcript    # Save to specific directory
  %(prog)s --gist                   # Publish to GitHub Gist
  %(prog)s -o ./out --gist          # Save locally AND publish to gist
  %(prog)s --session-id abc123      # Export specific session by ID

Note: This script wraps Simon Willison's claude-code-transcripts tool.
See https://github.com/simonw/claude-code-transcripts for more details.
        """
    )
    
    # Output directory option
    # If not specified, output goes to a temp directory and opens in browser
    parser.add_argument(
        '--output', '-o',
        type=str,
        metavar='DIR',
        help='Output directory for HTML files (default: temp directory)'
    )
    
    # Gist publishing option
    # Uploads the generated HTML to GitHub Gist for easy sharing
    parser.add_argument(
        '--gist',
        action='store_true',
        help='Upload to GitHub Gist and output preview URL (requires gh CLI)'
    )
    
    # Auto-naming option
    # Creates a subdirectory named after the session ID within the output directory
    parser.add_argument(
        '--auto-name', '-a',
        action='store_true',
        help='Auto-name output subdirectory based on session ID'
    )
    
    # Include JSON option
    # Copies the original session file to the output directory
    parser.add_argument(
        '--include-json',
        action='store_true',
        help='Include original session JSON/JSONL in output directory'
    )
    
    # Open in browser option
    # Automatically opens the generated HTML in the default browser
    parser.add_argument(
        '--open',
        action='store_true',
        default=True,
        help='Open generated HTML in browser (default: True when no --output)'
    )
    
    # Specific session ID option
    # Allows exporting a specific session rather than using the picker
    parser.add_argument(
        '--session-id',
        type=str,
        metavar='ID',
        help='Specific session ID to export (default: interactive picker)'
    )
    
    # List sessions option
    # Shows recent sessions without processing any
    parser.add_argument(
        '--list',
        action='store_true',
        help='List recent sessions and exit (do not process)'
    )
    
    # Parse command line arguments
    args = parser.parse_args()
    
    # Handle --list option: show recent sessions and exit
    if args.list:
        print("Recent Claude Code sessions:")
        print("-" * 60)
        sessions = get_recent_sessions(limit=20)
        if not sessions:
            print("No sessions found in ~/.claude/projects/")
            print("Make sure you have run Claude Code at least once.")
            return 1
        
        # Display each session with its modification time
        for i, session in enumerate(sessions, 1):
            # Get the modification time for display
            mtime = session.stat().st_mtime
            from datetime import datetime
            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
            
            # Extract project name from path for context
            # Path structure: ~/.claude/projects/<project-hash>/<session>.jsonl
            project_part = session.parent.name[:20]  # Truncate long hashes
            
            print(f"{i:2}. [{mtime_str}] {project_part}/.../{session.name}")
        
        return 0
    
    # Find specific session file if --session-id was provided
    session_path = None
    if args.session_id:
        # Search for a session file containing the specified ID
        sessions = get_recent_sessions(limit=100)
        for session in sessions:
            if args.session_id in session.name or args.session_id in str(session):
                session_path = session
                print(f"Found session: {session}")
                break
        
        if not session_path:
            print(f"Error: No session found matching ID: {args.session_id}")
            print("Use --list to see available sessions.")
            return 1
    
    # Run the transcript tool with collected options
    return run_transcript_tool(
        session_path=session_path,
        output_dir=args.output,
        gist=args.gist,
        auto_name=args.auto_name,
        include_json=args.include_json,
        open_browser=args.open
    )


# Standard Python idiom: only run main() if this script is executed directly
# (not imported as a module)
if __name__ == '__main__':
    sys.exit(main())
