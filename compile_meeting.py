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
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from slugify import slugify

from api import apply_corrections, call_api, gather_context
from config import PENDING_FILE, PROCESSED_FILE, WIKI_DIR, load_corrections
from query import run_query
from wiki import apply_output, ensure_dirs, read_file_safe


def file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_processed() -> dict:
    """Load the processed-files manifest. Returns empty dict if missing."""
    if PROCESSED_FILE.exists():
        return json.loads(PROCESSED_FILE.read_text())
    return {}


def save_processed(manifest: dict):
    """Write the processed-files manifest to disk."""
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(json.dumps(manifest, indent=2) + "\n")


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


def process_note(note_path: Path, corrections: dict[str, str], dry_run: bool = False):
    meeting_title = note_path.stem

    if dry_run:
        print(f"  [dry-run] Would process: {note_path}")
        return

    meeting_note = note_path.read_text()

    print(f"\nProcessing: {meeting_title}")

    print("  Loading existing wiki context...")
    context = gather_context()

    print("  Calling API...")
    try:
        output = call_api(meeting_note, context, corrections)
    except RuntimeError as e:
        print(f"  ⚠ Skipping: {e}")
        return

    print("  Writing wiki updates...")
    apply_output(output, meeting_title)


def run_apply_corrections(corrections: dict[str, str], dry_run: bool = False):
    """Apply corrections to all existing wiki files and folder names."""
    if not corrections:
        print("No corrections defined in corrections.json")
        return

    slug_corrections = {}
    for wrong, right in corrections.items():
        wrong_slug = slugify(wrong)
        right_slug = slugify(right)
        if wrong_slug != right_slug:
            slug_corrections[wrong_slug] = right_slug

    # Pass 1: Update file contents
    changed_files = 0
    for md_file in sorted(WIKI_DIR.rglob("*.md")):
        original = md_file.read_text()
        updated = apply_corrections(original, corrections)
        # Also fix slug references (e.g., path references in index.md)
        updated = apply_corrections(updated, slug_corrections)
        if updated != original:
            changed_files += 1
            rel = md_file.relative_to(WIKI_DIR)
            if dry_run:
                print(f"  [dry-run] Would update content: {rel}")
            else:
                md_file.write_text(updated)
                print(f"  updated: {rel}")

    # Pass 2: Rename directories (deepest first to avoid breaking parent paths)
    renamed_dirs = 0
    for d in sorted(WIKI_DIR.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not d.is_dir() or d.name.startswith("."):
            continue
        for wrong_slug, right_slug in slug_corrections.items():
            if wrong_slug in d.name:
                new_name = d.name.replace(wrong_slug, right_slug)
                new_path = d.parent / new_name
                renamed_dirs += 1
                if dry_run:
                    print(f"  [dry-run] Would rename: {d.relative_to(WIKI_DIR)} → {new_path.relative_to(WIKI_DIR)}")
                else:
                    d.rename(new_path)
                    print(f"  renamed: {d.relative_to(WIKI_DIR)} → {new_path.relative_to(WIKI_DIR)}")
                break

    # Pass 3: Update .obsidian/workspace.json if present
    workspace = WIKI_DIR / ".obsidian" / "workspace.json"
    if workspace.exists():
        original = workspace.read_text()
        updated = apply_corrections(original, slug_corrections)
        if updated != original:
            if dry_run:
                print(f"  [dry-run] Would update: .obsidian/workspace.json")
            else:
                workspace.write_text(updated)
                print(f"  updated: .obsidian/workspace.json")

    print(f"\nDone. Updated {changed_files} file(s), renamed {renamed_dirs} directory(ies).")


def main():
    parser = argparse.ArgumentParser(description="BenchSci wiki compiler")
    parser.add_argument("note", nargs="?", help="Path to a meeting note (.md) or folder of notes")
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing files")
    parser.add_argument("--pending", action="store_true", help="Print pending-bill.md")
    parser.add_argument("--query", type=str, help="Query the wiki")
    parser.add_argument("--apply-corrections", action="store_true", help="Apply corrections.json to existing wiki files and folders")
    parser.add_argument("--reprocess-all", action="store_true", help="Reprocess all files, ignoring the processed-files manifest")
    parser.add_argument("--backlinks", action="store_true", help="Rebuild backlinks across all wiki pages")
    args = parser.parse_args()

    if args.pending:
        content = read_file_safe(PENDING_FILE)
        print(content if content else "No pending items.")
        return

    if args.query:
        run_query(args.query)
        return

    if args.apply_corrections:
        corrections = load_corrections()
        run_apply_corrections(corrections, args.dry_run)
        return

    if args.backlinks:
        from backlinks import rebuild_all_backlinks
        rebuild_all_backlinks(args.dry_run)
        return

    if not args.note:
        parser.print_help()
        sys.exit(1)

    note_path = Path(args.note)
    if not note_path.exists():
        print(f"ERROR: Path not found: {note_path}")
        sys.exit(1)

    ensure_dirs()

    corrections = load_corrections()
    notes = collect_notes(note_path)
    manifest = load_processed()

    print(f"Wiki dir: {WIKI_DIR}")
    if args.dry_run:
        print("DRY RUN — no files will be written")
    print(f"Found {len(notes)} note(s) to process")

    skipped = 0
    processed = 0
    for note in notes:
        note_key = str(note.resolve())
        h = file_hash(note)
        entry = manifest.get(note_key)
        if not args.reprocess_all and entry and entry.get("content_hash") == h:
            skipped += 1
            continue

        process_note(note, corrections, args.dry_run)
        processed += 1

        if not args.dry_run:
            manifest[note_key] = {
                "content_hash": h,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_processed(manifest)

    if skipped:
        print(f"Skipped {skipped} already-processed note(s)")
    print(f"\nDone. Processed {processed} note(s).")


if __name__ == "__main__":
    main()
