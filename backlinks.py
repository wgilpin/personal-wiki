"""Backlink generation for the wiki.

Scans wiki pages for mentions of known entities (people, projects, themes)
and injects Obsidian wiki-links into the Related / Connected sections.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from config import PEOPLE_DIR, PROJECTS_DIR, THEMES_DIR, WIKI_DIR


@dataclass
class Entity:
    name: str   # display name from # Heading
    path: str   # relative to WIKI_DIR, without .md (for Obsidian links)
    kind: str   # "person", "project", "theme"


def _extract_heading(file_path: Path) -> str | None:
    """Extract the display name from the first # Heading line."""
    try:
        for line in file_path.read_text().splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return None


# The wiki owner appears on every page — linking to their own page is noise
WIKI_OWNER = "Bill"


def build_registry() -> list[Entity]:
    """Scan wiki dirs and build entity registry, sorted longest-name-first."""
    entities: list[Entity] = []

    for p in PEOPLE_DIR.glob("*.md"):
        name = _extract_heading(p)
        if not name or name == WIKI_OWNER:
            continue
        rel = str(p.relative_to(WIKI_DIR))
        entities.append(Entity(name=name, path=rel.removesuffix(".md"), kind="person"))

    registered_projects: set[str] = set()
    for p in PROJECTS_DIR.glob("*/summary.md"):
        name = _extract_heading(p)
        if name:
            rel = str(p.relative_to(WIKI_DIR))
            entities.append(Entity(name=name, path=rel.removesuffix(".md"), kind="project"))
            registered_projects.add(p.parent.name)

    # Projects without summaries: use latest snapshot heading for display name
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir() or project_dir.name in registered_projects:
            continue
        snapshots = sorted(project_dir.glob("*.md"), reverse=True)
        if not snapshots:
            continue
        heading = _extract_heading(snapshots[0])
        if heading:
            # Snapshot headings are "Project Name — YYYY-MM-DD", strip the date
            name = heading.split(" — ")[0].strip()
            # Link to the latest snapshot since there's no summary
            rel = str(snapshots[0].relative_to(WIKI_DIR))
            entities.append(Entity(name=name, path=rel.removesuffix(".md"), kind="project"))

    for p in THEMES_DIR.glob("*.md"):
        name = _extract_heading(p)
        if name:
            rel = str(p.relative_to(WIKI_DIR))
            entities.append(Entity(name=name, path=rel.removesuffix(".md"), kind="theme"))

    # Longest names first so "CAI 2" matches before "CAI"
    entities.sort(key=lambda e: len(e.name), reverse=True)
    return entities


def _strip_sections(content: str) -> str:
    """Return body text with headings, metadata lines, and link sections removed.

    This prevents matching entity names in headings or in the sections we'll overwrite.
    """
    skip_sections = {"## Related", "## Connected Projects", "## Connected People"}
    lines = []
    skipping = False
    for line in content.splitlines():
        # Skip metadata lines like **Role:** etc.
        if line.startswith("**") and ":" in line:
            continue
        # Track when we enter/leave skip sections
        if line.startswith("## "):
            skipping = line.strip() in skip_sections
            continue
        if line.startswith("# "):
            skipping = False
            continue
        if not skipping:
            lines.append(line)
    return "\n".join(lines)


def find_mentions(content: str, registry: list[Entity], self_path: str) -> dict[str, list[Entity]]:
    """Find entity mentions in page body, grouped by kind."""
    body = _strip_sections(content)
    found: dict[str, list[Entity]] = {"person": [], "project": [], "theme": []}

    for entity in registry:
        if entity.path == self_path:
            continue
        # Word-boundary match, case-sensitive.
        # Negative lookahead skips date contexts like "Jan 22", "Jan 2026".
        pattern = r"\b" + re.escape(entity.name) + r"\b(?!\s+\d)"
        if re.search(pattern, body):
            found[entity.kind].append(entity)

    return found


def _format_links(entities: list[Entity]) -> str:
    """Format a list of entities as Obsidian wiki-links, one per line."""
    if not entities:
        return ""
    # Sort alphabetically for stable output
    sorted_entities = sorted(entities, key=lambda e: e.name)
    return "\n".join(f"- [[{e.path}|{e.name}]]" for e in sorted_entities)


def _replace_section(content: str, heading: str, new_body: str) -> str:
    """Replace content under a ## heading up to the next ## or end of file."""
    lines = content.splitlines()
    result = []
    i = 0
    replaced = False

    while i < len(lines):
        if lines[i].strip() == heading:
            result.append(lines[i])
            result.append("")
            if new_body:
                result.append(new_body)
            replaced = True
            # Skip old content until next heading or end
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            # Add blank line before next section
            if i < len(lines):
                result.append("")
        else:
            result.append(lines[i])
            i += 1

    # If heading wasn't found, append it
    if not replaced:
        result.append("")
        result.append(heading)
        result.append("")
        if new_body:
            result.append(new_body)

    return "\n".join(result)


