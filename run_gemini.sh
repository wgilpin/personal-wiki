#!/bin/bash
LLM_PROVIDER=gemini WIKI_DIR=/Users/bgilpin/wiki/benchsci exec uv run python compile_meeting.py "/Users/bgilpin/Documents/Personal/Granola BenchSci" "$@"
