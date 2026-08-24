#!/usr/bin/env bash
set -euo pipefail

SERVER_NAME="${SERVER_NAME:-piazza-mcp}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex CLI is not installed or is not on PATH" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed or is not on PATH" >&2
  exit 1
fi

if codex mcp get "$SERVER_NAME" >/dev/null 2>&1; then
  codex mcp remove "$SERVER_NAME"
fi

codex mcp add "$SERVER_NAME" \
  -- uv --directory "$PROJECT_DIR" run --frozen piazza-mcp

codex mcp get "$SERVER_NAME"
