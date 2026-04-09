# Personal Wiki

Process Granola meeting notes into the BenchSci org wiki (Obsidian vault).

## Usage

```bash
uv run python compile_meeting.py <note.md or folder>
```

### Arguments

| Argument | Description |
|----------|-------------|
| `note` | Path to a meeting note `.md` file, or a folder of notes (recurses for all `.md` files). |

### Flags

| Flag | Description |
|------|-------------|
| `--dry-run` | Print what would happen without writing any files. |
| `--pending` | Print the contents of `pending-bill.md`. |
| `--query "..."` | Query the wiki with a natural-language question. |
| `--apply-corrections` | Apply `corrections.json` to all existing wiki files and folder names. |
| `--reprocess-all` | Reprocess all files, ignoring the processed-files manifest (skips already-processed notes by default). |
| `--backlinks` | Rebuild backlinks across all wiki pages. |

### Examples

```bash
# Process a single note
uv run python compile_meeting.py ~/Documents/Personal/Granola\ BenchSci/standup.md

# Process all notes in a folder
uv run python compile_meeting.py ~/Documents/Personal/Granola\ BenchSci

# Dry run to see what would change
uv run python compile_meeting.py ~/Documents/Personal/Granola\ BenchSci --dry-run

# Query the wiki
uv run python compile_meeting.py --query "what's going on with LENS?"

# Show pending items
uv run python compile_meeting.py --pending
```

### Environment

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Required. API key for Gemini (used for project/theme compilation). |
| `WIKI_DIR` | Path to wiki root. Defaults to `~/wiki/benchsci`. |

## Creating a macOS Dock shortcut

To create a Dock icon that runs a command (e.g. `compile_meeting.py`):

1. Write an AppleScript file:

```applescript
-- /tmp/compile_meeting.applescript
do shell script "cd /Users/bgilpin/Projects/personal-wiki && /opt/homebrew/bin/uv run python compile_meeting.py '/Users/bgilpin/Documents/Personal/Granola BenchSci'"
```

2. Compile it into a `.app` bundle:

```bash
osacompile -o ~/Applications/Compile\ Meeting.app /tmp/compile_meeting.applescript
```

3. Open Finder, Cmd+Shift+G to `~/Applications`, and drag the app to the Dock.

Notes:
- Use full paths for everything (`uv`, python scripts, arguments) since the app has no shell environment.
- The app runs silently — a white dot appears in the Dock while it's running, disappears when done.
- To rebuild after changing the script, just re-run the `osacompile` command.
