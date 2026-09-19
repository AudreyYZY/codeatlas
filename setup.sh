#!/bin/sh
set -eu
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then
  uv venv .venv --python 3.11
  uv pip install --python .venv/bin/python '.[web]'
else
  python3 -m venv .venv
  .venv/bin/python -m pip install '.[web]'
fi
echo 'Ready. Double-click Open CodeAtlas.command, or run .venv/bin/codeatlas app.'
