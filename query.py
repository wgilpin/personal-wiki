"""Wiki query mode — answer questions using wiki content."""

import sys

from config import (
    INDEX_FILE,
    PROJECTS_DIR,
    WIKI_DIR,
    timed_generate,
)
from models import PathList
from wiki import read_file_safe


def run_query(question: str):
    index = read_file_safe(INDEX_FILE)
    if not index:
        print("No index found. Run compile_meeting.py on some notes first.")
        sys.exit(1)

    find_response = timed_generate(
        "query/navigate",
        contents=f"Index:\n{index}\n\nQuestion: {question}\n\nWhich paths should I read?",
        system_instruction="You are a wiki navigator. Given an index and a question, return a JSON list of file paths to read.",
        response_schema=PathList,
    )
    path_list = PathList.model_validate_json(find_response.text)
    paths = path_list.paths if path_list.paths else [
        str(p.relative_to(WIKI_DIR)) for p in PROJECTS_DIR.glob("*/summary.md")
    ]

    pages = {}
    for p in paths:
        content = read_file_safe(WIKI_DIR / p)
        if content:
            pages[p] = content

    if not pages:
        print("No relevant pages found.")
        return

    pages_block = "\n\n".join(f"### {k}\n{v}" for k, v in pages.items())

    answer_response = timed_generate(
        "query/answer",
        contents=f"{pages_block}\n\nQuestion: {question}",
        system_instruction="You are a knowledgeable assistant with access to an organizational wiki. Answer questions directly and honestly based on the wiki content provided.",
    )
    print(answer_response.text)
