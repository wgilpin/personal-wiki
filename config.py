"""Shared configuration and LLM client (Gemini or Ollama)."""

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

WIKI_DIR = Path(os.environ.get("WIKI_DIR", Path.home() / "wiki" / "benchsci"))
PROJECTS_DIR = WIKI_DIR / "projects"
THEMES_DIR = WIKI_DIR / "themes"
PEOPLE_DIR = WIKI_DIR / "people"
PENDING_FILE = WIKI_DIR / "pending-bill.md"
CLOSED_FILE = WIKI_DIR / "closed.md"
INDEX_FILE = WIKI_DIR / "index.md"
PROCESSED_FILE = WIKI_DIR / ".processed.json"
SCHEMA_FILE = Path(__file__).parent / "schema.md"
CORRECTIONS_FILE = Path(__file__).parent / "corrections.json"


# ---------------------------------------------------------------------------
# LLM response wrapper
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    text: str
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


# ---------------------------------------------------------------------------
# Provider setup
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")

if LLM_PROVIDER == "gemini":
    from google import genai
    from google.genai import types as _gemini_types

    _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    _model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

elif LLM_PROVIDER == "ollama":
    from openai import OpenAI

    _client = OpenAI(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        api_key="ollama",
    )
    _model = os.environ.get("OLLAMA_MODEL", "gemma4:26b")

else:
    raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")

API_MODEL = _model

if LLM_PROVIDER != "gemini":
    print(f"[LLM] Using {LLM_PROVIDER} ({_model})")



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_corrections() -> dict[str, str]:
    """Load corrections map. Returns empty dict if file missing."""
    if CORRECTIONS_FILE.exists():
        return json.loads(CORRECTIONS_FILE.read_text())
    return {}


def _schema_prompt(schema_cls: type[BaseModel]) -> str:
    """Build a system-prompt fragment that describes the expected JSON schema."""
    schema = json.dumps(schema_cls.model_json_schema(), indent=2)
    return (
        "You MUST respond with a JSON object that strictly conforms to this JSON Schema.\n"
        "Do not include any text outside the JSON object. No markdown fences, no preamble.\n\n"
        f"JSON Schema:\n```json\n{schema}\n```\n\n"
    )


# ---------------------------------------------------------------------------
# Provider-specific generation
# ---------------------------------------------------------------------------

def _generate_gemini(
    contents: str,
    system_instruction: str,
    response_schema: type[BaseModel] | None,
    max_output_tokens: int | None,
) -> LLMResponse:
    config_kwargs: dict = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if response_schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema
    if max_output_tokens:
        config_kwargs["max_output_tokens"] = max_output_tokens

    response = _client.models.generate_content(
        model=_model,
        contents=contents,
        config=_gemini_types.GenerateContentConfig(**config_kwargs),
    )

    finish = response.candidates[0].finish_reason if response.candidates else None
    usage = response.usage_metadata
    return LLMResponse(
        text=response.text,
        finish_reason=str(finish) if finish else None,
        prompt_tokens=usage.prompt_token_count,
        completion_tokens=usage.candidates_token_count,
        total_tokens=usage.total_token_count,
    )


def _generate_ollama(
    contents: str,
    system_instruction: str,
    response_schema: type[BaseModel] | None,
    max_output_tokens: int | None,
) -> LLMResponse:
    effective_system = ""
    if response_schema:
        effective_system += _schema_prompt(response_schema)
    if system_instruction:
        effective_system += system_instruction

    messages = []
    if effective_system:
        messages.append({"role": "system", "content": effective_system})
    messages.append({"role": "user", "content": contents})

    kwargs: dict = {}
    if response_schema:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_schema.__name__,
                "strict": True,
                "schema": response_schema.model_json_schema(),
            },
        }
    if max_output_tokens:
        kwargs["max_tokens"] = max_output_tokens

    response = _client.chat.completions.create(
        model=_model,
        messages=messages,
        **kwargs,
    )

    choice = response.choices[0]
    usage = response.usage

    # Strip illegal JSON control characters that local models sometimes emit
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", choice.message.content)

    # Normalise finish_reason to match Gemini conventions
    _FINISH_MAP = {"stop": "STOP", "length": "MAX_TOKENS"}
    finish_reason = _FINISH_MAP.get(choice.finish_reason, choice.finish_reason)

    return LLMResponse(
        text=text,
        finish_reason=finish_reason,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_DISPATCH = {"gemini": _generate_gemini, "ollama": _generate_ollama}


def timed_generate(
    label: str,
    *,
    contents: str,
    system_instruction: str = "",
    response_schema: type[BaseModel] | None = None,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    t0 = time.perf_counter()
    result = _DISPATCH[LLM_PROVIDER](contents, system_instruction, response_schema, max_output_tokens)
    elapsed = time.perf_counter() - t0
    print(
        f"  [{label}] {elapsed:.1f}s"
        f"  tokens: {result.prompt_tokens} in → {result.completion_tokens} out"
        f" ({result.total_tokens} total)"
    )
    return result
