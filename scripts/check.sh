#!/usr/bin/env bash
set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  uv sync --extra dev
  uv run ruff check .
  uv run mypy src
  uv run pytest
else
  PYTHONPATH=src python3 -m compileall -q src tests scripts
  PYTHONPATH=src python3 -m unittest discover -s tests/unit
fi
