#!/bin/sh
set -eu
cd "$(dirname "$0")"
export CODEATLAS_HOME="$PWD/.codeatlas"
if [ ! -x .venv/bin/python ]; then
  echo 'First-time setup: run ./setup.sh from this folder.'
  read -r task_reply
  exit 1
fi
exec .venv/bin/python -m codeatlas.cli app "$@"
