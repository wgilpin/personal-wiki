"""File helpers, index maintenance, pending items, and people updates."""

from datetime import date
from pathlib import Path

from config import (
    CLOSED_FILE,
    INDEX_FILE,
    PENDING_FILE,
    PEOPLE_DIR,
    PROJECTS_DIR,
    THEMES_DIR,
    WIKI_DIR,
)
from models import IndexUpdate, PendingItem, PeopleUpdate, WikiOutput


def ensure_dirs():
    for d in [PROJECTS_DIR, THEMES_DIR, PEOPLE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    WIKI_DIR.mkdir(parents=True, exist_ok=True)


def read_file_safe(path: Path) -> str:
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


def update_index(updates: list[IndexUpdate], dry_run: bool = False):
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


def sweep_closed(dry_run: bool = False):
    """Move checked-off items from pending-bill.md to closed.md."""
    pending = read_file_safe(PENDING_FILE)
    if not pending:
        return

    keep_lines: list[str] = []
    closed_lines: list[str] = []
    current_heading: str | None = None

    for line in pending.splitlines():
        if line.startswith("### "):
            current_heading = line
            keep_lines.append(line)
        elif line.startswith("- [x]") or line.startswith("- [X]"):
            closed_lines.append((current_heading, line))
        else:
            keep_lines.append(line)

    if not closed_lines:
        return

    # Remove empty date headings (heading followed by another heading or EOF)
    cleaned: list[str] = []
    for i, line in enumerate(keep_lines):
        if line.startswith("### "):
            # Look ahead: is the next non-blank line another heading or EOF?
            rest = [l for l in keep_lines[i + 1:] if l.strip()]
            if not rest or rest[0].startswith("### "):
                continue  # drop empty heading
        cleaned.append(line)

    # Write updated pending file
    new_pending = "\n".join(cleaned).rstrip() + "\n"
    write_file(PENDING_FILE, new_pending, dry_run)

    # Build closed.md content
    existing_closed = read_file_safe(CLOSED_FILE)
    if not existing_closed:
        existing_closed = "# Closed\n\nCompleted action items.\n"

    # Group closed items by date heading
    by_date: dict[str, list[str]] = {}
    for heading, item in closed_lines:
        by_date.setdefault(heading, []).append(item)

    for heading, items in by_date.items():
        if heading and heading in existing_closed:
            # Append under existing date section
            idx = existing_closed.index(heading) + len(heading)
            next_nl = existing_closed.index("\n", idx)
            next_heading = existing_closed.find("\n### ", next_nl)
            if next_heading == -1:
                insert_at = len(existing_closed.rstrip())
            else:
                insert_at = next_heading
            existing_closed = (
                existing_closed[:insert_at].rstrip()
                + "\n"
                + "\n".join(items)
                + "\n"
                + existing_closed[insert_at:]
            )
        else:
            existing_closed = (
                existing_closed.rstrip()
                + f"\n\n{heading}\n"
                + "\n".join(items)
                + "\n"
            )

    write_file(CLOSED_FILE, existing_closed, dry_run)

    count = len(closed_lines)
    print(f"  Swept {count} closed item(s) to closed.md")


def append_pending(items: list[PendingItem], registry=None, dry_run: bool = False):
    if not items:
        return

    from backlinks import link_pending_line

    existing = read_file_safe(PENDING_FILE)
    if not existing:
        existing = "# Pending — Bill\n\nActions only Bill owns. Review weekly.\n"

    # Group new items by date, inserting under existing or new h3 headings
    for item in items:
        project_part = f" — {item.project}" if item.project and item.project not in ("unknown", "none", "") else ""
        source_link = f"[{item.source_meeting}]({item.source_doc})" if item.source_doc else item.source_meeting
        line = f"- [ ] {item.action}{project_part} (from: {source_link})"
        if registry:
            line = link_pending_line(line, registry)

        heading = f"### {item.date_captured}"
        if heading in existing:
            # Find the end of this date section (next heading or EOF) and append
            idx = existing.index(heading) + len(heading)
            # Find the next line after the heading
            next_nl = existing.index("\n", idx)
            # Find the next heading or end of file
            next_heading = existing.find("\n### ", next_nl)
            if next_heading == -1:
                insert_at = len(existing.rstrip())
            else:
                insert_at = next_heading
            existing = existing[:insert_at].rstrip() + "\n" + line + "\n" + existing[insert_at:]
        else:
            # Append new date section at end
            existing = existing.rstrip() + f"\n\n{heading}\n{line}\n"

    write_file(PENDING_FILE, existing, dry_run)


def apply_people_updates(updates: list[PeopleUpdate], dry_run: bool = False):
    for update in updates:
        write_file(WIKI_DIR / update.path, update.updated_content, dry_run)


def apply_output(output: WikiOutput, meeting_title: str, dry_run: bool = False):
    snapshot_index_updates = []

    for snap in output.snapshots:
        path = WIKI_DIR / snap.path
        write_file(path, snap.content, dry_run)
        snapshot_index_updates.append(IndexUpdate(
            path=snap.path,
            one_line_summary=f"Snapshot from {meeting_title}",
        ))

    for proj in output.project_summaries:
        write_file(WIKI_DIR / proj.path, proj.updated_content, dry_run)

    for theme in output.theme_updates:
        write_file(WIKI_DIR / theme.path, theme.updated_content, dry_run)

    apply_people_updates(output.people_updates, dry_run)

    all_index_updates = snapshot_index_updates + output.index_updates
    if all_index_updates:
        update_index(all_index_updates, dry_run)

    # Build registry after all files are written so new entities are included
    from backlinks import build_registry, process_content

    registry = build_registry()

    # Append pending items with backlinks baked into each line
    append_pending(output.pending_bill, registry, dry_run)

    # Post-process: inject backlinks into all entity pages that were just written
    for entity_list in (output.project_summaries, output.theme_updates, output.people_updates):
        for item in entity_list:
            path = WIKI_DIR / item.path
            if path.exists():
                content = path.read_text()
                updated = process_content(content, item.path, registry)
                if updated != content:
                    write_file(path, updated, dry_run)
