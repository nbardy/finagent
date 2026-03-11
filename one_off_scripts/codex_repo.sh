#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CODEX_HOME="$ROOT/.codex"

uv run python "$ROOT/one_off_scripts/setup_repo_codex_home.py" --dest "$CODEX_HOME" >/dev/null

exec codex -C "$ROOT" "$@"
