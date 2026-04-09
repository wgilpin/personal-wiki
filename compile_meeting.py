#!/usr/bin/env python3
"""
compile_meeting.py — Process a Granola meeting note into the BenchSci org wiki.

Usage:
    python compile_meeting.py <path-to-granola-note.md>
    python compile_meeting.py <path-to-granola-note.md> --dry-run
    python compile_meeting.py --pending          # print pending-bill.md
    python compile_meeting.py --query "what's going on with LENS?"

Requirements:
    uv add google-genai python-dotenv python-slugify

Environment:
    GEMINI_API_KEY      — for project/theme compilation (API)
    WIKI_DIR            — path to your wiki root (default: ~/wiki/benchsci)
"""

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WIKI_DIR = Path(os.environ.get("WIKI_DIR", Path.home() / "wiki" / "benchsci"))
PROJECTS_DIR = WIKI_DIR / "projects"
THEMES_DIR = WIKI_DIR / "themes"
PEOPLE_DIR = WIKI_DIR / "people"
PENDING_FILE = WIKI_DIR / "pending-bill.md"
INDEX_FILE = WIKI_DIR / "index.md"
SCHEMA_FILE = Path(__file__).parent / "schema.md"

API_MODEL = "gemini-2.0-flash"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def timed_generate(label: str, **kwargs):
    t0 = time.perf_counter()
    response = client.models.generate_content(**kwargs)
    elapsed = time.perf_counter() - t0
    print(f"  [{label}] {elapsed:.1f}s")
    return response


# ---------------------------------------------------------------------------
# Output schema (Pydantic)
# ---------------------------------------------------------------------------

class Snapshot(BaseModel):
    path: str
    content: str

class ProjectSummary(BaseModel):
    path: str
    updated_content: str

class ThemeUpdate(BaseModel):
    path: str
    updated_content: str

class PendingItem(BaseModel):
    action: str
    project: str
    date_captured: str
    source_meeting: str

class PeopleUpdate(BaseModel):
    path: str
    updated_content: str

class IndexUpdate(BaseModel):
    path: str
    one_line_summary: str

class WikiOutput(BaseModel):
    snapshots: list[Snapshot] = []
    project_summaries: list[ProjectSummary] = []
    theme_updates: list[ThemeUpdate] = []
    pending_bill: list[PendingItem] = []
    people_updates: list[PeopleUpdate] = []
    index_updates: list[IndexUpdate] = []

class PathList(BaseModel):
    paths: list[str]

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def load_schema() -> str:
    if SCHEMA_FILE.exists():
        return SCHEMA_FILE.read_text()
    return "(schema.md not found — place schema.md alongside this script)"


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def ensure_dirs():
    for d in [PROJECTS_DIR, THEMES_DIR, PEOPLE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    WIKI_DIR.mkdir(parents=True, exist_ok=True)


def read_file_safe(path: Path) -> str:
    """Return file content or empty string if not found."""
    if path.exists():
        return path.read_text()
    return ""


def write_file(path: Path, content: str, dry_run: bool = False):
    if dry_run:
        print(f"\n{'='*60}")
        print(f"WOULD WRITE: {path}")
        print('='*60)
        print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"  wrote: {path.relative_to(WIKI_DIR)}")


# ---------------------------------------------------------------------------
# Index maintenance
# ---------------------------------------------------------------------------

def update_index(updates: list[IndexUpdate], dry_run: bool = False):
    """Maintain index.md as a simple markdown table."""
    index_content = read_file_safe(INDEX_FILE)

    entries: dict[str, dict] = {}
    for line in index_content.splitlines():
        if line.startswith("|") and not line.startswith("| Path") and not line.startswith("| ---"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3:
                entries[parts[0]] = {"summary": parts[1], "updated": parts[2]}

    today = date.today().isoformat()
    for u in updates:
        entries[u.path] = {"summary": u.one_line_summary, "updated": today}

    lines = [
        "# Wiki Index",
        "",
        "| Path | Summary | Last Updated |",
        "| --- | --- | --- |",
    ]
    for path, meta in sorted(entries.items()):
        lines.append(f"| {path} | {meta['summary']} | {meta['updated']} |")

    write_file(INDEX_FILE, "\n".join(lines) + "\n", dry_run)


# ---------------------------------------------------------------------------
# Pending bill maintenance
# ---------------------------------------------------------------------------

def append_pending(items: list[PendingItem], dry_run: bool = False):
    """Append new action items to pending-bill.md."""
    if not items:
        return

    existing = read_file_safe(PENDING_FILE)
    if not existing:
        existing = "# Pending — Bill\n\nActions only Bill owns. Review weekly.\n\n"

    new_lines = [
        f"- [ ] {item.action} — {item.project} (captured {item.date_captured}, from: {item.source_meeting})"
        for item in items
    ]

    updated = existing.rstrip() + "\n" + "\n".join(new_lines) + "\n"
    write_file(PENDING_FILE, updated, dry_run)


# ---------------------------------------------------------------------------
# People updates
# ---------------------------------------------------------------------------

def apply_people_updates(updates: list[PeopleUpdate], dry_run: bool = False):
    """Write or update individual people pages."""
    for update in updates:
        write_file(WIKI_DIR / update.path, update.updated_content, dry_run)


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_api(meeting_note: str, existing_context: dict) -> WikiOutput:
    """Call Gemini API with structured output. Returns a validated WikiOutput."""
    schema = load_schema()

    context_lines = ["## Existing Wiki Content\n"]
    for path, content in existing_context.items():
        if content:
            context_lines.append(f"### {path}\n```\n{content}\n```\n")

    context_block = "\n".join(context_lines) if existing_context else "No existing wiki content yet."

    system_prompt = f"{schema}\n\n{context_block}"

    user_message = f"Process this meeting note and return the JSON output as specified in the schema.\n\n{meeting_note}"

    response = timed_generate(
        "compile",
        model=API_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=WikiOutput,
        ),
    )

    return WikiOutput.model_validate_json(response.text)


