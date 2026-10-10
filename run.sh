#!/usr/bin/env bash
# macOS / Linux: first run creates .venv and installs packages, then starts the app.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements-dev.txt
fi
exec .venv/bin/python run.py "$@"
