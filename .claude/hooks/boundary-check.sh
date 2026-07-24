#!/bin/bash
# PreToolUse hook for Edit/Write: enforces filesystem boundaries (agnostic).
#
# Boundaries enforced:
#   1. knowledge-base/references/ (similar projects — inspiration) AND
#      knowledge-base/tools/ (tools we depend on) are both read-only study
#      material — never edit either. Capture findings in
#      knowledge-base/discoveries/blueprints/.
#
# Additional architectural boundaries (e.g., DIP between domain and adapter
# layers) are project-specific and belong in rules/architecture.md as
# conventions enforced by code review, not by this hook.
#
# Exit 0 = allow, Exit 2 = block.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.filePath // empty')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# --- Exception: project-owned metadata at the ROOT of references/ or tools/ ---
# Files prefixed with "_" directly under those dirs (e.g. _catalog.md, written by
# /roadmap-init) are OUR bookkeeping ABOUT the study material — not edits TO the
# cloned third-party code. Anything inside a peer folder stays blocked, because the
# pattern requires the "_" name to be the last path segment.
if echo "$FILE_PATH" | grep -qE '(^|/)(\.claude/)?knowledge-base/(references|tools)/_[^/]+$'; then
  exit 0
fi

# --- knowledge-base/{references,tools}/ are read-only ---
# Matches both standalone (knowledge-base/) and plugin install (.claude/knowledge-base/) layouts.
if echo "$FILE_PATH" | grep -qE '(^|/)(\.claude/)?knowledge-base/(references|tools)/'; then
  echo '{"decision":"block","reason":"BOUNDARY VIOLATION: knowledge-base/references/ (similar projects — inspiration) and knowledge-base/tools/ (tools we depend on) are read-only. Never edit/create files there. Capture findings in knowledge-base/discoveries/blueprints/."}' >&2
  exit 2
fi

exit 0
