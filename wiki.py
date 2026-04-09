"""File helpers, index maintenance, pending items, and people updates."""

from datetime import date
from pathlib import Path

from config import (
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


def append_pending(items: list[PendingItem], registry=None, dry_run: bool = False):
    if not items:
        return

    from backlinks import link_pending_line

    existing = read_file_safe(PENDING_FILE)
    if not existing:
        existing = "# Pending — Bill\n\nActions only Bill owns. Review weekly.\n\n"

    new_lines = []
    for item in items:
        line = f"- [ ] {item.action} — {item.project} (captured {item.date_captured}, from: {item.source_meeting})"
        if registry:
            line = link_pending_line(line, registry)
        new_lines.append(line)

    updated = existing.rstrip() + "\n" + "\n".join(new_lines) + "\n"
    write_file(PENDING_FILE, updated, dry_run)


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
