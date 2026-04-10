#!/bin/bash
LLM_PROVIDER=ollama OLLAMA_MODEL=gemma4:26b WIKI_DIR=/Users/bgilpin/Projects/temp exec uv run python compile_meeting.py "/Users/bgilpin/Documents/Personal/Granola BenchSci" "$@"
