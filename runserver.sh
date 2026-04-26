#!/usr/bin/env bash
# Always use the project venv’s Python (system `python3` has no Django).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python3" ]; then
  exec "$ROOT/.venv/bin/python3" manage.py runserver "$@"
fi
if [ -x "$ROOT/venv/bin/python3" ]; then
  exec "$ROOT/venv/bin/python3" manage.py runserver "$@"
fi

echo "No virtualenv found at .venv/ or venv/. Create and install deps:" >&2
echo "  python3 -m venv .venv" >&2
echo "  source .venv/bin/activate" >&2
echo "  pip install -r requirements.txt" >&2
exit 1
