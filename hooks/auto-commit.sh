#!/bin/bash
# Auto-commit WIP changes when Claude Code session ends
# Used by: Claude Code Stop hook
#
# Configure PROJECTS with your project paths.

PROJECTS=(
  # "/your/project/path"
  # "/another/project"
)

for PROJECT in "${PROJECTS[@]}"; do
  [ -d "$PROJECT/.git" ] || continue

  cd "$PROJECT" || continue

  # Check if there are any changes (modified, untracked, staged)
  if git diff --quiet HEAD 2>/dev/null && \
     git diff --staged --quiet 2>/dev/null && \
     [ -z "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
    continue  # Nothing to commit in this project
  fi

  # Stage everything except secrets and build artifacts
  git add -A \
    -- ':!**/.env*' \
    -- ':!**/node_modules/**' \
    -- ':!**/.next/**' \
    -- ':!**/*.log' \
    2>/dev/null

  # Only commit if something was staged
  if git diff --staged --quiet 2>/dev/null; then
    continue
  fi

  git commit -m "wip: auto-checkpoint $(date '+%Y-%m-%d %H:%M')" \
    --no-gpg-sign \
    -q \
    2>/dev/null

  git push -q 2>/dev/null || true

done
