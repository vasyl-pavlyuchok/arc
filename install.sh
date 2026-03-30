#!/bin/bash
# ARC — Adaptive Rule Context
# Installation script
# Usage: ./install.sh

set -e

ARC_DIR="$HOME/.arc"
HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo "Installing ARC — Adaptive Rule Context"
echo "======================================="

# 1. Create .arc domain directory
echo ""
echo "1. Setting up domains directory at $ARC_DIR..."
mkdir -p "$ARC_DIR/sessions"

# Copy example domains
for domain in domains/*; do
  name=$(basename "$domain")
  dest="$ARC_DIR/$name"
  if [ -f "$dest" ]; then
    echo "   ⚠  $name already exists — skipping (keeping yours)"
  else
    cp "$domain" "$dest"
    echo "   ✓  $name"
  fi
done

# 2. Install hooks
echo ""
echo "2. Installing hooks to $HOOKS_DIR..."
mkdir -p "$HOOKS_DIR"

for hook in hooks/*; do
  name=$(basename "$hook")
  dest="$HOOKS_DIR/$name"
  if [ -f "$dest" ]; then
    echo "   ⚠  $name already exists — skipping (keeping yours)"
  else
    cp "$hook" "$dest"
    chmod +x "$dest"
    echo "   ✓  $name"
  fi
done

# 3. Configure Claude Code settings
echo ""
echo "3. Configuring Claude Code settings..."

if [ ! -f "$SETTINGS_FILE" ]; then
  echo '{}' > "$SETTINGS_FILE"
fi

# Auto-merge ARC hooks into settings.json without overwriting existing hooks
if grep -q "arc-hook.py" "$SETTINGS_FILE" 2>/dev/null; then
  echo "   ⚠  arc-hook.py already registered in settings.json — skipping"
else
  python3 - "$SETTINGS_FILE" << 'PYEOF'
import json, sys

settings_file = sys.argv[1]
try:
    with open(settings_file, 'r') as f:
        settings = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    settings = {}

hooks = settings.setdefault('hooks', {})

arc_hooks = {
    'UserPromptSubmit': {
        'matcher': '',
        'hook': {'type': 'command', 'command': 'python3 ~/.claude/hooks/arc-hook.py'}
    },
    'PostToolUse': {
        'matcher': 'Bash',
        'hook': {'type': 'command', 'command': 'python3 ~/.claude/hooks/output-trimmer.py'}
    },
    'PreToolUse': {
        'matcher': 'Bash',
        'hook': {'type': 'command', 'command': 'python3 ~/.claude/hooks/secret-scanner.py'}
    }
}

for event, config in arc_hooks.items():
    event_hooks = hooks.setdefault(event, [])
    # Find existing group with same matcher or create new one
    target_group = None
    for group in event_hooks:
        if group.get('matcher', '') == config['matcher']:
            target_group = group
            break
    if target_group is None:
        target_group = {'matcher': config['matcher'], 'hooks': []}
        event_hooks.append(target_group)
    # Add hook if not already present
    hook_cmd = config['hook']['command']
    if not any(h.get('command') == hook_cmd for h in target_group.get('hooks', [])):
        target_group.setdefault('hooks', []).append(config['hook'])

with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
PYEOF
  echo "   ✓  settings.json updated (hooks merged, existing hooks preserved)"
fi

echo ""
echo "======================================="
echo "✓ ARC installed!"
echo ""
echo "Next steps:"
echo "  1. Edit ~/.arc/global to add your own rules"
echo "  2. Create new domains in ~/.arc/ following the examples"
echo "  3. Update ~/.arc/manifest to register your domains"
echo "  4. Restart Claude Code"
echo ""
echo "Docs: https://github.com/vasyl-pavlyuchok/arc"
