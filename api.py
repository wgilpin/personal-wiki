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


def call_api(meeting_note: str, existing_context: dict) -> WikiOutput:
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
            max_output_tokens=65536,
        ),
    )

    return WikiOutput.model_validate_json(response.text)