def inject_backlinks(content: str, mentions: dict[str, list[Entity]], page_kind: str) -> str:
    """Rewrite link sections in content based on page kind."""
    if page_kind == "theme":
        project_links = _format_links(mentions.get("project", []))
        people_links = _format_links(mentions.get("person", []))
        content = _replace_section(content, "## Connected Projects", project_links)
        content = _replace_section(content, "## Connected People", people_links)
    else:
        # People and project pages use ## Related
        all_mentions = []
        for kind in ("project", "theme", "person"):
            all_mentions.extend(mentions.get(kind, []))
        links = _format_links(all_mentions)
        content = _replace_section(content, "## Related", links)

    return content


def _is_snapshot(path: Path) -> bool:
    """True for dated snapshot files like 2026-04-07.md."""
    return bool(re.match(r"\d{4}-\d{2}-\d{2}\.md$", path.name))


def _skip_file(path: Path) -> bool:
    """True for files that should not receive backlinks."""
    return (
        _is_snapshot(path)
        or path.name in ("index.md", "pending-bill.md")
        or path.name.startswith(".")
    )


def _page_kind(path: Path) -> str:
    """Determine the page kind from its path."""
    rel = str(path.relative_to(WIKI_DIR))
    if rel.startswith("people/"):
        return "person"
    if rel.startswith("projects/"):
        return "project"
    if rel.startswith("themes/"):
        return "theme"
    return "unknown"


def process_content(content: str, rel_path: str, registry: list[Entity]) -> str:
    """Process a single page's content and return updated content with backlinks."""
    self_path = rel_path.removesuffix(".md")

    # Determine page kind from path
    if rel_path.startswith("people/"):
        kind = "person"
    elif rel_path.startswith("projects/"):
        kind = "project"
    elif rel_path.startswith("themes/"):
        kind = "theme"
    else:
        return content

    mentions = find_mentions(content, registry, self_path)
    return inject_backlinks(content, mentions, kind)


def _build_project_slug_map(registry: list[Entity]) -> dict[str, Entity]:
    """Build a slug -> Entity lookup for projects.

    Path is like "projects/cai-2/summary" or "projects/thermo-fisher/2026-04-08".
    The slug is always the second segment.
    """
    slug_map: dict[str, Entity] = {}
    for e in registry:
        if e.kind == "project":
            parts = e.path.split("/")
            if len(parts) >= 2:
                # Prefer summary paths over snapshot paths
                if parts[1] not in slug_map or parts[-1] == "summary":
                    slug_map[parts[1]] = e
    return slug_map


def link_pending_line(line: str, registry: list[Entity], _slug_map: dict[str, Entity] | None = None) -> str:
    """Add wiki-links to a single pending-bill line."""
    if not line.startswith("- ["):
        return line

    if _slug_map is None:
        _slug_map = _build_project_slug_map(registry)

    # Replace project slug after " — " (em dash)
    match = re.search(r" — (\S+)( \(captured)", line)
    if match:
        slug = match.group(1)
        if slug in _slug_map and slug not in ("unknown", "none"):
            e = _slug_map[slug]
            line = line.replace(f" — {slug}", f" — [[{e.path}|{e.name}]]")

    # Replace people names in the line text
    for entity in registry:
        if entity.kind != "person":
            continue
        # Only match if not already inside a [[ ]] link, skip date contexts
        pattern = r"(?<!\[\[)(?<!\|)\b" + re.escape(entity.name) + r"\b(?!\]\])(?!\s+\d)"
        if re.search(pattern, line):
            line = re.sub(pattern, f"[[{entity.path}|{entity.name}]]", line)

    return line


def add_backlinks_to_pending(content: str, registry: list[Entity]) -> str:
    """Add inline wiki-links to all lines in pending-bill.md."""
    slug_map = _build_project_slug_map(registry)
    lines = content.splitlines()
    result = [link_pending_line(line, registry, slug_map) for line in lines]
    return "\n".join(result)


def process_file(file_path: Path, registry: list[Entity]) -> str | None:
    """Process a single wiki file. Returns updated content or None if unchanged."""
    if _skip_file(file_path):
        return None

    content = file_path.read_text()
    kind = _page_kind(file_path)
    if kind == "unknown":
        return None

    rel = str(file_path.relative_to(WIKI_DIR))
    updated = process_content(content, rel, registry)
    if updated != content:
        return updated
    return None


def rebuild_all_backlinks(dry_run: bool = False):
    """Rebuild backlinks across the entire wiki."""
    from wiki import write_file

    registry = build_registry()
    print(f"  Built registry: {len(registry)} entities")

    updated_count = 0

    # Process all entity pages
    for md_file in sorted(WIKI_DIR.rglob("*.md")):
        if _skip_file(md_file):
            continue
        kind = _page_kind(md_file)
        if kind == "unknown":
            continue

        content = md_file.read_text()
        rel = str(md_file.relative_to(WIKI_DIR))
        updated = process_content(content, rel, registry)
        if updated != content:
            updated_count += 1
            write_file(md_file, updated, dry_run)

    # Process pending-bill.md
    pending = WIKI_DIR / "pending-bill.md"
    if pending.exists():
        content = pending.read_text()
        updated = add_backlinks_to_pending(content, registry)
        if updated != content:
            updated_count += 1
            write_file(pending, updated, dry_run)

    print(f"\n  Backlinks: updated {updated_count} file(s)")
