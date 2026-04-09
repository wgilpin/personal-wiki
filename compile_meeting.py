#!/usr/bin/env python3
"""
compile_meeting.py — Process Granola meeting notes into the BenchSci org wiki.

Usage:
    python compile_meeting.py <path-to-granola-note.md>
    python compile_meeting.py <folder-or-.>            # recurse for all .md files
    python compile_meeting.py <path> --dry-run
    python compile_meeting.py --pending                # print pending-bill.md
    python compile_meeting.py --query "what's going on with LENS?"

Requirements:
    uv add google-genai python-dotenv python-slugify

Environment:
    GEMINI_API_KEY      — for project/theme compilation (API)
    WIKI_DIR            — path to your wiki root (default: ~/wiki/benchsci)
"""

import argparse
import sys
from pathlib import Path

from api import call_api, gather_context
from config import PENDING_FILE, WIKI_DIR
from query import run_query
from wiki import apply_output, ensure_dirs, read_file_safe


def collect_notes(path: Path) -> list[Path]:
    """Return a sorted list of .md files from a file or directory path."""
    if path.is_file():
        return [path]
    if path.is_dir():
        notes = sorted(path.rglob("*.md"))
        if not notes:
            print(f"No .md files found in {path}")
            sys.exit(1)
        return notes
    print(f"ERROR: Not a file or directory: {path}")
    sys.exit(1)


def process_note(note_path: Path, dry_run: bool = False):
    meeting_title = note_path.stem

    if dry_run:
        print(f"  [dry-run] Would process: {note_path}")
        return

    meeting_note = note_path.read_text()

    print(f"\nProcessing: {meeting_title}")

    print("  Loading existing wiki context...")
    context = gather_context()

    print("  Calling API...")
    output = call_api(meeting_note, context)

    print("  Writing wiki updates...")
    apply_output(output, meeting_title)


def main():
    parser = argparse.ArgumentParser(description="BenchSci wiki compiler")
    parser.add_argument("note", nargs="?", help="Path to a meeting note (.md) or folder of notes")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing files")
    parser.add_argument("--pending", action="store_true", help="Print pending-bill.md")
    parser.add_argument("--query", type=str, help="Query the wiki")
    args = parser.parse_args()

    if args.pending:
        content = read_file_safe(PENDING_FILE)
        print(content if content else "No pending items.")
        return

    if args.query:
        run_query(args.query)
        return

    if not args.note:
        parser.print_help()
        sys.exit(1)

    note_path = Path(args.note)
    if not note_path.exists():
        print(f"ERROR: Path not found: {note_path}")
        sys.exit(1)

    ensure_dirs()

    notes = collect_notes(note_path)

    print(f"Wiki dir: {WIKI_DIR}")
    if args.dry_run:
        print("DRY RUN — no files will be written")
    print(f"Found {len(notes)} note(s) to process")

    for note in notes:
        process_note(note, args.dry_run)

    print(f"\nDone. Processed {len(notes)} note(s).")


if __name__ == "__main__":
    main()
