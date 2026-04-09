"""Shared configuration and Gemini client."""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv()

WIKI_DIR = Path(os.environ.get("WIKI_DIR", Path.home() / "wiki" / "benchsci"))
PROJECTS_DIR = WIKI_DIR / "projects"
THEMES_DIR = WIKI_DIR / "themes"
PEOPLE_DIR = WIKI_DIR / "people"
PENDING_FILE = WIKI_DIR / "pending-bill.md"
INDEX_FILE = WIKI_DIR / "index.md"
SCHEMA_FILE = Path(__file__).parent / "schema.md"
CORRECTIONS_FILE = Path(__file__).parent / "corrections.json"

API_MODEL = "gemini-2.0-flash"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def load_corrections() -> dict[str, str]:
    """Load corrections map. Returns empty dict if file missing."""
    if CORRECTIONS_FILE.exists():
        return json.loads(CORRECTIONS_FILE.read_text())
    return {}


def timed_generate(label: str, **kwargs):
    t0 = time.perf_counter()
    response = client.models.generate_content(**kwargs)
    elapsed = time.perf_counter() - t0
    print(f"  [{label}] {elapsed:.1f}s")
    return response
