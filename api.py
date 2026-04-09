"""Gemini API calls and wiki context gathering."""

from google.genai import types

from config import (
    API_MODEL,
    PEOPLE_DIR,
    PROJECTS_DIR,
    SCHEMA_FILE,
    THEMES_DIR,
    WIKI_DIR,
    timed_generate,
)
from models import WikiOutput


def load_schema() -> str:
    if SCHEMA_FILE.exists():
        return SCHEMA_FILE.read_text()
    return "(schema.md not found — place schema.md alongside this script)"


def gather_context() -> dict:
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


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    """Apply known transcription corrections to text. Longest matches first."""
    for wrong, right in sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True):
        text = text.replace(wrong, right)
    return text


def build_corrections_prompt(corrections: dict[str, str]) -> str:
    """Build a system prompt section from corrections and wiki entity names."""
    lines = ["\n## Transcription Corrections\n"]
    lines.append("Granola transcripts frequently mishear product and project names.")
    lines.append("The following corrections have already been applied to the input text,")
    lines.append("but watch for variants the automatic replacement may have missed:\n")

    for wrong, right in corrections.items():
        lines.append(f'- "{wrong}" → {right}')

    # Derive canonical entity names from the wiki directory structure
    project_names = sorted(d.name for d in PROJECTS_DIR.iterdir() if d.is_dir())
    people_names = sorted(p.stem for p in PEOPLE_DIR.glob("*.md"))

    if project_names:
        lines.append("\n### Known Project Names (from wiki)")
        lines.append("Always use these exact names (not phonetic variants):\n")
        for p in project_names:
            lines.append(f"- {p}")

    if people_names:
        lines.append("\n### Known People Names (from wiki)")
        lines.append("Prefer these canonical forms:\n")
        for p in people_names:
            lines.append(f"- {p}")

    return "\n".join(lines)


def call_api(meeting_note: str, existing_context: dict, corrections: dict[str, str] | None = None) -> WikiOutput:
    schema = load_schema()

    if corrections:
        meeting_note = apply_corrections(meeting_note, corrections)
        corrections_block = build_corrections_prompt(corrections)
    else:
        corrections_block = ""

    context_lines = ["## Existing Wiki Content\n"]
    for path, content in existing_context.items():
        if content:
            context_lines.append(f"### {path}\n```\n{content}\n```\n")

    context_block = "\n".join(context_lines) if existing_context else "No existing wiki content yet."

    system_prompt = f"{schema}\n\n{context_block}\n{corrections_block}"
    user_message = f"Process this meeting note and return the JSON output as specified in the schema.\n\n{meeting_note}"

    response = timed_generate(
        "compile",
        model=API_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=WikiOutput,
            max_output_tokens=65536,
        ),
    )

    return WikiOutput.model_validate_json(response.text)