# ---------------------------------------------------------------------------
# Gather existing context
# ---------------------------------------------------------------------------

def gather_context(output: dict) -> dict:
    """Load all existing project summaries and theme pages to provide as context."""
    context = {}

    for summary_path in PROJECTS_DIR.glob("*/summary.md"):
        rel = str(summary_path.relative_to(WIKI_DIR))
        context[rel] = summary_path.read_text()

    for theme_path in THEMES_DIR.glob("*.md"):
        rel = str(theme_path.relative_to(WIKI_DIR))
        context[rel] = theme_path.read_text()

    for person_path in PEOPLE_DIR.glob("*.md"):
        rel = str(person_path.relative_to(WIKI_DIR))
        context[rel] = person_path.read_text()

    return context


# ---------------------------------------------------------------------------
# Apply output
# ---------------------------------------------------------------------------

def apply_output(output: WikiOutput, meeting_title: str, dry_run: bool = False):
    snapshot_index_updates = []

    # 1. Snapshots
    for snap in output.snapshots:
        path = WIKI_DIR / snap.path
        write_file(path, snap.content, dry_run)
        snapshot_index_updates.append(IndexUpdate(
            path=snap.path,
            one_line_summary=f"Snapshot from {meeting_title}",
        ))

    # 2. Project summaries
    for proj in output.project_summaries:
        write_file(WIKI_DIR / proj.path, proj.updated_content, dry_run)

    # 3. Theme updates
    for theme in output.theme_updates:
        write_file(WIKI_DIR / theme.path, theme.updated_content, dry_run)

    # 4. Pending bill
    append_pending(output.pending_bill, dry_run)

    # 5. People updates
    apply_people_updates(output.people_updates, dry_run)

    # 6. Index
    all_index_updates = snapshot_index_updates + output.index_updates
    if all_index_updates:
        update_index(all_index_updates, dry_run)


# ---------------------------------------------------------------------------
# Query mode
# ---------------------------------------------------------------------------

def run_query(question: str):
    """Answer a question using the wiki index and relevant pages."""
    index = read_file_safe(INDEX_FILE)
    if not index:
        print("No index found. Run compile_meeting.py on some notes first.")
        sys.exit(1)

    # First pass: ask model which pages to read
    find_response = timed_generate(
        "query/navigate",
        model=API_MODEL,
        contents=f"Index:\n{index}\n\nQuestion: {question}\n\nWhich paths should I read?",
        config=types.GenerateContentConfig(
            system_instruction="You are a wiki navigator. Given an index and a question, return a JSON list of file paths to read.",
            response_mime_type="application/json",
            response_schema=PathList,
        ),
    )
    path_list = PathList.model_validate_json(find_response.text)
    paths = path_list.paths if path_list.paths else [
        str(p.relative_to(WIKI_DIR)) for p in PROJECTS_DIR.glob("*/summary.md")
    ]

    # Load pages
    pages = {}
    for p in paths:
        content = read_file_safe(WIKI_DIR / p)
        if content:
            pages[p] = content

    if not pages:
        print("No relevant pages found.")
        return

    pages_block = "\n\n".join(f"### {k}\n{v}" for k, v in pages.items())

    # Second pass: answer the question
    answer_response = timed_generate(
        "query/answer",
        model=API_MODEL,
        contents=f"{pages_block}\n\nQuestion: {question}",
        config=types.GenerateContentConfig(
            system_instruction="You are a knowledgeable assistant with access to an organizational wiki. Answer questions directly and honestly based on the wiki content provided.",
        ),
    )
    print(answer_response.text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="BenchSci wiki compiler")
    parser.add_argument("note", nargs="?", help="Path to Granola meeting note (.md)")
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
        print(f"ERROR: File not found: {note_path}")
        sys.exit(1)

    ensure_dirs()

    meeting_note = note_path.read_text()
    meeting_title = note_path.stem

    print(f"Processing: {meeting_title}")
    print(f"Wiki dir:   {WIKI_DIR}")
    if args.dry_run:
        print("DRY RUN — no files will be written\n")

    print("Loading existing wiki context...")
    context = gather_context({})

    print("Calling API...")
    output = call_api(meeting_note, context)

    print("Writing wiki updates...")
    apply_output(output, meeting_title, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
